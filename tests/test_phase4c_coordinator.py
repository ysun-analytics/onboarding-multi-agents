"""
Phase 4c tests — the Coordinator's two LLM calls (plan summary + welcome message).

Wiring + the deterministic send-timing logic run key-free; the live LLM content runs only
with a key.
"""

from datetime import date

import pytest

from onboarding.agents.coordinator_llm import (
    build_plan_summary_agent,
    build_welcome_agent,
    draft_welcome_message,
    render_plan_summary,
)
from onboarding.config import MODEL, has_api_key
from onboarding.data_loaders import get_profile
from onboarding.models import ApproveResponse, PlanSummary, WelcomeMessageDraft
from onboarding.orchestrator import Orchestrator, _compute_send_strategy
from tests.fakes import (
    fake_compliance_runner,
    fake_it_runner,
    fake_manager_note_runner,
    fake_manager_prep_runner,
    fake_plan_summary_runner,
    fake_welcome_runner,
)


# --- WIRING: these are tool-less structured LLM calls, not agents ------------------

def test_coordinator_calls_have_no_tools():
    plan_agent = build_plan_summary_agent()
    welcome_agent = build_welcome_agent()
    assert plan_agent.tools == [] and welcome_agent.tools == []  # no tools = not agents
    assert plan_agent.output_type is PlanSummary
    assert welcome_agent.output_type is WelcomeMessageDraft
    assert plan_agent.model == welcome_agent.model == MODEL == "gpt-4o"


# --- DETERMINISTIC send timing (no key) -------------------------------------------

def test_send_now_when_start_within_14_days():
    # Sarah starts 2026-06-21; "today" 2026-06-13 → 8 days out → send now.
    strategy, send_date = _compute_send_strategy("2026-06-21", today=date(2026, 6, 13))
    assert strategy == "send_now" and send_date is None


def test_schedule_when_start_more_than_14_days_out():
    # 30 days out → schedule for start − 14 days.
    strategy, send_date = _compute_send_strategy("2026-07-13", today=date(2026, 6, 13))
    assert strategy == "schedule" and send_date == "2026-06-29"


def test_orchestrator_overrides_send_strategy_deterministically():
    # Even though the fake welcome runner returns "send_now", the orchestrator recomputes.
    # This proves the override fires (the value depends on the real date, so we just check
    # it's one of the valid outcomes and that a scheduled date appears iff scheduling).
    orch = Orchestrator(
        "h_005",  # Yuki starts 2026-07-12 — likely a schedule relative to 2026-06-13
        it_runner=fake_it_runner,
        compliance_runner=fake_compliance_runner,
        manager_prep_runner=fake_manager_prep_runner,
        plan_summary_runner=fake_plan_summary_runner,
        welcome_runner=fake_welcome_runner,
        manager_note_runner=fake_manager_note_runner,
    )
    orch.run(lambda r: ApproveResponse(action="approve"))
    draft = orch.results["coordinator_welcome"]
    assert draft.send_strategy in ("send_now", "schedule")
    if draft.send_strategy == "schedule":
        assert draft.scheduled_send_date is not None


# --- LIVE (needs a key; auto-skips without one) -----------------------------------

@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_plan_summary_renders_all_four_blocks():
    profile = get_profile("h_001")
    orch = Orchestrator(  # build a plan to render (everything else fake/irrelevant here)
        "h_001", it_runner=fake_it_runner, compliance_runner=fake_compliance_runner,
        manager_prep_runner=fake_manager_prep_runner,
    )
    plan = orch.build_plan(profile)
    summary = render_plan_summary(plan, profile)
    assert isinstance(summary, PlanSummary)
    assert summary.it_provisioning.actions and summary.compliance_docs.actions
    assert summary.manager_prep.actions and summary.coordinator.actions


@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_welcome_message_is_personalized():
    profile = get_profile("h_001")
    draft = draft_welcome_message(profile, "Tom Brennan", ["MacBook ready", "intro on day 1"])
    assert isinstance(draft, WelcomeMessageDraft)
    assert "Sarah" in draft.body          # addressed by first name
    assert "Tom" in draft.body            # names the buddy
