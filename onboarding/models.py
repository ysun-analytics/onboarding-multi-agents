"""
models.py — the shared data contracts for the onboarding system.

This is the spine of the whole project. Every agent, tool, and the orchestrator
imports types from here. We define them ONCE so there is a single source of truth
for "what shape is a new-hire profile" or "what does a HITL request look like."

Why Pydantic (and not plain dicts or dataclasses):
  Pydantic validates data against a schema AT RUNTIME. When an LLM later returns
  an agent's output, we hand it to Pydantic; if the model hallucinated a field or
  dropped a required one, Pydantic raises an error immediately — instead of the bad
  data silently flowing three steps downstream and corrupting the dashboard. This is
  the machinery behind the interview talking point "handoffs are typed JSON contracts."

These types are the Python translation of the TypeScript-style contracts in
4_agent_specs.md §1. Keeping them faithful to that doc matters: the doc is what
Yuyan studies for the interview, the code is what runs the demo — they must agree.
"""

from __future__ import annotations  # lets us write list[str] / X | None on Python 3.9

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Enumerations (closed sets of allowed values)
# ---------------------------------------------------------------------------
# We use Literal[...] instead of Python's Enum class because Pydantic treats a
# Literal as "the value must be exactly one of these strings." It serializes to
# plain JSON strings (what the LLM and the mock data files actually use) with no
# conversion layer. An Enum would force .value lookups everywhere for no benefit.

EmploymentType = Literal["fte", "contractor"]

# role_family is deliberately COARSE (6 buckets, not 50 job titles). Design choice:
# the LLM is good at fuzzy categorization, the type system is not. We let the agent
# reason about "Senior Data Scientist" nuance from role_title in its prompt, while
# role_family drives the deterministic routing. See 4_agent_specs.md §3.6.
RoleFamily = Literal[
    "engineering", "sales", "operations", "finance", "executive", "other"
]

Seniority = Literal["junior", "mid", "senior", "staff", "principal", "exec"]

# The lifecycle status any agent's work can be in. Used for dashboard indicators.
AgentStatus = Literal[
    "pending", "in_progress", "awaiting_approval", "complete", "blocked"
]

# Which of the four "org-chart" actors produced something.
AgentName = Literal["coordinator", "it_provisioning", "manager_prep", "compliance_docs"]

# The five HITL gates + the escalation gate. Note "30_60_90_signoff" starts with a
# digit — fine as a string value, just not as a Python identifier.
GateType = Literal[
    "plan_approval",
    "special_access",
    "30_60_90_signoff",
    "welcome_message_review",
    "readiness_at_risk",
    "escalation",
]


# ---------------------------------------------------------------------------
# 2. Primitive shared structures
# ---------------------------------------------------------------------------

class Location(BaseModel):
    country: str  # ISO-ish short code in our mock data: "US", "UK", "SG"
    city: str


class ReasoningTrace(BaseModel):
    """The agent's natural-language 'why', kept in a DEDICATED field.

    Design choice: every structured output carries its reasoning here rather than
    mixing prose into the data fields. This keeps the machine-readable data clean
    while still surfacing the human-readable explanation the non-technical
    coordinator needs to trust the decision. 'Trust through visibility' in code.
    """

    summary: str          # one-line plain English, for the dashboard card header
    steps: List[str]      # step-by-step reasoning, shown when the user expands


# ---------------------------------------------------------------------------
# 3. The new-hire profile — the input that starts everything
# ---------------------------------------------------------------------------

class NewHireProfile(BaseModel):
    """The system's entry point. Mirrors mock_data/profiles.json.

    start_date is REQUIRED. That is intentional: the 'test_malformed' profile in
    the mock data is missing it, so validating that profile raises an error — which
    is exactly the Scenario D graceful-failure demo. The type system itself is what
    catches the bad input.
    """

    hire_id: str
    full_name: str
    role_title: str        # human-readable, e.g. "Senior Software Engineer"
    role_family: RoleFamily  # routable category used by deterministic logic
    team: str
    manager_id: str        # manager's name/details resolved via the org roster
    location: Location
    employment_type: EmploymentType
    start_date: str        # ISO 8601 date string, e.g. "2026-06-21"
    seniority: Seniority


class ValidationResult(BaseModel):
    """Returned by the coordinator's validate_profile step."""

    is_valid: bool
    errors: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Human-in-the-loop (HITL) types
