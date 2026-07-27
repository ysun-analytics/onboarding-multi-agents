"""
test_phase5_api.py — guard the FastAPI dashboard backend end-to-end.

These run against the CACHED demo runs (committed in demo_cache/), so they need no
API key and are fast + deterministic. They protect the demo invariants the
interviewer will actually click through:
  - a hire runs from plan approval to complete, one gate at a time;
  - the malformed profile fails GRACEFULLY (a readable view, never a 500);
  - Sarah and Marcus produce visibly DIFFERENT flows (the "same agents, different
    reasoning" hero moment).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from onboarding.server import app

client = TestClient(app)


def _run(hire_id, mode="cached"):
    return client.post("/api/run", json={"hire_id": hire_id, "mode": mode}).json()


def _approve(session_id):
    return client.post(f"/api/session/{session_id}/gate", json={"action": "approve"}).json()


def _gate_sequence(hire_id):
    """Click Approve through a cached run, collecting the gate types seen."""
    r = _run(hire_id)
    sid, view = r["session_id"], r["view"]
    seq = []
    while view.get("pending_gate"):
        seq.append(view["pending_gate"]["gate_type"])
        view = _approve(sid)["view"]
    return seq, view


def test_profiles_endpoint_lists_cached_hires():
    profs = client.get("/api/profiles").json()["profiles"]
    ids = {p["hire_id"] for p in profs}
    assert {"h_001", "h_002"}.issubset(ids)
    sarah = next(p for p in profs if p["hire_id"] == "h_001")
    assert sarah["cached"] is True


def test_sarah_runs_to_complete_one_gate_at_a_time():
    seq, final = _gate_sequence("h_001")
    assert seq == [
        "plan_approval", "special_access", "30_60_90_signoff", "welcome_message_review",
    ]
    assert final["state"] == "complete"
    assert final["pending_gate"] is None


def test_exactly_one_gate_is_active_at_each_pause():
    r = _run("h_001")
    sid, view = r["session_id"], r["view"]
    while view.get("pending_gate"):
        active = [s for s in view["stages"] if s.get("gate")]
        assert len(active) == 1, "exactly one stage should carry the pending gate"
        assert active[0]["gate"]["gate_type"] == view["pending_gate"]["gate_type"]
        view = _approve(sid)["view"]


def test_malformed_profile_fails_gracefully():
    r = _run("test_malformed")
    view = r["view"]
    assert view["ok"] is False
    assert view["state"] == "halted_invalid"
    assert "message" in view and view["message"]
    # never a 500 — the dashboard stays up


def test_unknown_session_returns_readable_message_not_crash():
    r = client.post("/api/session/does_not_exist/gate", json={"action": "approve"})
    assert r.status_code == 200
    assert r.json()["state"] == "expired"


def test_sarah_and_marcus_produce_different_flows():
    """The hero moment: same four agents, visibly different reasoning. Sarah (Sr Eng,
    US FTE) trips an AWS special-access gate; Marcus (AE, UK contractor) does not."""
    sarah_seq, sarah_final = _gate_sequence("h_001")
    marcus_seq, marcus_final = _gate_sequence("h_002")

    assert "special_access" in sarah_seq
    assert "special_access" not in marcus_seq

    def it_summary(view):
        return next(s["summary"] for s in view["stages"] if s["id"] == "it")
    assert it_summary(sarah_final) != it_summary(marcus_final)

    def doc_names(view):
        comp = next(s for s in view["stages"] if s["id"] == "compliance")
        return [d["name"] for d in comp["details"]["required_documents"]]
    # UK contractor docs differ from US FTE docs (IR35 vs I-9, etc.)
    assert doc_names(sarah_final) != doc_names(marcus_final)


@pytest.mark.parametrize("hire_id", ["h_001", "h_002", "h_003", "h_005"])
def test_each_demo_profile_completes(hire_id):
    _, final = _gate_sequence(hire_id)
    assert final["state"] == "complete"
