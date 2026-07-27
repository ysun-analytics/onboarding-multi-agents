"""
Phase 4b tests — the real Manager Prep agent.

The 30-60-90 plan is creative LLM output, so we DON'T test its prose. We test the things
that must hold regardless of wording: the structure (all three phases populated), the
buddy is never the manager, the intro meeting is scheduled when slots exist, and — the
important edge case — an empty calendar produces a *blocked* escalation, not a crash.
"""

import pytest

from onboarding.agents.manager_prep import build_manager_prep_agent, run_manager_prep
from onboarding.config import MODEL, has_api_key
from onboarding.data_loaders import get_manager_name, get_profile
from onboarding.models import (
    IntroMeetingBlocked,
    IntroMeetingScheduled,
    ManagerPrepResult,
    ProvisioningSummary,
)

# A minimal provisioning summary to hand the agent (stands in for IT's real output).
_SUMMARY = ProvisioningSummary(
    hardware_summary="MacBook Pro 16-inch",
    systems_provisioned=["GitHub Enterprise", "Datadog"],
    pending_special_access=["AWS Console"],
)


# --- WIRING (no key needed) -------------------------------------------------------

def test_agent_wiring():
    agent = build_manager_prep_agent()
    assert len(agent.tools) == 4  # 30-60-90 is NOT a tool — it's the agent's judgment
    assert agent.output_type is ManagerPrepResult
    assert agent.model == MODEL == "gpt-4o"


# --- LIVE (needs a key; auto-skips without one) -----------------------------------

@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_happy_path_structure_and_buddy():
    profile = get_profile("h_001")  # Sarah; James has free slots
    result = run_manager_prep(profile, _SUMMARY)
    assert isinstance(result, ManagerPrepResult)
    # All three phases populated (Learn / Build / Deliver)
    plan = result.thirty_sixty_ninety
    assert plan.thirty_days and plan.sixty_days and plan.ninety_days
    # Intro meeting scheduled (James has availability)
    assert isinstance(result.intro_meeting, IntroMeetingScheduled)
    # Buddy is a real teammate, never the manager
    assert result.buddy_recommendation.name not in ("", get_manager_name(profile.manager_id))


@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_fully_booked_calendar_escalates_not_crashes():
    profile = get_profile("h_001")
    result = run_manager_prep(profile, _SUMMARY, calendar_busy=True)
    # The union must resolve to the BLOCKED shape, with at least one alternative offered.
    assert isinstance(result.intro_meeting, IntroMeetingBlocked)
    assert len(result.intro_meeting.alternatives) >= 1
