"""
coordinator_llm.py — the Assistant's three content-generation LLM calls.

IMPORTANT framing for the interview: these are NOT agents. They have no tools and take
no actions — each is a single structured LLM call that turns data into language. The
orchestrator stays a deterministic state machine; it just reaches for the LLM at the
points where natural language IS the product:

  1. render_plan_summary — turn the deterministic OnboardingPlan into the plain-English
     consolidated plan the coordinator approves at the plan_approval gate.
  2. draft_welcome_message — write the personalized welcome note to the new hire.
  3. draft_manager_note — write the cover note to the hiring manager that packages the
     Manager Prep output (intro, buddy, DRAFT 30-60-90, checklist) and hands it over.

Mechanically we still use the SDK's Agent + Runner, because an Agent with output_type and
NO tools is the cleanest way to get a validated, typed result out of one LLM call. So
"tool-less Agent" = "structured LLM call" here. That distinction — agent vs. single LLM
call — is worth stating crisply: an agent loops and uses tools; these do neither.

Note on the welcome message: the SEND TIMING (send now vs. schedule) is a date
computation, not a judgment — so the orchestrator computes it deterministically and
overrides whatever the model returns. The LLM writes the words; code decides the when.
"""

from __future__ import annotations

from agents import Agent, Runner

from ..config import MODEL, ensure_api_key
from ..models import (
    IntroMeetingScheduled,
    ManagerNoteDraft,
    ManagerPrepResult,
    NewHireProfile,
    OnboardingPlan,
    PlanSummary,
    WelcomeMessageDraft,
)

# Based on 4_agent_specs.md §2.2, with one addition (2026-06-14): an explicit
# instruction to make the `reasoning` trace HIRE-SPECIFIC. The coordinator reads the
# reasoning first, at the top of the plan card, so a generic "IT sets up hardware"
# wastes the most valuable spot on the screen. We force it to name concrete
# consequences of THIS profile (expected gates, which document set, role/location
# specifics) — which is also what makes the "same agents, different reasoning"
# narrative visible at first glance instead of only after expanding a sub-card.
PLAN_SUMMARY_PROMPT = """\
You are the Onboarding Coordinator. You have just generated an onboarding plan for a new
hire by applying rules to their profile. Your job now is to render that plan as a clear,
scannable summary the HR Onboarding Coordinator can review in under 30 seconds.

For each of the four specialist agents, write:
- Two to three bullets covering the most important actions they will take.
- A single line naming which HITL approval gates will surface during their work.

Fill the `reasoning` field — this is the FIRST thing the coordinator reads, so make it
specific to THIS hire, never generic:
- reasoning.summary: one sentence capturing what is distinctive about this person and
  what it means for their onboarding — draw on their seniority, role, location, and
  employment type (e.g. a senior US engineer vs. a UK sales contractor onboard differently).
- reasoning.steps: 3 to 4 bullets, each naming a CONCRETE consequence of this specific
  profile. Good bullets: "Senior engineer → expect an AWS access gate for your approval";
  "UK contractor → IR35 / Right-to-Work document set, not the US federal one". Bad bullets:
  generic process descriptions like "IT Provisioning sets up hardware and accounts."
  Every bullet must reference something true of THIS hire's profile or plan.

NEVER calculate dates or durations yourself (you get them wrong). If you mention timing,
use the TIMING line provided in the input verbatim — do not compute "starts in N months"
or similar from the dates.

Use plain English. The reader is non-technical. Do not invent actions, gates, or details
that are not in the profile or the plan you were given. Do not editorialize or recommend
changes — your job is to render, not to advise.
"""

# Verbatim from 4_agent_specs.md §2.3.
WELCOME_PROMPT = """\
You are the Onboarding Coordinator drafting a personalized welcome message from the hiring
manager and team to a new hire.

The message must:
- Address the new hire by first name.
- Reference their specific team and role.
- Name their onboarding buddy (provided in input).
- Mention 2-3 concrete things they can expect on day one (provided in input).
- Convey warmth without sounding corporate or generic.
- Be 120-180 words. Not longer.

The message must NOT:
- Invent details about the team, company, or buddy beyond what is provided.
- Make promises about compensation, equity, or HR matters.
- Include calendar invites, document attachments, or anything beyond plain text.

For send_strategy, just return "send_now"; the system computes the real send timing
separately, so do not worry about it.
"""

