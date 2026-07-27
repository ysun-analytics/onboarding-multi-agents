"""
server.py — the thin FastAPI backend behind the dashboard.

Thin is the point. All the IP lives in the orchestrator, the agents, and the typed
contracts. This file is just the seam between an HTTP request (a button click in the
browser) and the orchestrator's pause/resume generator. It holds NO business logic —
it routes requests to one of two drivers:

  cached  (default) — replay a frozen real run from demo_cache/. Instant, never calls
                      the API, never fails mid-walkthrough. This is what the demo uses.
  live              — drive the REAL generator: next() to the first gate, hand it to
                      the browser, send() the human's answer back when they click.
                      Proves the cached runs are genuine, on demand.

Both produce the identical view-model shape (onboarding/view_model.py), so the
frontend has ONE render path regardless of which engine answered.

Sessions live in an in-memory dict. Persistence is an explicit non-goal — this is a
single-operator demo, not a multi-tenant service. (CLAUDE.md: don't build production
scaffolding that doesn't serve a demo invariant.)

Run:  .venv/bin/python -m uvicorn onboarding.server:app --reload
      (use `python -m uvicorn`, not `.venv/bin/uvicorn` — the space in this folder's path
       makes the bare launcher run under system Python, where the `agents` SDK is missing,
       so "live run" fails with ImportError while cached mode still works.)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import data_loaders as data
from .config import has_api_key
from .models import (
    AcknowledgeResponse,
    ApproveResponse,
    DenyResponse,
    EditResponse,
    RequestChangesResponse,
    TakeActionResponse,
)
from .orchestrator import Orchestrator
from .view_model import build_view_model

_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _ROOT / "demo_cache"
_STATIC_DIR = _ROOT / "static"
_DIAGRAMS_DIR = _ROOT / "docs" / "diagrams"

app = FastAPI(title="Onboarding Coordinator")


@app.middleware("http")
async def no_cache_assets(request, call_next):
    """Tell the browser never to cache the frontend assets. Without this, editing
    app.css / app.js during the build leaves the browser showing a stale copy — which
    looks like a broken layout (e.g. CSS-less giant SVGs) even though the files on disk
    are correct. Fine for a localhost demo; you'd cache aggressively in production."""
    response = await call_next(request)
    if request.url.path.startswith(("/static", "/diagrams")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

# session_id -> session state. A cached session is a frozen list of screens; a live
# session holds the running generator so we can resume it on the next click.
_SESSIONS: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class RunBody(BaseModel):
    hire_id: str
    mode: str = "cached"  # "cached" | "live"


class GateBody(BaseModel):
    action: str                        # approve | deny | edit | request_changes | acknowledge | take_action
    edited_payload: Optional[dict] = None
    feedback: Optional[str] = None
    coordinator_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@app.get("/api/profiles")
def list_profiles():
    """The demo roster for the picker. We expose only the profiles we have a cached
    run for (plus a flag), so the dashboard never offers a hire it can't render fast.
    The malformed fixture is included so the graceful-failure path is demoable."""
    out = []
    for hire_id in data.list_profile_ids():
        try:
            p = data.get_profile(hire_id)
            label = f"{p.full_name} — {p.role_title} · {p.location.city} · " \
                    f"{'FTE' if p.employment_type == 'fte' else 'Contractor'}"
            out.append({
                "hire_id": hire_id, "name": p.full_name, "role_title": p.role_title,
                "label": label, "cached": (_CACHE_DIR / f"{hire_id}.json").exists(),
                "valid": True,
            })
        except Exception:
            # Malformed profile (Scenario D): list it so it can be demoed, flagged.
            out.append({
                "hire_id": hire_id, "name": hire_id, "role_title": "(malformed profile)",
                "label": f"{hire_id} — malformed (graceful-failure demo)",
                "cached": False, "valid": False,
            })
    return {"profiles": out}


# ---------------------------------------------------------------------------
# Run + resume
# ---------------------------------------------------------------------------

@app.post("/api/run")
def run(body: RunBody):
    session_id = uuid.uuid4().hex[:12]
    mode = body.mode if body.mode in ("cached", "live") else "cached"

    # Fall back to live if asked for cached but no cache exists (e.g. malformed).
    if mode == "cached" and not (_CACHE_DIR / f"{body.hire_id}.json").exists():
        mode = "live"

    try:
        if mode == "cached":
            view = _start_cached(session_id, body.hire_id)
        else:
            view = _start_live(session_id, body.hire_id)
    except Exception as exc:  # noqa: BLE001 — never 500 the dashboard
        return JSONResponse(_error_view(body.hire_id, exc), status_code=200)

    return {"session_id": session_id, "mode": mode, "view": view}


@app.post("/api/session/{session_id}/gate")
def resolve_gate(session_id: str, body: GateBody):
    sess = _SESSIONS.get(session_id)
    if sess is None:
        return JSONResponse(
            {"ok": False, "state": "expired",
             "message": "This session expired. Pick the hire again to restart."},
            status_code=200,
        )
    try:
        if sess["mode"] == "cached":
            view = _advance_cached(sess, body)
        else:
            view = _advance_live(sess, body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(_error_view(sess["hire_id"], exc), status_code=200)
    return {"session_id": session_id, "mode": sess["mode"], "view": view}


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    sess = _SESSIONS.get(session_id)
    if sess is None:
        return JSONResponse(
            {"ok": False, "state": "expired",
             "message": "This session expired. Pick the hire again to restart."},
            status_code=200,
        )
    return {"session_id": session_id, "mode": sess["mode"], "view": sess["last_view"]}


# ---------------------------------------------------------------------------
# Cached driver — replay frozen real screens
# ---------------------------------------------------------------------------

def _start_cached(session_id: str, hire_id: str) -> dict:
    cache = json.loads((_CACHE_DIR / f"{hire_id}.json").read_text())
    steps = cache["steps"]
    view = steps[0] if steps else cache["final"]
    _SESSIONS[session_id] = {
        "mode": "cached", "hire_id": hire_id, "cache": cache,
        "step_index": 0, "last_view": view,
    }
    return view


def _advance_cached(sess: dict, body: GateBody) -> dict:
    """Advance to the next frozen screen. In cached mode every action advances — the
    cache replays the approved happy path. (Genuine edit / request_changes branching
    is what `mode=live` is for.)"""
    steps = sess["cache"]["steps"]
    sess["step_index"] += 1
    i = sess["step_index"]
    view = steps[i] if i < len(steps) else sess["cache"]["final"]
    sess["last_view"] = view
    return view


# ---------------------------------------------------------------------------
# Live driver — drive the real generator across HTTP requests
# ---------------------------------------------------------------------------

def _start_live(session_id: str, hire_id: str) -> dict:
    if not has_api_key():
        raise RuntimeError("Live mode needs OPENAI_API_KEY in .env.")
    orch = Orchestrator(hire_id)
    gen = orch.run_steps()
    pending = _next_or_none(gen)
    view = build_view_model(orch, pending=pending)
    _SESSIONS[session_id] = {
        "mode": "live", "hire_id": hire_id, "orch": orch, "gen": gen,
        "pending": pending, "last_view": view,
    }
    return view


def _advance_live(sess: dict, body: GateBody) -> dict:
    pending = sess["pending"]
    if pending is None:                       # already finished — nothing to resolve
        return sess["last_view"]
    response = _to_response(body)
    gen, orch = sess["gen"], sess["orch"]
    try:
        sess["pending"] = gen.send(response)
    except StopIteration:
        sess["pending"] = None
    view = build_view_model(orch, pending=sess["pending"])
    sess["last_view"] = view
    return view


def _next_or_none(gen):
    try:
        return next(gen)
    except StopIteration:
        return None


def _to_response(body: GateBody):
    """Map a button click to the typed HITLResponse the orchestrator expects.
    approve/acknowledge proceed; edit/request_changes are real responses that (in the
    current revision semantics) halt the flow for a human to revise."""
    a = body.action
    if a == "approve":
        return ApproveResponse(action="approve", coordinator_note=body.coordinator_note)
    if a == "deny":
        return DenyResponse(action="deny", coordinator_note=body.coordinator_note)
    if a == "acknowledge":
        return AcknowledgeResponse(action="acknowledge", coordinator_note=body.coordinator_note)
    if a == "edit":
        return EditResponse(action="edit", edited_payload=body.edited_payload or {},
                            coordinator_note=body.coordinator_note)
    if a == "request_changes":
        return RequestChangesResponse(action="request_changes",
                                      feedback=body.feedback or "Please revise.")
    if a == "take_action":
        return TakeActionResponse(action="take_action", target_task_id="readiness")
    return ApproveResponse(action="approve")


# ---------------------------------------------------------------------------
# Graceful failure — a readable card, never a stack trace (CLAUDE.md invariant)
# ---------------------------------------------------------------------------

def _error_view(hire_id: str, exc: Exception) -> dict:
    return {
        "session_id": None, "mode": "error",
        "view": {
            "ok": False, "state": "error", "hire": None, "orchestrator": None,
            "stages": [], "pending_gate": None, "events": [],
            "message": (
                f"Something went wrong starting onboarding for {hire_id}. "
                "Nothing was provisioned. You can try again, or switch to cached mode. "
                f"(Details for the developer: {type(exc).__name__})"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(_STATIC_DIR / "index.html")


# Mount static assets (css/js) + the architecture diagrams for "How it's built".
# Kept last so they don't shadow the API routes.
if _DIAGRAMS_DIR.exists():
    app.mount("/diagrams", StaticFiles(directory=str(_DIAGRAMS_DIR)), name="diagrams")
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
