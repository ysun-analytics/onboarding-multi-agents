"""
build_demo_cache.py — run the REAL agents once per demo profile and freeze the result.

Why cache at all? The live demo calls GPT-4o several times per hire (plan summary, IT,
compliance, manager prep, manager cover note, welcome — plus each agent's internal tool
loop). That's
20-40 seconds and a non-zero chance of a transient API hiccup mid-walkthrough. For a
45-minute interview we want the dashboard to feel instant and never fail. So we run
each profile through the real pipeline ONCE, here, and snapshot every screen the
dashboard will show. The server replays those snapshots.

Crucially this is REAL agent output, captured — not hand-written fixtures. The live
path still exists (server `mode=live`) to prove it on demand. Cache = reliability;
live = proof. (PRD §9 mitigation.)

What we snapshot: the view model at every human-gate pause, plus the final completed
view model. The server steps through them as the coordinator clicks each gate.

Run:  .venv/bin/python scripts/build_demo_cache.py            # default demo set
      .venv/bin/python scripts/build_demo_cache.py h_001 h_002
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the project root importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onboarding.config import has_api_key  # noqa: E402
from onboarding.models import AcknowledgeResponse, ApproveResponse  # noqa: E402
from onboarding.orchestrator import Orchestrator  # noqa: E402
from onboarding.view_model import build_view_model  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "demo_cache"

# Order matters: the P0 scenarios first. Sarah is the happy path; Marcus is the
# "same agents, different reasoning" hero moment.
DEFAULT_PROFILES = ["h_001", "h_002", "h_003", "h_005"]


def _auto_response(request):
    """Approve every decision gate, acknowledge every alert — the happy path the
    cache replays. The live path is where a human can edit / request changes."""
    if request.gate_type == "readiness_at_risk":
        return AcknowledgeResponse(action="acknowledge")
    return ApproveResponse(action="approve")


def build_one(hire_id: str) -> dict:
    """Drive the real generator, snapshotting the view model at each pause."""
    orch = Orchestrator(hire_id)
    gen = orch.run_steps()
    steps = []
    try:
        request = next(gen)                       # advance to the first gate
        while True:
            steps.append(build_view_model(orch, pending=request))  # snapshot the pause
            response = _auto_response(request)
            request = gen.send(response)           # answer it, advance to the next
    except StopIteration:
        pass
    final = build_view_model(orch, pending=None)   # completed (or halted) screen
    return {"hire_id": hire_id, "steps": steps, "final": final}


def main(profile_ids):
    if not has_api_key():
        print("ERROR: no OPENAI_API_KEY found in .env — cannot run the real agents.")
        sys.exit(1)
    CACHE_DIR.mkdir(exist_ok=True)
    for hire_id in profile_ids:
        print(f"  running {hire_id} through the real agents… ", end="", flush=True)
        try:
            cache = build_one(hire_id)
        except Exception as exc:  # noqa: BLE001 — a script; surface and continue
            print(f"FAILED ({type(exc).__name__}: {exc})")
            continue
        out = CACHE_DIR / f"{hire_id}.json"
        out.write_text(json.dumps(cache, indent=2))
        n_gates = len(cache["steps"])
        print(f"ok · {n_gates} gate(s) · {cache['final']['state']} → {out.name}")


if __name__ == "__main__":
    ids = sys.argv[1:] or DEFAULT_PROFILES
    print(f"Building demo cache for: {', '.join(ids)}")
    main(ids)
    print("Done.")