# ---------------------------------------------------------------------------
# THREE shapes, chosen to fit the KIND of decision (the action set follows the decision,
# not the other way round):
#   - Content-review gates: approve / edit / escalate — you're reviewing something you can
#     reword (the plan, the 30-60-90, the welcome message), so "edit" makes sense.
#   - Binary-decision gates: approve / DENY — a yes/no with nothing to reword (special
#     access: grant the AWS console, or don't). "Edit" is meaningless here; the missing
#     "no" was a real gap. (Added 2026-06-14.)
#   - Alerts: acknowledge / take_action — a status to act on, not a proposal to approve
#     (only readiness_at_risk).
# The dashboard renders the right buttons based on gate_type.

class RevisionEntry(BaseModel):
    revision: int
    reasoning: ReasoningTrace
    coordinator_feedback: Optional[str] = None  # set when prior action was request_changes


class RevisionState(BaseModel):
    """Tracks how many times a gate has been revised. Capped at 2 before forced
    escalation — this bounds the 'LLM chases its tail' failure mode when feedback
    contradicts a hard rule (e.g. 'skip the I-9' for a US FTE)."""

    revision_count: int = 0
    history: List[RevisionEntry] = Field(default_factory=list)


class HITLRequest(BaseModel):
    """One card surfaced to the coordinator in the dashboard."""

    gate_type: GateType
    agent: AgentName
    summary: str               # one-line for the card
    proposed_decision: str     # what the agent recommends
    rationale: str             # why
    alternatives: Optional[List[str]] = None  # used by escalations
    payload: dict = Field(default_factory=dict)  # gate-specific data
    revision_state: RevisionState = Field(default_factory=RevisionState)


# The five possible coordinator responses. We model each action as its own class
# and union them. Pydantic's "smart" union matching distinguishes them by their
# distinct `action` literal + field set, so we don't need an explicit discriminator.
class ApproveResponse(BaseModel):
    action: Literal["approve"]
    coordinator_note: Optional[str] = None


class DenyResponse(BaseModel):
    """The 'no' on a binary-decision gate (e.g. special access). Denying does NOT halt
    onboarding — the hire simply doesn't get that access — so the flow proceeds, but the
    decision is recorded as a denial so the dashboard shows it was withheld, not granted."""

    action: Literal["deny"]
    coordinator_note: Optional[str] = None


class EditResponse(BaseModel):
    action: Literal["edit"]
    edited_payload: dict
    coordinator_note: Optional[str] = None


class RequestChangesResponse(BaseModel):
    action: Literal["request_changes"]
    feedback: str


class AcknowledgeResponse(BaseModel):
    action: Literal["acknowledge"]
    coordinator_note: Optional[str] = None


class TakeActionResponse(BaseModel):
    action: Literal["take_action"]
    target_task_id: str


HITLResponse = Union[
    ApproveResponse,
    DenyResponse,
    EditResponse,
    RequestChangesResponse,
    AcknowledgeResponse,
    TakeActionResponse,
]


# ---------------------------------------------------------------------------
# 5. The onboarding plan — built DETERMINISTICALLY by the orchestrator
# ---------------------------------------------------------------------------
# This is the orchestrator's output BEFORE any LLM call. It encodes the routing
# decision (who runs, in what order/parallelism) and the gates we can already
# anticipate from the profile + catalogs. The LLM call #1 later renders this into
# the plain-English PlanSummary the coordinator approves.
#
# Why a typed plan and not just "run the agents": the consolidated plan IS the
# orchestrator's value proposition made visible. Being able to predict which gates
# will fire — before a single agent runs — is what proves the routing is real logic,
# not an LLM guess.

class PlannedAgentWork(BaseModel):
    agent: AgentName
    will_run: bool
    run_wave: int  # execution order: 1 = first parallel wave (IT + Compliance),
                   #                  2 = Manager Prep (needs IT first),
                   #                  0 = coordinator-only work (plan, welcome msg)
    anticipated_actions: List[str]
    anticipated_gates: List[GateType] = Field(default_factory=list)


class OnboardingPlan(BaseModel):
    hire_id: str
    profile: NewHireProfile
    work: List[PlannedAgentWork]
    note: str  # one-line deterministic summary, e.g. routing rationale


# ---------------------------------------------------------------------------
# 6. Coordinator LLM-call output contracts (used in Phase 4; defined here so the
#    spine is complete and the stub orchestrator can return typed placeholders)
# ---------------------------------------------------------------------------

class PlanSummaryAgentBlock(BaseModel):
    actions: List[str]
    gates: List[str]


class PlanSummary(BaseModel):
    """Output of LLM call #1 — the human-readable consolidated plan."""

    reasoning: ReasoningTrace
    it_provisioning: PlanSummaryAgentBlock
    manager_prep: PlanSummaryAgentBlock
    compliance_docs: PlanSummaryAgentBlock
    coordinator: PlanSummaryAgentBlock


