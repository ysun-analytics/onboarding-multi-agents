"""
orchestrator.py — the Onboarding Coordinator, implemented as a STATE MACHINE.

This is the single most important design decision in the project, so it gets the
longest comment.

The orchestrator is NOT an agent. Its job — who runs, in what order, in parallel or
sequentially, and which human gates to surface — is deterministic routing. Routing
is a RULE, not a judgment, so it does not get an LLM. Using an LLM here would add
latency and non-determinism while removing the one thing we most want from an
orchestrator: predictability. (The orchestrator DOES make two LLM calls later, in
Phase 4 — rendering the plan summary and drafting the welcome message — because
those are content-generation tasks where natural language is the product. Routing
is not one of them.)

That is the answer to the interview's sharpest question, "why agents at all?":
because we reserve agents for judgment-heavy work and keep the plumbing deterministic.

WHAT IS STUBBED IN PHASE 2:
  The four specialist "agents" here return canned, profile-derived placeholder data
  (look for `_stub`). In Phase 3 these become real OpenAI Agents SDK calls. What is
  NOT stubbed — and is the real deliverable of Phase 2 — is the routing and the
  deterministic gate ANTICIPATION in build_plan(): from the profile + catalogs alone,
  before any agent runs, the orchestrator can predict that Sarah will trip the AWS
  special-access gate and Yuki will trip a compliance escalation. That prediction is
  the proof that the routing is real logic, not a script.

HOW HUMAN GATES ARE HANDLED:
  run() takes a `gate_handler` callback. Whenever the machine reaches a HITL gate it
  calls gate_handler(request) and waits for a HITLResponse. The orchestrator does not
  know or care whether a human (the Streamlit dashboard) or an automated test answers
  — it just calls the handler. That inversion of control is how the SAME state machine
  drives both the live demo and the unit tests.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Dict, Generator, List, Literal, Optional, Tuple

from . import data_loaders as data
from .models import (
    AcknowledgeResponse,
    ApproveResponse,
    ComplianceEscalation,
    DenyResponse,
    EditResponse,
    ComplianceResult,
    HardwareItem,
    HITLRequest,
    HITLResponse,
    IntroMeetingScheduled,
    ManagerNoteDraft,
    ManagerPrepResult,
    NewHireProfile,
    OnboardingPlan,
    PlannedAgentWork,
    ProvisioningResult,
    ProvisioningSummary,
    ReasoningTrace,
    RequiredDocument,
    SpecialAccessRequest,
    ThirtySixtyNinety,
    ValidationResult,
    WelcomeMessageDraft,
)

# The states the machine can occupy. Naming them explicitly (rather than tracking
# progress with scattered booleans) is what makes this a state machine: at any moment
# the dashboard can read orchestrator.state and know exactly where the hire is.
OnboardingState = Literal[
    "received",
    "halted_invalid",          # validation failed — Scenario D
    "awaiting_plan_approval",
    "provisioning_and_compliance",  # wave 1: IT + Compliance run "in parallel"
    "manager_prep",                 # wave 2: needs IT's provisioning summary first
    "drafting_welcome",
    "monitoring",                   # readiness check scheduled for T-3 days
    "complete",
]

# Rank used to evaluate seniority thresholds on special-access systems.
_SENIORITY_RANK = {
    "junior": 0, "mid": 1, "senior": 2, "staff": 3, "principal": 4, "exec": 5,
}

# A gate_handler answers a HITL request. The dashboard supplies a real one; tests
# supply an auto-responder.
GateHandler = Callable[[HITLRequest], HITLResponse]

# The welcome-message send window: send immediately if the start date is within 14 days,
# otherwise schedule the send for 14 days before start (HITL gate spec). `today` is a
# parameter so tests can pin the reference date instead of depending on the real clock.
WELCOME_LEAD_DAYS = 14


def _compute_send_strategy(
    start_date: str, today: Optional[date] = None
) -> Tuple[str, Optional[str]]:
    """Deterministic send timing — a date computation, not a judgment, so it lives in
    code and overrides whatever the LLM guessed. Returns (strategy, scheduled_send_date)."""
    today = today or date.today()
    start = date.fromisoformat(start_date)
    if (start - today).days <= WELCOME_LEAD_DAYS:
        return "send_now", None
    return "schedule", (start - timedelta(days=WELCOME_LEAD_DAYS)).isoformat()


class Orchestrator:
    def __init__(
        self,
        hire_id: str,
        *,
        it_runner: Optional[Callable[[NewHireProfile], ProvisioningResult]] = None,
        compliance_runner: Optional[Callable[[NewHireProfile], ComplianceResult]] = None,
        manager_prep_runner: Optional[Callable[..., ManagerPrepResult]] = None,
        plan_summary_runner: Optional[Callable[..., PlanSummary]] = None,
        welcome_runner: Optional[Callable[..., WelcomeMessageDraft]] = None,
        manager_note_runner: Optional[Callable[..., ManagerNoteDraft]] = None,
    ) -> None:
        self.hire_id = hire_id
        self.state: OnboardingState = "received"
        self.events: List[str] = []          # human-readable trace for the dashboard
        self.plan: Optional[OnboardingPlan] = None
        self.plan_summary: Optional[PlanSummary] = None  # LLM call #1 output
        self.results: Dict[str, object] = {}  # agent name -> its typed result
        self.gates_fired: List[str] = []      # which HITL gates actually surfaced
        # Dependency injection for the agents AND the coordinator's two LLM calls.
        # Default = the real LLM; tests inject fakes so routing tests stay fast,
        # deterministic, and key-free.
        self._it_runner = it_runner
        self._compliance_runner = compliance_runner
        self._manager_prep_runner = manager_prep_runner
        self._plan_summary_runner = plan_summary_runner
        self._welcome_runner = welcome_runner
        self._manager_note_runner = manager_note_runner

    def _provision(self, profile: NewHireProfile) -> ProvisioningResult:
        """Run IT provisioning via the injected runner, or the real agent by default.
        The real agent is imported lazily so that pure-routing tests never need the
        OpenAI SDK key just to import the orchestrator."""
        if self._it_runner is not None:
            return self._it_runner(profile)
        from .agents.it_provisioning import run_it_provisioning
        return run_it_provisioning(profile)

    def _check_compliance(self, profile: NewHireProfile) -> ComplianceResult:
        """Run Compliance via the injected runner, or the real agent by default."""
        if self._compliance_runner is not None:
            return self._compliance_runner(profile)
        from .agents.compliance_docs import run_compliance_docs
        return run_compliance_docs(profile)

    def _prep_manager(
        self, profile: NewHireProfile, provisioning: ProvisioningSummary
    ) -> ManagerPrepResult:
        """Run Manager Prep via the injected runner, or the real agent by default.
        Note this is the one handoff that carries a second argument — the provisioning
        summary — because the 30-60-90 plan must reference what the hire will actually have."""
        if self._manager_prep_runner is not None:
            return self._manager_prep_runner(profile, provisioning)
        from .agents.manager_prep import run_manager_prep
        return run_manager_prep(profile, provisioning)

    def _render_plan_summary(self, plan: OnboardingPlan, profile: NewHireProfile) -> PlanSummary:
        """LLM call #1 — render the deterministic plan in plain English."""
        if self._plan_summary_runner is not None:
            return self._plan_summary_runner(plan, profile)
        from .agents.coordinator_llm import render_plan_summary
        return render_plan_summary(plan, profile)

    def _draft_welcome(
        self, profile: NewHireProfile, buddy_name: str, logistics: List[str]
    ) -> WelcomeMessageDraft:
        """LLM call #2 — draft the welcome message, then OVERRIDE the send timing
        deterministically. The LLM writes the words; code decides the when, because send
        timing is a date computation, not a judgment (facts-vs-judgment, applied)."""
        if self._welcome_runner is not None:
            draft = self._welcome_runner(profile, buddy_name, logistics)
        else:
            from .agents.coordinator_llm import draft_welcome_message
            draft = draft_welcome_message(profile, buddy_name, logistics)
        strategy, send_date = _compute_send_strategy(profile.start_date)
        return draft.model_copy(update={"send_strategy": strategy, "scheduled_send_date": send_date})

    def _draft_manager_note(
        self, profile: NewHireProfile, manager_name: str, mp: ManagerPrepResult
    ) -> ManagerNoteDraft:
        """LLM call #3 — the Assistant drafts the cover note that hands the Manager Prep
        package to the manager. Same shape as _draft_welcome: injected fake in tests, real
        LLM call by default. No send-timing override here — the note goes to an internal
        colleague on approval, so there is no schedule-vs-now date judgment to make."""
        if self._manager_note_runner is not None:
            return self._manager_note_runner(profile, manager_name, mp)
        from .agents.coordinator_llm import draft_manager_note
        return draft_manager_note(profile, manager_name, mp)

    # -- small logging helper so every transition is visible in the demo ----------
    def _log(self, message: str) -> None:
        self.events.append(message)

    # =====================================================================
    # STEP 2 — validation (deterministic, Python)
    # =====================================================================
    def validate(self) -> ValidationResult:
        """Try to parse the raw profile into the typed model. If the type system
        rejects it (e.g. missing start_date), we surface the errors gracefully
        instead of crashing — this is the Scenario D 'malformed profile' path."""
        try:
            profile = data.get_profile(self.hire_id)
            self._profile = profile
            return ValidationResult(is_valid=True)
        except Exception as exc:  # pydantic.ValidationError or KeyError
            errors = [line.strip() for line in str(exc).splitlines() if line.strip()]
            return ValidationResult(is_valid=False, errors=errors)

    # =====================================================================
    # STEP 3 — build the onboarding plan DETERMINISTICALLY
    # =====================================================================
    def build_plan(self, profile: NewHireProfile) -> OnboardingPlan:
        """The heart of Phase 2. Pure Python rules over the profile + catalogs.

        Crucially, this ANTICIPATES which HITL gates will fire — before any agent
        runs — by reading the same catalogs the agents will use. That foresight is
        the orchestrator's value proposition: one consolidated, predictable plan."""

        # --- IT Provisioning: hardware + systems, anticipate special-access gate ---
        hardware = data.get_default_hardware(profile.role_family)
        software = data.get_software_for_role(profile.role_family)
        it_actions = [
            f"Provision hardware: {hardware}",
            f"Create accounts for {len(software)} role-standard system(s)",
            "Assign role security groups",
        ]
        it_gates = []
        if self._anticipates_special_access(profile, software):
            it_actions.append("Flag elevated/sensitive access for manager approval")
            it_gates.append("special_access")

        # --- Compliance: docs by jurisdiction, anticipate unknown-combo escalation -
        jurisdiction_known = profile.location.country in data.get_known_jurisdictions()
        comp_actions = [
            "Determine required documents for "
            f"{profile.location.country} / {profile.employment_type}",
            "Track completion and send reminders as start date approaches",
        ]
        comp_gates = []
        if not jurisdiction_known:
            comp_actions.append(
                "Surface unfamiliar-jurisdiction escalation with best-effort doc set"
            )
            comp_gates.append("escalation")

        # --- Manager Prep (wave 2): always drafts a plan needing sign-off ----------
        mp_actions = [
            "Draft a role-tailored 30-60-90 day plan",
            "Schedule a manager intro meeting",
            "Recommend an onboarding buddy",
            "Send the manager a prep checklist",
        ]
        mp_gates = ["30_60_90_signoff"]

        # --- Coordinator's own work (wave 0): consolidated plan + welcome + monitor -
        coord_actions = [
            "Render this consolidated plan for approval",
            "Draft a personalized welcome message",
            "Run a readiness check 3 days before start date",
        ]
        coord_gates = ["plan_approval", "welcome_message_review", "readiness_at_risk"]

        work = [
            PlannedAgentWork(agent="coordinator", will_run=True, run_wave=0,
                             anticipated_actions=coord_actions, anticipated_gates=coord_gates),
            PlannedAgentWork(agent="it_provisioning", will_run=True, run_wave=1,
                             anticipated_actions=it_actions, anticipated_gates=it_gates),
            PlannedAgentWork(agent="compliance_docs", will_run=True, run_wave=1,
                             anticipated_actions=comp_actions, anticipated_gates=comp_gates),
            PlannedAgentWork(agent="manager_prep", will_run=True, run_wave=2,
                             anticipated_actions=mp_actions, anticipated_gates=mp_gates),
        ]
        note = (
            f"{profile.role_family}/{profile.employment_type} in "
            f"{profile.location.country}: IT + Compliance run in parallel, "
            f"Manager Prep follows IT."
        )
        return OnboardingPlan(hire_id=profile.hire_id, profile=profile, work=work, note=note)

    def _anticipates_special_access(self, profile: NewHireProfile, software: List[dict]) -> bool:
        """A system trips the special-access gate if it requires approval AND the
        hire meets any seniority threshold attached to it. Mirrors the IT agent's
        own logic so the plan can predict the gate before the agent runs."""
        hire_rank = _SENIORITY_RANK[profile.seniority]
        for item in software:
            if not item.get("requires_approval"):
                continue
            threshold = item.get("seniority_threshold")
            if threshold is None or hire_rank >= _SENIORITY_RANK[threshold]:
                return True
        return False

    # =====================================================================
    # The core engine — a GENERATOR that walks the state machine and PAUSES at
    # every human gate.
    #
    # Why a generator? A HITL gate has to stop the whole machine and wait for a
    # person to click a button in a browser. Over HTTP there is nothing to "block"
    # on — the request that started the run has long since returned, and the click
    # arrives in a *separate* request minutes later. A plain function can't pause in
    # the middle and resume later; a generator can. `yield request` freezes the
    # machine exactly where it is, hands the gate out to the caller, and the matching
    # `.send(response)` later thaws it and resumes with the human's decision.
    #
    # run() (below) is the thin driver for the synchronous case — tests and the
    # cache-builder — that answers each gate immediately. The FastAPI server drives
    # the SAME generator by hand: next() to the first gate, return it over HTTP,
    # and send() the answer when the button click arrives. One engine, two drivers.
    # =====================================================================
    def run_steps(self) -> "Generator[HITLRequest, HITLResponse, None]":
        # STEP 1-2: receive + validate
        self._log(f"Received profile {self.hire_id}.")
        validation = self.validate()
        if not validation.is_valid:
            self.state = "halted_invalid"
            self._log(f"HALTED: profile invalid — {'; '.join(validation.errors)}")
            return
        profile: NewHireProfile = self._profile
        self._log(f"Validated {profile.full_name} ({profile.role_title}).")

        # STEP 3: build plan deterministically (Python rules).
        self.plan = self.build_plan(profile)
        self._log(f"Built consolidated plan. {self.plan.note}")

        # STEP 4: LLM call #1 — render the plan in plain English for the coordinator.
        self.plan_summary = self._render_plan_summary(self.plan, profile)
        self._log("Rendered plan summary for approval.")

        # STEP 5: plan_approval gate — pause for the human
        proceed = yield from self._emit_gate(self._plan_approval_request(self.plan))
        if not proceed:
            self._log("Plan not approved; halting. (Phase 4 wires edit/request-changes.)")
            return
        self.state = "provisioning_and_compliance"

        # STEP 6: IT Provisioning + Compliance are the "parallel wave." We run BOTH to
        # completion and record their results BEFORE surfacing any approval gate. That
        # ordering matters for the dashboard: when the human lands on IT's special-access
        # gate, Compliance is already shown as complete — matching the "they run at the
        # same time" handoff note. If we surfaced IT's gate before Compliance ran, the UI
        # would (correctly but confusingly) show Compliance as "not started yet," which
        # contradicts the parallel framing. (We run them sequentially in code; the gates
        # are deferred so the *observable* behavior is the parallel wave finishing first.)
        it_result = self._provision(profile)
        self.results["it_provisioning"] = it_result
        self._log(f"IT Provisioning complete: {it_result.hardware.item}.")

        comp_result = self._check_compliance(profile)
        self.results["compliance_docs"] = comp_result
        self._log(f"Compliance complete: {len(comp_result.required_documents)} document(s).")

        # Both specialists have finished the wave; now surface the approvals they raised.
        if it_result.special_access_requests:
            names = ", ".join(r.system for r in it_result.special_access_requests)
            yield from self._emit_gate(self._special_access_request(it_result))
            self._log(f"Special-access gate surfaced for: {names}.")
        if comp_result.escalations:
            yield from self._emit_gate(self._compliance_escalation_request(comp_result))
            self._log("Compliance escalation gate surfaced (unfamiliar jurisdiction).")

        # STEP 7-8: Manager Prep runs AFTER IT (needs the provisioning summary)
        self.state = "manager_prep"
        prov_summary = self._derive_provisioning_summary(it_result)
        mp_result = self._prep_manager(profile, prov_summary)
        self.results["manager_prep"] = mp_result
        # The Assistant auto-drafts the cover note that packages this for the manager (LLM #3)
        # and frames the 30-60-90 as a draft the manager owns. The coordinator reviews this
        # note and sends it (or an edit) to the manager — that is what the gate below decides.
        manager_name = data.get_manager_name(profile.manager_id)
        note = self._draft_manager_note(profile, manager_name, mp_result)
        self.results["manager_note"] = note
        self._log(f"Manager Prep complete: draft 30-60-90 + cover note ready to send to {manager_name}.")
        yield from self._emit_gate(self._signoff_request(mp_result, note, manager_name))

        # STEP 10-12: LLM call #2 — draft welcome message + review gate.
        self.state = "drafting_welcome"
        buddy_name = mp_result.buddy_recommendation.name
        logistics = self._day_one_logistics(prov_summary, mp_result)
        welcome = self._draft_welcome(profile, buddy_name, logistics)
        self.results["coordinator_welcome"] = welcome
        yield from self._emit_gate(self._welcome_review_request(welcome))
        self._log(f"Welcome message ready ({welcome.send_strategy}).")

        # STEP 13: schedule readiness check (the alert is computed at T-3 in Phase 4)
        self.state = "monitoring"
        self._log("Scheduled readiness check for 3 days before start date.")

        # STEP 14: done
        self.state = "complete"
        self._log("Onboarding plan fully assembled. All gates resolved.")

    # =====================================================================
    # The synchronous driver — answers each gate immediately via a callback.
    # Used by the tests and the demo-cache builder. The dashboard does NOT use this;
    # it drives run_steps() by hand so it can pause across HTTP requests.
    # =====================================================================
    def run(self, gate_handler: GateHandler) -> None:
        gen = self.run_steps()
        try:
            request = next(gen)          # advance to the first gate
            while True:
                response = gate_handler(request)
                request = gen.send(response)  # answer it, advance to the next
        except StopIteration:
            return                        # generator finished — flow is complete

    # -- gate plumbing ------------------------------------------------------------
    def _emit_gate(
        self, request: HITLRequest
    ) -> "Generator[HITLRequest, HITLResponse, bool]":
        """Surface a gate and PAUSE. Records the gate, yields the request to whoever is
        driving the generator, and resumes when they send() back a response. Returns
        True if the flow may proceed (approve/acknowledge), False otherwise.

        In Phase 2 we treat approve/acknowledge as 'proceed' and anything else as a
        stop; Phase 4 implements edit + request_changes + the 2-revision cap."""
        self.gates_fired.append(request.gate_type)
        response = yield request
        # What "proceed" means: approve / acknowledge proceed; an Edit is an approval of the
        # EDITED version, so it proceeds too. A DENY also proceeds — declining special access
        # doesn't halt onboarding, the hire just doesn't get that grant. (Request-changes and
        # anything else would stop the flow.)
        return isinstance(
            response, (ApproveResponse, AcknowledgeResponse, EditResponse, DenyResponse)
        )

    # =====================================================================
    # HITL request builders — turn agent output into a dashboard card
    # =====================================================================
    def _plan_approval_request(self, plan: OnboardingPlan) -> HITLRequest:
        # Payload carries both the deterministic plan AND the LLM-rendered summary, so the
        # dashboard shows the plain-English version while the structured plan stays the
        # source of truth.
        payload = {"plan": plan.model_dump()}
        if self.plan_summary is not None:
            payload["plan_summary"] = self.plan_summary.model_dump()
        return HITLRequest(
            gate_type="plan_approval", agent="coordinator",
            summary=f"Approve the onboarding plan for {plan.profile.full_name}.",
            proposed_decision="Proceed with the consolidated plan as shown.",
            rationale=plan.note,
            payload=payload,
        )

    def _special_access_request(self, it: ProvisioningResult) -> HITLRequest:
        req = it.special_access_requests[0]
        return HITLRequest(
            gate_type="special_access", agent="it_provisioning",
            summary=f"Approve {req.system} access ({req.requested_access}).",
            proposed_decision=f"Grant {req.requested_access} on {req.system}.",
            rationale=req.rationale,
            payload={"requests": [r.model_dump() for r in it.special_access_requests]},
        )

    def _compliance_escalation_request(self, comp: ComplianceResult) -> HITLRequest:
        esc = comp.escalations[0]
        return HITLRequest(
            gate_type="escalation", agent="compliance_docs",
            summary="Unfamiliar jurisdiction — review proposed documents.",
            proposed_decision="Use the best-effort document set shown.",
            rationale=esc.reason, alternatives=esc.proposed_document_set,
            payload={"escalation": esc.model_dump()},
        )

    def _signoff_request(
        self, mp: ManagerPrepResult, note: ManagerNoteDraft, manager_name: str
    ) -> HITLRequest:
        # We KEEP the internal gate_type "30_60_90_signoff" (stable id the tests, view-model and
        # frontend route on) but the DISPLAY is now "review & send to the manager" — the same
        # code-identifier-vs-display-name split we use for coordinator/Assistant. The decision is
        # no longer "sign off before it reaches the hire"; it's "review this package and send it
        # to the MANAGER, who then owns and customizes the draft 30-60-90."
        return HITLRequest(
            gate_type="30_60_90_signoff", agent="manager_prep",
            summary=f"Review and send the onboarding package to {manager_name}.",
            proposed_decision=f"Send the cover note + draft 30-60-90 to {manager_name}.",
            rationale=(
                "The 30-60-90 is a starting draft for the manager to own and customize. "
                "Review the package, then send it to them."
            ),
            payload={
                "plan": mp.thirty_sixty_ninety.model_dump(),
                "note": note.model_dump(),
                "manager_name": manager_name,
            },
        )

    def _welcome_review_request(self, w: WelcomeMessageDraft) -> HITLRequest:
        return HITLRequest(
            gate_type="welcome_message_review", agent="coordinator",
            summary="Review the welcome message before it is sent.",
            proposed_decision=f"{w.send_strategy} the message.",
            rationale="Personalized messages are reviewed before reaching the new hire.",
            payload={"draft": w.model_dump()},
        )

    # =====================================================================
    # Coordinator helpers. All four specialists and both LLM calls are now real;
    # the orchestrator's own job is synthesis — turning the specialists' results into
    # the inputs each downstream step needs.
    # =====================================================================
    def _day_one_logistics(
        self, prov: ProvisioningSummary, mp: ManagerPrepResult
    ) -> List[str]:
        """Synthesize 2-3 concrete day-one things for the welcome message, pulled from the
        specialists' results. This is the orchestrator's value: it stitches the picture
        together so the coordinator (and the new hire) don't have to."""
        logistics = [f"Your {prov.hardware_summary} will be set up and ready"]
        if prov.systems_provisioned:
            logistics.append(f"Access to {', '.join(prov.systems_provisioned[:3])}")
        if isinstance(mp.intro_meeting, IntroMeetingScheduled):
            logistics.append(f"An intro meeting with your manager on {mp.intro_meeting.proposed_time}")
        logistics.append(f"Your onboarding buddy, {mp.buddy_recommendation.name}, will be in touch")
        return logistics

    def _derive_provisioning_summary(self, it: ProvisioningResult) -> ProvisioningSummary:
        return ProvisioningSummary(
            hardware_summary=it.hardware.item,
            systems_provisioned=[s.system for s in it.software_access],
            pending_special_access=[r.system for r in it.special_access_requests],
        )
