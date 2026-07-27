"""
fakes.py — deterministic stand-ins for the LLM agents, used by tests.

Why this exists: the routing tests check the ORCHESTRATOR's logic (who runs, which
gates fire), not the QUALITY of an agent's LLM output. Calling a real agent in those
tests would make them slow, non-deterministic, and dependent on an API key — for no
benefit, since they're not testing the agent. So we inject a fake IT runner that
reproduces the routing-relevant behavior (a senior engineer trips special access; a
sales contractor does not) with pure, instant Python.

This is the payoff of dependency injection in the Orchestrator: the same state machine
runs against real agents in the demo and fake agents in the tests.
"""

from __future__ import annotations

from onboarding import data_loaders as data
from onboarding.models import (
    BuddyRecommendation,
    ComplianceEscalation,
    ComplianceResult,
    HardwareItem,
    IntroMeetingScheduled,
    ManagerNoteDraft,
    ManagerPrepResult,
    NewHireProfile,
    OnboardingPlan,
    PlanSummary,
    PlanSummaryAgentBlock,
    ProvisioningResult,
    ProvisioningSummary,
    ReasoningTrace,
    RequiredDocument,
    SoftwareAccess,
    SpecialAccessRequest,
    ThirtySixtyNinety,
    WelcomeMessageDraft,
)

_SENIORITY_RANK = {
    "junior": 0, "mid": 1, "senior": 2, "staff": 3, "principal": 4, "exec": 5,
}


def fake_it_runner(profile: NewHireProfile) -> ProvisioningResult:
    """A catalog-driven fake of the IT agent. Deterministic, no LLM, no key needed.
    Mirrors the real agent's routing-relevant decisions: it flags special access when
    a required system needs approval and the hire meets its seniority threshold."""
    hardware = data.get_default_hardware(profile.role_family)
    software = data.get_software_for_role(profile.role_family)
    hire_rank = _SENIORITY_RANK[profile.seniority]

    special = []
    standard = []
    for item in software:
        needs_approval = item.get("requires_approval")
        threshold = item.get("seniority_threshold")
        meets_threshold = threshold is None or hire_rank >= _SENIORITY_RANK[threshold]
        if needs_approval and meets_threshold:
            special.append(SpecialAccessRequest(
                system=item["system"],
                requested_access=item["access_level"],
                rationale=item.get("approval_rationale", "Requires manager approval."),
            ))
        elif not needs_approval:
            standard.append(SoftwareAccess(
                system=item["system"], access_level=item["access_level"], status="complete",
            ))

    return ProvisioningResult(
        reasoning=ReasoningTrace(
            summary=f"[fake] Standard {profile.role_family} provisioning.",
            steps=["Deterministic test fake — not a real LLM call."],
        ),
        hardware=HardwareItem(item=hardware, status="in_progress"),
        software_access=standard,
        special_access_requests=special,
    )


def fake_compliance_runner(profile: NewHireProfile) -> ComplianceResult:
    """A catalog-driven fake of the Compliance agent. Mirrors the routing-relevant
    behavior: a known jurisdiction yields documents; an unknown one escalates."""
    known = profile.location.country in data.get_known_jurisdictions()
    docs, escalations = [], []
    if known:
        docs = [RequiredDocument(
            name="[fake] jurisdiction document set",
            deadline=profile.start_date, status="not_started",
            rationale=f"Determined by {profile.location.country}/{profile.employment_type}.",
        )]
    else:
        escalations = [ComplianceEscalation(
            reason=f"Unfamiliar jurisdiction: {profile.location.country}.",
            proposed_document_set=["[fake] closest-known-jurisdiction doc set"],
        )]
    return ComplianceResult(
        reasoning=ReasoningTrace(
            summary="[fake] Compliance determination.",
            steps=["Deterministic test fake — not a real LLM call."],
        ),
        required_documents=docs, escalations=escalations,
    )


def fake_manager_prep_runner(
    profile: NewHireProfile, provisioning: ProvisioningSummary
) -> ManagerPrepResult:
    """A deterministic fake of the Manager Prep agent: schedules the first free slot and
    picks the first non-manager teammate. Enough for routing tests; no LLM, no key."""
    slots = data.get_free_slots(profile.manager_id)
    members = [m for m in data.get_team_members(profile.team) if not m["is_manager"]]
    pick = members[0] if members else {"full_name": "(none)", "tenure_years": 0.0}
    return ManagerPrepResult(
        reasoning=ReasoningTrace(
            summary="[fake] Manager prep.",
            steps=["Deterministic test fake — not a real LLM call."],
        ),
        thirty_sixty_ninety=ThirtySixtyNinety(
            thirty_days=["[fake]"], sixty_days=["[fake]"], ninety_days=["[fake]"],
        ),
        intro_meeting=IntroMeetingScheduled(
            proposed_time=slots[0] if slots else f"{profile.start_date}T10:00",
            duration_minutes=30, status="complete",
        ),
        buddy_recommendation=BuddyRecommendation(
            name=pick["full_name"], tenure_years=float(pick["tenure_years"]),
            rationale="[fake] first non-manager teammate.", status="complete",
        ),
        manager_checklist=["[fake] prep checklist"],
    )


def _block(name: str) -> PlanSummaryAgentBlock:
    return PlanSummaryAgentBlock(actions=[f"[fake] {name} action"], gates=[])


def fake_plan_summary_runner(plan: OnboardingPlan, profile: NewHireProfile) -> PlanSummary:
    """Deterministic fake of LLM call #1 (plan summary)."""
    return PlanSummary(
        reasoning=ReasoningTrace(summary="[fake] plan summary", steps=["test fake"]),
        it_provisioning=_block("IT"),
        manager_prep=_block("Manager Prep"),
        compliance_docs=_block("Compliance"),
        coordinator=_block("Coordinator"),
    )


def fake_welcome_runner(
    profile: NewHireProfile, buddy_name: str, logistics: list
) -> WelcomeMessageDraft:
    """Deterministic fake of LLM call #2 (welcome message). The orchestrator overrides
    send_strategy deterministically, so the value here is just a placeholder."""
    return WelcomeMessageDraft(
        reasoning=ReasoningTrace(summary="[fake] welcome", steps=["test fake"]),
        subject_line=f"Welcome, {profile.full_name.split()[0]}!",
        body=f"[fake] welcome body mentioning buddy {buddy_name}.",
        send_strategy="send_now",
    )


def fake_manager_note_runner(
    profile: NewHireProfile, manager_name: str, mp: ManagerPrepResult
) -> ManagerNoteDraft:
    """Deterministic fake of LLM call #3 (the cover note to the manager)."""
    return ManagerNoteDraft(
        reasoning=ReasoningTrace(summary="[fake] manager note", steps=["test fake"]),
        subject_line=f"Onboarding package for {profile.full_name}",
        body=(f"[fake] note to {manager_name}: intro, buddy "
              f"{mp.buddy_recommendation.name}, and a draft 30-60-90 for you to make your own."),
    )
