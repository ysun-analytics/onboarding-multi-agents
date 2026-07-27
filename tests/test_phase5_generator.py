"""
test_phase5_generator.py — guard the pause/resume engine the dashboard depends on.

These tests protect the refactor that turned run() into a generator (run_steps). If a
future prompt change reorders the flow or drops a gate, these fail loudly — the
dashboard's whole interaction model is "drive the generator one gate at a time," so
the gate SEQUENCE is a demo invariant.

They use deterministic fake agents (no LLM, no key) so they run in milliseconds.
"""

from __future__ import annotations

from onboarding.models import (
    ApproveResponse,
    HITLRequest,
    RequestChangesResponse,
)
from onboarding.orchestrator import Orchestrator
from tests.fakes import (
    fake_compliance_runner,
    fake_it_runner,
    fake_manager_note_runner,
    fake_manager_prep_runner,
    fake_plan_summary_runner,
    fake_welcome_runner,
)


def _orch(hire_id="h_001"):
    return Orchestrator(
        hire_id,
        it_runner=fake_it_runner,
        compliance_runner=fake_compliance_runner,
        manager_prep_runner=fake_manager_prep_runner,
        plan_summary_runner=fake_plan_summary_runner,
        welcome_runner=fake_welcome_runner,
        manager_note_runner=fake_manager_note_runner,
    )


def _drive(orch, answer=lambda req: ApproveResponse(action="approve")):
    """Step the generator to completion, collecting the gates it yields."""
    gates = []
    gen = orch.run_steps()
    try:
        req = next(gen)
        while True:
            gates.append(req)
            req = gen.send(answer(req))
    except StopIteration:
        pass
    return gates


def test_run_steps_yields_hitl_requests():
    gates = _drive(_orch())
    assert gates, "expected at least one gate"
    assert all(isinstance(g, HITLRequest) for g in gates)


def test_engineer_gate_sequence_is_stable():
    """Sarah (Sr Eng, US FTE) trips: plan, AWS special access, sign-off, welcome."""
    gates = [g.gate_type for g in _drive(_orch("h_001"))]
    assert gates == [
        "plan_approval", "special_access", "30_60_90_signoff", "welcome_message_review",
    ]


def test_generator_completes_and_sets_state():
    orch = _orch()
    _drive(orch)
    assert orch.state == "complete"


def test_gates_fired_is_recorded_in_order():
    orch = _orch()
    gates = _drive(orch)
    assert orch.gates_fired == [g.gate_type for g in gates]


def test_non_approval_halts_the_flow():
    """Request-changes on the FIRST gate (plan approval) stops everything — no agent
    runs, no further gates surface. Proves _emit_gate's proceed/stop contract."""
    orch = _orch()
    answer = lambda req: RequestChangesResponse(action="request_changes", feedback="redo")
    gates = _drive(orch, answer=answer)
    assert [g.gate_type for g in gates] == ["plan_approval"]
    assert orch.state != "complete"
    assert "it_provisioning" not in orch.results


def test_run_driver_still_works():
    """The synchronous run() driver (used by tests + the cache builder) must remain a
    thin loop over run_steps — i.e. the legacy entry point keeps working."""
    orch = _orch()
    orch.run(lambda req: ApproveResponse(action="approve"))
    assert orch.state == "complete"
    assert "manager_prep" in orch.results
