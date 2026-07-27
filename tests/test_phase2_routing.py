"""
Phase 2 tests — protect the demo invariants for the orchestrator's deterministic
routing and graceful failure. These are not coverage-for-coverage's-sake; each one
guards a specific thing the interviewer will see (CLAUDE.md §Testing).

Run: python3 -m pytest tests/ -q     (or: python3 -m pytest tests/test_phase2_routing.py)
"""

from onboarding.models import ApproveResponse
from onboarding.orchestrator import Orchestrator

from .fakes import (
    fake_compliance_runner,
    fake_it_runner,
    fake_manager_note_runner,
    fake_manager_prep_runner,
    fake_plan_summary_runner,
    fake_welcome_runner,
)


def _approve_all(_request):
    """A gate handler that approves everything — stands in for the human/dashboard."""
    return ApproveResponse(action="approve")


def _run(hire_id):
    # Inject fakes for all four agents AND both coordinator LLM calls, so these routing
    # tests are key-free and deterministic.
    orch = Orchestrator(
        hire_id,
        it_runner=fake_it_runner,
        compliance_runner=fake_compliance_runner,
        manager_prep_runner=fake_manager_prep_runner,
        plan_summary_runner=fake_plan_summary_runner,
        welcome_runner=fake_welcome_runner,
        manager_note_runner=fake_manager_note_runner,
    )
    orch.run(_approve_all)
    return orch


# --- Invariant: the happy path completes for both hero profiles -------------------

def test_sarah_completes():
    orch = _run("h_001")
    assert orch.state == "complete"


def test_marcus_completes():
    orch = _run("h_002")
    assert orch.state == "complete"


# --- Invariant: the special-access gate fires for the senior engineer, NOT for the
#     sales contractor. This is the "same agents, different reasoning" proof. --------

def test_engineer_trips_special_access_gate():
    orch = _run("h_001")
    assert "special_access" in orch.gates_fired


def test_sales_contractor_does_not_trip_special_access():
    orch = _run("h_002")
    assert "special_access" not in orch.gates_fired


# --- Invariant: an unknown jurisdiction escalates instead of guessing -------------

def test_singapore_triggers_compliance_escalation():
    orch = _run("h_005")  # Yuki Tanaka, Singapore
    assert "escalation" in orch.gates_fired


def test_known_jurisdiction_does_not_escalate():
    orch = _run("h_001")  # Sarah, US
    assert "escalation" not in orch.gates_fired


# --- Invariant: every run surfaces the always-on gates in the right order ----------

def test_core_gate_sequence_present_and_ordered():
    orch = _run("h_001")
    core = [g for g in orch.gates_fired
            if g in {"plan_approval", "30_60_90_signoff", "welcome_message_review"}]
    assert core == ["plan_approval", "30_60_90_signoff", "welcome_message_review"]


# --- Invariant: a malformed profile halts gracefully, never crashes ---------------

def test_malformed_profile_halts_without_crashing():
    orch = _run("test_malformed")
    assert orch.state == "halted_invalid"
    assert orch.gates_fired == []          # never reached a gate
    assert any("start_date" in e for e in orch.events)  # told the user what was wrong


# --- Invariant: two different profiles produce non-identical gate sets -------------

def test_profiles_produce_distinct_routing():
    sarah = _run("h_001").gates_fired
    marcus = _run("h_002").gates_fired
    assert sarah != marcus