# Added 2026-06-14. The 30-60-90 used to be framed as a plan handed to the new hire. We
# changed the workflow: it's now a DRAFT proposed to the MANAGER, who owns and customizes it.
# This note is how the Assistant hands that package over. The strict ORDER below is the
# coordinator's request (general → intro → buddy → 30-60-90 → checklist) — keep it.
MANAGER_NOTE_PROMPT = """\
You are the Onboarding Assistant, writing a short cover note to a HIRING MANAGER about their
incoming direct report. You have prepared an onboarding package for them: a proposed intro
meeting, an onboarding buddy, a DRAFT 30-60-90 day plan, and a manager prep checklist. The
30-60-90 and the checklist appear in full BELOW your note in the dashboard — do not repeat
them verbatim; your note introduces and frames them.

Write the note in THIS ORDER:
1. A warm, brief general opening: address the manager by name, name the new hire, their role
   and team, and when they start. For timing, quote the TIMING line in the input verbatim —
   never compute or estimate dates yourself.
2. The intro meeting: if it is scheduled, say it's booked (state the time). If it is blocked,
   say you couldn't find a slot and flag that you've proposed alternatives for them to pick.
3. The onboarding buddy: SUGGEST a person and give one line on why they're a good fit — frame
   it as a recommendation the manager can accept or swap, NOT a done deal. Use suggesting
   language ("I'd suggest X…", "X could be a great fit…"), never "X will be the buddy."
4. The 30-60-90 plan: make explicit that this is a STARTING DRAFT for the manager to review,
   edit, and make their own — not a finished plan and not yet shared with the new hire. Invite
   them to adjust it to how they actually want to run the ramp.
5. Point them to the prep checklist below.

Tone: collegial, manager-to-colleague, warm but efficient. 120-180 words. Plain text only —
no markdown, no attachments, no calendar invites. Do not invent facts beyond what you're given.

Never use bracketed placeholders like [Your Name], [Manager], or [Team]. If you sign off, sign
as "The Onboarding team" — never leave a blank to fill in.
"""


def build_plan_summary_agent() -> Agent:
    """A tool-less Agent = a single structured LLM call that returns a PlanSummary."""
    return Agent(
        name="Coordinator: Plan Summary",
        instructions=PLAN_SUMMARY_PROMPT,
        model=MODEL,
        output_type=PlanSummary,
    )


def build_welcome_agent() -> Agent:
    return Agent(
        name="Coordinator: Welcome Message",
        instructions=WELCOME_PROMPT,
        model=MODEL,
        output_type=WelcomeMessageDraft,
    )


def build_manager_note_agent() -> Agent:
    return Agent(
        name="Assistant: Manager Cover Note",
        instructions=MANAGER_NOTE_PROMPT,
        model=MODEL,
        output_type=ManagerNoteDraft,
    )


def _timing_fact(profile: NewHireProfile) -> str:
    """Compute the start-date timing in CODE and hand it to the model as a fact it may
    only quote. Date arithmetic is a fact, not a judgment — and LLMs are unreliable at it
    (an early draft confidently said a hire 7 days out 'starts in 9 months'). So we never
    let the model compute it: facts-vs-judgment, applied to the plan summary."""
    from datetime import date

    try:
        days = (date.fromisoformat(profile.start_date) - date.today()).days
    except (ValueError, TypeError):
        return "start date unavailable"
    if days < 0:
        return f"start date ({profile.start_date}) has already passed"
    horizon = "within 2 weeks" if days <= 14 else "more than 2 weeks away"
    unit = "day" if days == 1 else "days"
    return f"starts in {days} {unit} on {profile.start_date} ({horizon})"


def render_plan_summary(plan: OnboardingPlan, profile: NewHireProfile) -> PlanSummary:
    """LLM call #1. Needs OPENAI_API_KEY."""
    ensure_api_key()
    agent = build_plan_summary_agent()
    user_input = (
        "Render this onboarding plan as a scannable summary.\n\n"
        f"NEW HIRE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"TIMING (already computed — quote this, never recompute dates): {_timing_fact(profile)}\n\n"
        f"PLAN (already decided — render it, don't change it):\n{plan.model_dump_json(indent=2)}"
    )
    return Runner.run_sync(agent, user_input, context=None).final_output


def draft_welcome_message(
    profile: NewHireProfile, buddy_name: str, day_one_logistics: list
) -> WelcomeMessageDraft:
    """LLM call #2. Needs OPENAI_API_KEY. The orchestrator overrides send timing after."""
    ensure_api_key()
    agent = build_welcome_agent()
    logistics = "\n".join(f"- {item}" for item in day_one_logistics)
    user_input = (
        f"Write the welcome message.\n\n"
        f"NEW HIRE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"ONBOARDING BUDDY: {buddy_name}\n\n"
        f"DAY-ONE LOGISTICS (mention 2-3 of these):\n{logistics}"
    )
    return Runner.run_sync(agent, user_input, context=None).final_output


def draft_manager_note(
    profile: NewHireProfile, manager_name: str, mp: ManagerPrepResult
) -> ManagerNoteDraft:
    """LLM call #3. Needs OPENAI_API_KEY. Composes the cover note to the manager from the
    Manager Prep agent's structured output. The 30-60-90 and checklist are NOT re-sent to the
    model in full — the note frames them; the dashboard renders them structured below."""
    ensure_api_key()
    agent = build_manager_note_agent()
    if isinstance(mp.intro_meeting, IntroMeetingScheduled):
        intro = f"SCHEDULED for {mp.intro_meeting.proposed_time} ({mp.intro_meeting.duration_minutes} min)."
    else:
        intro = (
            "BLOCKED — no free slot. Proposed alternatives: "
            + "; ".join(mp.intro_meeting.alternatives)
        )
    user_input = (
        "Write the cover note to the hiring manager.\n\n"
        f"HIRING MANAGER: {manager_name}\n\n"
        f"NEW HIRE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"TIMING (quote this, never recompute dates): {_timing_fact(profile)}\n\n"
        f"INTRO MEETING: {intro}\n\n"
        f"ONBOARDING BUDDY: {mp.buddy_recommendation.name} "
        f"({mp.buddy_recommendation.tenure_years} yrs) — {mp.buddy_recommendation.rationale}"
    )
    return Runner.run_sync(agent, user_input, context=None).final_output
