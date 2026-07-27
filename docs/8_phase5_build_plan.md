# Phase 5 Build Plan — Dashboard (HTML + FastAPI)

## Context
Phase 4 is complete: all four agents + the orchestrator run on real GPT-4o, 28 tests green. The dashboard design is signed off (`design/onboarding_assistant_mockup.html`). Decision (2026-06-14): build the real frontend in **HTML/CSS/JS + a thin FastAPI backend**, driven by the real orchestrator. This **drops Streamlit** from the locked stack (flagged change to CLAUDE.md) but keeps FastAPI, which was already locked. The UI replays **cached real agent outputs** for a fast, crash-proof demo, with the HITL gates fully interactive and one **live-run** path to prove it's real (PRD §9 mitigation).

## Components

### 1. Orchestrator generator refactor — `onboarding/orchestrator.py`
The pause/resume engine the gates need over HTTP.
- Extract the body of `run()` into a generator `run_steps()` that `yield`s each `HITLRequest` and receives the `HITLResponse` via `.send()`.
- Add `_emit_gate(request)` generator helper: append to `gates_fired`, `resp = yield request`, `return isinstance(resp, (ApproveResponse, AcknowledgeResponse))`. Call sites use `proceed = yield from self._emit_gate(...)`.
- Keep `run(gate_handler)` as a thin driver looping `next`/`send` over `run_steps()` — so the existing 28 tests pass unchanged.

### 2. Demo cache — `scripts/build_demo_cache.py` → `demo_cache/<hire_id>.json`
- Run each demo profile through the real agents once (auto-approving gates), capturing: `plan`, `plan_summary`, IT / Compliance / Manager-Prep results, welcome draft, `events`, `gates_fired`, and each gate's request payload.
- Backend replays these for instant, reliable demos. Order: **h_001 Sarah, h_002 Marcus** first (the P0 scenarios); h_003 / h_004 / h_005 if smooth.

### 3. View model — `onboarding/view_model.py`
- Pure function: orchestrator state/results → the dashboard "flow" structure the frontend renders (orchestrator band; stages each with `agent`, `status`, `summary`, `reasoning`, optional `gate{type, actions, rationale, payload}`; handoff labels). One source of truth for both cached and live paths.

### 4. FastAPI backend — `onboarding/server.py`
- `GET /api/profiles` → demo profile list.
- `POST /api/run {hire_id, mode}` → create a session, drive `run_steps()` to the first gate (or completion), return the view model + pending gate. `mode = cached` (default) | `live`.
- `POST /api/session/{id}/gate {action, ...}` → resolve the pending gate (`gen.send(response)`), advance to the next gate/completion, return the updated view model.
- `GET /api/session/{id}` → current state.
- Sessions in an in-memory dict (single-user demo; persistence is an explicit non-goal).
- Serves the static frontend at `/`.
- Graceful failure: a malformed profile returns a `halted_invalid` view with a plain-English message — never a 500.

### 5. Frontend — `static/index.html`, `static/app.css`, `static/app.js`
- Port the signed-off mockup into these files. Two views: **Dashboard** + **How it's built**.
- `app.js`: load `/api/profiles`; on profile select → `POST /api/run`; render the flow (orchestrator band, agent stages with color/icon identities, handoff connectors, gate cards); gate buttons → `POST …/gate` → re-render. Keep the agent identities, handoff connectors, and the two HITL shapes (decision gate = 3 actions; alert = 2) from the mockup.
- "How it's built": static diagrams (`docs/diagrams/*.svg`) + design principles.

### 6. Deps, run, tests
- `requirements.txt`: add `fastapi`, `uvicorn[standard]`, `httpx` (for TestClient).
- `README.md`: run instructions (`uvicorn onboarding.server:app`).
- Tests: keep the 28 green; add `tests/test_phase5_generator.py` (step through `run_steps()`) and `tests/test_phase5_api.py` (FastAPI TestClient: run cached Sarah end-to-end, resolve gates, assert states).

## Decisions made solo overnight (for morning review)
- Cached-replay is the default demo path; live-run available via `mode=live`.
- Vanilla JS frontend (no framework / no build step) for reliability and walkthrough legibility.
- In-memory sessions, no persistence (per non-goals).
- Cache Sarah + Marcus first; add the others only if everything is smooth.

## Verification
- `.venv/bin/python -m pytest -q` → all green (28 existing + new).
- Build the cache; start `uvicorn onboarding.server:app` (background); `curl /api/profiles`, `POST /api/run` for h_001, then `POST …/gate` approvals through to `complete`.
- `curl /` → 200 + the dashboard HTML.
- Leave a morning summary in the study-guide session log (`docs/7_…`): what's done, decisions made, what's left.
