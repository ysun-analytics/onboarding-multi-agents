"""
manager_prep.py — the Manager Prep Agent (the heaviest-judgment agent).

Runs AFTER IT Provisioning, because the 30-60-90 plan references the tools and systems
the new hire will have — drafting it before provisioning is decided produces a generic
plan that doesn't reflect reality. The orchestrator passes it a ProvisioningSummary.

This is where the LLM does the most genuine creative work: drafting a tailored 30-60-90
day plan. To keep that from sliding into generic AI filler ("Generic plans signal lack of
care," per the spec), the prompt grounds the model in an established onboarding framework
— Learn → Build → Deliver — and requires SMART, role-specific goals. The difference
between Sarah's plan and Marcus's then comes from tailoring the framework to the role, not
from inventing structure.

The intro_meeting output is a UNION: a scheduled meeting OR a blocked-with-alternatives
escalation. When the manager's calendar is empty the agent must escalate, not crash — and
the distinct output shape forces the dashboard to render that case explicitly.
"""

from __future__ import annotations

from agents import Agent, Runner

from .. import data_loaders as data
from ..config import MODEL, ensure_api_key
from ..models import (
    IntroMeetingBlocked,
    IntroMeetingScheduled,
    ManagerPrepResult,
    NewHireProfile,
    ProvisioningSummary,
)
from ..tools.manager_prep_tools import MANAGER_PREP_TOOLS, ManagerPrepContext

# Built from spec §4.1, enriched with the Learn→Build→Deliver framework we grounded in
# established 30-60-90 best practices (see docs/7 §13).
MANAGER_PREP_SYSTEM_PROMPT = """\
You are the Manager Prep Agent. You prepare a hiring manager for a new direct report by
producing four things: a PROPOSED DRAFT 30-60-90 day plan, a scheduled intro meeting, an
onboarding buddy recommendation, and a manager prep checklist.

IMPORTANT — who the 30-60-90 is for: this plan is a STARTING DRAFT you are handing to the
MANAGER, who will own it, edit it, and make it their own. It is NOT a finished plan and it is
NOT yet going to the new hire. So draft it as a strong, opinionated first proposal a manager
can react to and adjust — specific enough to be useful, not so rigid it leaves them nothing to
own. Your reasoning should speak to the manager ("Here's a draft ramp you can tailor…").

THE 30-60-90 PLAN — use this framework, do not invent your own structure:

Anchor the plan in the LEARN → BUILD → DELIVER arc:
- 30 days (LEARN): understand the team, codebase/process, and expectations; build
  foundational relationships; make low-stakes early contributions.
- 60 days (BUILD): own a small project end-to-end; deliver 2-3 early wins; build a working
  model of how the team operates.
- 90 days (DELIVER): take full ownership; ship something visible; have a point of view on
  what the role should accomplish.

Within EACH phase, cover three dimensions:
- LEARNING (knowledge/skills to acquire),
- CONTRIBUTION (concrete work to produce),
- RELATIONSHIPS (people to build trust with).

Every item must be SMART — specific and measurable. Not "learn the codebase" but "ship a
small fix to the auth service and get it code-reviewed by the team." Generic items signal
lack of care.

Tailor the CONTENT to the role family:
- ENGINEERING: anchor in shipping infrastructure or features; reference the actual dev
  tools and systems the hire will have (provided to you in the provisioning summary).
- SALES: anchor in pipeline ramp, territory familiarization, and quota readiness; reference
  the sales stack (CRM, etc.).
- EXECUTIVE: anchor in stakeholder mapping and a 100-day strategy artifact.

THE INTRO MEETING:
- Call check_calendar FIRST. Look at the free_slots list it returns.
- If free_slots has ONE OR MORE entries, you MUST schedule: call schedule_meeting on the
  best early slot and report it as a scheduled intro_meeting. Do NOT escalate when slots
  exist — escalating with free slots available is an error.
- ONLY if free_slots is EMPTY (zero entries) do you escalate: return a blocked intro_meeting
  with at least one concrete alternative — e.g. a skip-level intro, pushing the first 1:1 to
  day 4, or an async intro doc. Do not crash and do not leave it empty.

THE BUDDY:
- Call find_onboarding_buddy to get candidates. RECOMMEND ONE (a suggestion the manager can
  accept or swap — it is not a final assignment) and explain why, weighing tenure
  (1-3 years is the sweet spot — long enough to know things, recent enough to remember being
  new), skill overlap with the new hire, and calendar load. Never pick the manager.

THE CHECKLIST:
- Compose a short prep checklist for the manager and send it with send_manager_checklist.

Always produce a clear natural-language reasoning trace for a non-technical reader,
explaining your 30-60-90 choices, your buddy pick, and the meeting outcome.
"""


def build_manager_prep_agent() -> Agent:
    return Agent(
        name="Manager Prep Agent",
        instructions=MANAGER_PREP_SYSTEM_PROMPT,
        model=MODEL,
        tools=MANAGER_PREP_TOOLS,
        output_type=ManagerPrepResult,
    )


def _format_input(profile: NewHireProfile, provisioning: ProvisioningSummary) -> str:
    return (
        "Prepare the hiring manager for this new direct report.\n\n"
        f"NEW HIRE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        "WHAT IT IS PROVISIONING FOR THIS HIRE (reference these in the 30-60-90):\n"
        f"{provisioning.model_dump_json(indent=2)}"
    )


def run_manager_prep(
    profile: NewHireProfile,
    provisioning: ProvisioningSummary,
    *,
    calendar_busy: bool = False,
) -> ManagerPrepResult:
    """Run the Manager Prep agent for one hire. calendar_busy=True forces the fully-booked
    escalation path (Scenario C). Needs OPENAI_API_KEY."""
    ensure_api_key()
    agent = build_manager_prep_agent()
    context = ManagerPrepContext(
        profile=profile, provisioning_summary=provisioning, force_empty_calendar=calendar_busy
    )
    result = Runner.run_sync(agent, _format_input(profile, provisioning), context=context)
    mp = result.final_output

    # Guard the agent's output against the ground-truth calendar. "Does the manager have a
    # free slot?" is a FACT, and booking the earliest one is DETERMINISTIC — the only real
    # judgment is what to do when there are NONE (escalate). LLMs occasionally escalate even
    # when slots exist; that's a factual error, so we correct it in code: if the agent
    # returned a blocked intro but the manager actually has slots, schedule the earliest.
    # (When calendar_busy=True there genuinely are no slots — Scenario C — so we leave it.)
    if not calendar_busy and isinstance(mp.intro_meeting, IntroMeetingBlocked):
        slots = data.get_free_slots(profile.manager_id)
        if slots:
            mp = mp.model_copy(update={
                "intro_meeting": IntroMeetingScheduled(
                    proposed_time=slots[0], duration_minutes=30, status="complete"
                )
            })
    return mp