class WelcomeMessageDraft(BaseModel):
    """Output of LLM call #2 — the personalized welcome message."""

    reasoning: ReasoningTrace
    subject_line: str
    body: str
    send_strategy: Literal["send_now", "schedule"]
    scheduled_send_date: Optional[str] = None  # ISO 8601, set when scheduling


class ManagerNoteDraft(BaseModel):
    """Output of LLM call #3 — the cover note the Assistant drafts TO the hiring manager.

    Design (2026-06-14): the Manager Prep agent produces the structured 30-60-90, intro and
    buddy; the Assistant then writes ONE plain-English cover note that packages them and hands
    the work to the manager — framing the 30-60-90 as a *starting draft for the manager to own
    and customize*, not a finished plan for the new hire. The coordinator reviews this note and
    sends it (or an edited version) to the manager. Same split as the welcome message: the
    specialist supplies the data, the Assistant writes the words. No send_strategy field —
    this goes to an internal colleague on approval, so there is no schedule-vs-send-now date
    judgment to make."""

    reasoning: ReasoningTrace
    subject_line: str
    body: str


# ---------------------------------------------------------------------------
# 7. Specialist agent output contracts (built in Phase 3-4; defined now so the
#    handoff contracts are pinned down before we write the agents that fill them)
# ---------------------------------------------------------------------------

class HardwareItem(BaseModel):
    item: str
    status: AgentStatus
    notes: Optional[str] = None


class SoftwareAccess(BaseModel):
    system: str
    access_level: str
    status: AgentStatus


class SecurityGroup(BaseModel):
    group: str
    status: AgentStatus


class SpecialAccessRequest(BaseModel):
    system: str
    requested_access: str
    rationale: str
    status: Literal["awaiting_approval"] = "awaiting_approval"


class ProvisioningResult(BaseModel):
    """IT Provisioning Agent output (4_agent_specs.md §3.3)."""

    reasoning: ReasoningTrace
    hardware: HardwareItem
    software_access: List[SoftwareAccess] = Field(default_factory=list)
    security_groups: List[SecurityGroup] = Field(default_factory=list)
    special_access_requests: List[SpecialAccessRequest] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ProvisioningSummary(BaseModel):
    """The subset of ProvisioningResult that the orchestrator hands to Manager Prep.
    Manager Prep needs to know what tools the hire will have, not the full ticket
    detail — so we pass a derived summary, not the whole result."""

    hardware_summary: str
    systems_provisioned: List[str] = Field(default_factory=list)
    pending_special_access: List[str] = Field(default_factory=list)


class ThirtySixtyNinety(BaseModel):
    # This is a DRAFT the manager owns, not a finished plan. The Assistant proposes it; the
    # manager edits and makes it their own after the coordinator sends it over. The status
    # value reflects that it's awaiting the coordinator's review-and-send, not a final sign-off.
    thirty_days: List[str]
    sixty_days: List[str]
    ninety_days: List[str]
    status: Literal["draft_awaiting_signoff"] = "draft_awaiting_signoff"


class IntroMeetingScheduled(BaseModel):
    proposed_time: str  # ISO 8601
    duration_minutes: int
    status: AgentStatus


class IntroMeetingBlocked(BaseModel):
    status: Literal["blocked"] = "blocked"
    reason: str
    alternatives: List[str]


class BuddyRecommendation(BaseModel):
    name: str
    tenure_years: float
    rationale: str
    status: AgentStatus


class ManagerPrepResult(BaseModel):
    """Manager Prep Agent output (4_agent_specs.md §4.3).

    intro_meeting is a UNION of two shapes: scheduled vs. blocked-with-alternatives.
    Modeling the failure case as a distinct shape (not an empty 'scheduled') forces
    the dashboard to render the escalation explicitly — we can't accidentally treat
    a scheduling failure as a soft success."""

    reasoning: ReasoningTrace
    thirty_sixty_ninety: ThirtySixtyNinety
    intro_meeting: Union[IntroMeetingScheduled, IntroMeetingBlocked]
    buddy_recommendation: BuddyRecommendation
    manager_checklist: List[str] = Field(default_factory=list)


class RequiredDocument(BaseModel):
    name: str
    deadline: str  # ISO 8601
    status: Literal["not_started", "sent", "in_progress", "completed", "overdue"]
    rationale: str


class ComplianceEscalation(BaseModel):
    reason: str
    proposed_document_set: List[str]
    requires_human_review: Literal[True] = True


class ComplianceResult(BaseModel):
    """Compliance & Docs Agent output (4_agent_specs.md §5.3)."""

    reasoning: ReasoningTrace
    required_documents: List[RequiredDocument] = Field(default_factory=list)
    escalations: List[ComplianceEscalation] = Field(default_factory=list)
