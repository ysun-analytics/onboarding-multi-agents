"""
view_model.py — turn the orchestrator's live state into ONE rendering contract.

Why this module exists (the design point worth defending in the interview):
  The frontend should not know about Pydantic models, the OpenAI SDK, or how the
  orchestrator advances. It should receive a single, flat, JSON-serializable
  "view model" describing the flow to draw — an orchestrator band, an ordered list
  of stages, and (at most) one pending gate. Everything the dashboard renders comes
  from here.

Why that matters: we have TWO ways to drive the demo — replaying a cached real run
  (fast, crash-proof) and a genuine live run (proves it's real). If each produced a
  different shape, the frontend would need two code paths. Instead BOTH paths call
  build_view_model() and emit the identical structure. One renderer, two engines.

The structure deliberately mirrors the signed-off mockup
  (design/onboarding_assistant_mockup.html): the Coordinator is an orchestrator
  *band*, not a peer agent; the specialists are stages with reasoning traces; gates
  render inline on the stage that raised them, in one of two shapes (decision = 3
  actions, alert = 2).
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from . import data_loaders as data
from .models import (
    HITLRequest,
    IntroMeetingScheduled,
)

# Which stage a given gate renders on. The frontend reads stage.gate; this map is
# how we route a HITLRequest to the right card.
_GATE_TO_STAGE = {
    "plan_approval": "plan",
    "special_access": "it",
    "escalation": "compliance",
    "30_60_90_signoff": "manager_prep",
    "welcome_message_review": "welcome",
    "readiness_at_risk": "readiness",
}

# Agent identity classes — match the mockup's color/icon system.
_AGENT_CLASS = {
    "coordinator": "coord",
    "it_provisioning": "it",
    "compliance_docs": "comp",
    "manager_prep": "mgr",
}

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_date(iso: Optional[str]) -> Optional[str]:
    """'2026-06-21' -> 'Jun 21, 2026'. Returns the input unchanged if it isn't a
    plain ISO date, so a hallucinated datetime string never crashes the render."""
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
        return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"
    except (ValueError, IndexError):
        return iso


def _gate_shape(gate_type: str) -> str:
    return "alert" if gate_type == "readiness_at_risk" else "decision"


def _gate_actions(gate_type: str) -> List[str]:
    """The two HITL shapes from the spec. Alerts are a status to act on (2 actions);
    decision gates are a judgment to make (3 actions)."""
    if gate_type == "readiness_at_risk":
        return ["acknowledge", "take_action"]
    return ["approve", "edit", "request_changes"]


def _gate_dict(req: HITLRequest) -> dict:
    return {
        "gate_type": req.gate_type,
        "agent": req.agent,
        "summary": req.summary,
        "proposed_decision": req.proposed_decision,
        "rationale": req.rationale,
        "alternatives": req.alternatives or [],
        "shape": _gate_shape(req.gate_type),
        "actions": _gate_actions(req.gate_type),
        "payload": req.payload,
    }


def build_view_model(orch, pending: Optional[HITLRequest] = None) -> dict:
    """Pure read of the orchestrator → the dashboard view model. Never mutates the
    orchestrator; never calls the LLM. Safe to call at any pause point or at the end."""

    # --- the malformed-profile path (Scenario D): fail as a readable card --------
    if orch.state == "halted_invalid":
        return {
            "state": "halted_invalid",
            "ok": False,
            "message": (
                "This profile couldn't be processed because it's missing required "
                "information. Nothing was provisioned. Fix the profile in the HR system "
                "and re-run — no half-finished onboarding was created."
            ),
            "errors": _validation_errors(orch),
            "events": list(orch.events),
            "hire": None,
            "orchestrator": None,
            "stages": [],
            "pending_gate": None,
        }

    profile = getattr(orch, "_profile", None) or (orch.plan.profile if orch.plan else None)
    results = orch.results
    gates_fired = orch.gates_fired
    pending_type = pending.gate_type if pending else None

    def gate_for(stage_id: str) -> Optional[dict]:
        """Return the pending-gate dict if this stage is the one currently awaiting."""
        if pending and _GATE_TO_STAGE.get(pending.gate_type) == stage_id:
            return _gate_dict(pending)
        return None

    def resolved(gate_type: str) -> bool:
        """A gate has been answered if it fired and isn't the one we're paused on."""
        return gate_type in gates_fired and gate_type != pending_type

    stages: List[dict] = []
    stages.append(_plan_stage(orch, profile, gate_for, resolved))
    stages.append(_it_stage(orch, results, gate_for, resolved))
    stages.append(_compliance_stage(orch, results, gate_for, resolved))
    stages.append(_manager_prep_stage(orch, results, gate_for, resolved))
    stages.append(_welcome_stage(orch, results, gate_for, resolved))
    stages.append(_readiness_stage(orch))

    return {
        "state": orch.state,
        "ok": True,
        "hire": _hire_header(profile),
        "orchestrator": _orchestrator_band(orch, profile, pending),
        "stages": stages,
        "pending_gate": _gate_dict(pending) if pending else None,
        "events": list(orch.events),
    }


# ---------------------------------------------------------------------------
# Header + orchestrator band
# ---------------------------------------------------------------------------

def _hire_header(profile) -> Optional[dict]:
    if profile is None:
        return None
    emp = "Full-time" if profile.employment_type == "fte" else "Contractor"
    return {
        "name": profile.full_name,
        "role_title": profile.role_title,
        "team": profile.team.replace("_", " ").title(),
        "location": f"{profile.location.city}, {profile.location.country}",
        "employment": emp,
        "manager": data.get_manager_name(profile.manager_id),
        "start_date": _fmt_date(profile.start_date),
    }


def _orchestrator_band(orch, profile, pending) -> dict:
    """The Coordinator's status line — it's the conductor, not a peer agent."""
    name = profile.full_name.split()[0] if profile else "the new hire"
    waiting = pending is not None
    if orch.state == "complete":
        status = "All agents complete · every gate resolved · onboarding assembled."
    elif waiting:
        status = f"Coordinating {name}'s onboarding · 1 approval waiting for you."
    else:
        status = f"Coordinating {name}'s onboarding."
    return {
        "name": "Onboarding Assistant",
        "agent_class": "coord",
        "status": status,
        "waiting": waiting,
    }


# ---------------------------------------------------------------------------
# Stage builders — each returns {id, agent, agent_class, title, status, summary,
# reasoning, details, gate}. status drives the pill; gate is the inline HITL card.
# ---------------------------------------------------------------------------

def _stage(id, agent, title, status, summary, reasoning=None, details=None, gate=None):
    return {
        "id": id,
        "agent": agent,
        "agent_class": _AGENT_CLASS[agent],
        "title": title,
        "status": status,           # pending | awaiting_approval | complete | scheduled
        "summary": summary,
        "reasoning": reasoning or [],
        "details": details or {},
        "gate": gate,
    }


def _plan_stage(orch, profile, gate_for, resolved) -> dict:
    gate = gate_for("plan")
    if orch.plan is None:
        status, summary = "pending", "Building the consolidated plan…"
    elif gate:
        status = "awaiting_approval"
        summary = "One plan covering all four agents — approve in a single click, not four."
    else:
        status = "complete"
        summary = "One plan covering all four agents — approved in a single click, not four."

    sections = _plan_sections(orch)
    reasoning = []
    if orch.plan_summary is not None:
        reasoning = orch.plan_summary.reasoning.steps
    return _stage(
        "plan", "coordinator", "Consolidated plan", status, summary,
        reasoning=reasoning, details={"sections": sections}, gate=gate,
    )


def _plan_sections(orch) -> List[dict]:
    """The four collapsible rows of the plan card — one per agent, with the gate it
    will trip. Sourced from the deterministic plan (gates) + the LLM summary (prose)."""
    if orch.plan is None:
        return []
    label = {
        "coordinator": "Assistant", "it_provisioning": "IT Provisioning",
        "compliance_docs": "Compliance & Docs", "manager_prep": "Manager Prep",
    }
    # Plain language — no "gate" jargon; the reader is a non-technical coordinator.
    gate_label = {
        "special_access": "You'll approve the special-access request",
        "escalation": "Needs your review (unfamiliar location)",
        "30_60_90_signoff": "You'll review & send it to the manager",
        "welcome_message_review": "Needs your review before sending",
        "plan_approval": "Needs your approval", "readiness_at_risk": "Readiness check",
    }
    summary = orch.plan_summary
    blocks = {
        "it_provisioning": getattr(summary, "it_provisioning", None) if summary else None,
        "compliance_docs": getattr(summary, "compliance_docs", None) if summary else None,
        "manager_prep": getattr(summary, "manager_prep", None) if summary else None,
        "coordinator": getattr(summary, "coordinator", None) if summary else None,
    }
    order = ["it_provisioning", "compliance_docs", "manager_prep", "coordinator"]
    by_agent = {w.agent: w for w in orch.plan.work}
    sections = []
    for agent in order:
        work = by_agent.get(agent)
        if work is None:
            continue
        block = blocks.get(agent)
        text = " ".join(block.actions) if block and block.actions else \
            " ".join(work.anticipated_actions)
        gates = [gate_label.get(g, g) for g in work.anticipated_gates
                 if g not in ("plan_approval", "readiness_at_risk")]
        sections.append({
            "agent": agent,
            "agent_class": _AGENT_CLASS[agent],
            "label": label[agent],
            "text": text,
            "gate": ("⚑ " + "; ".join(gates)) if gates else None,
        })
    return sections


def _it_stage(orch, results, gate_for, resolved) -> dict:
    gate = gate_for("it")
    it = results.get("it_provisioning")
    if it is None:
        return _stage("it", "it_provisioning", "IT Provisioning", "pending",
                      "Waiting on plan approval…")
    held = [r.system for r in it.special_access_requests]
    systems = [s.system for s in it.software_access]
    summary = f"{it.hardware.item} · {', '.join(systems[:4])}"
    if held:
        summary += f" · {', '.join(held)} held for approval"
    status = "awaiting_approval" if gate else "complete"
    details = {
        "hardware": {"item": it.hardware.item, "status": it.hardware.status,
                     "notes": it.hardware.notes},
        "software_access": [{"system": s.system, "access_level": s.access_level,
                             "status": s.status} for s in it.software_access],
        "security_groups": [{"group": g.group, "status": g.status}
                            for g in it.security_groups],
        "special_access_requests": [{"system": r.system, "access": r.requested_access,
                                     "rationale": r.rationale} for r in it.special_access_requests],
        "warnings": it.warnings,
    }
    return _stage("it", "it_provisioning", "IT Provisioning", status, summary,
                  reasoning=it.reasoning.steps, details=details, gate=gate)


def _compliance_stage(orch, results, gate_for, resolved) -> dict:
    gate = gate_for("compliance")
    comp = results.get("compliance_docs")
    if comp is None:
        return _stage("compliance", "compliance_docs", "Compliance & Docs", "pending",
                      "Waiting on plan approval…")
    n = len(comp.required_documents)
    names = ", ".join(d.name for d in comp.required_documents[:6])
    summary = f"{n} document{'s' if n != 1 else ''} · {names}"
    status = "awaiting_approval" if gate else "complete"
    details = {
        "required_documents": [{"name": d.name, "deadline": _fmt_date(d.deadline),
                                "status": d.status, "rationale": d.rationale}
                               for d in comp.required_documents],
        "escalations": [{"reason": e.reason, "proposed_document_set": e.proposed_document_set}
                        for e in comp.escalations],
    }
    return _stage("compliance", "compliance_docs", "Compliance & Docs", status, summary,
                  reasoning=comp.reasoning.steps, details=details, gate=gate)


def _manager_prep_stage(orch, results, gate_for, resolved) -> dict:
    gate = gate_for("manager_prep")
    mp = results.get("manager_prep")
    if mp is None:
        return _stage("manager_prep", "manager_prep", "Manager Prep", "pending",
                      "Waiting on IT's provisioning summary…")
    profile = getattr(orch, "_profile", None) or (orch.plan.profile if orch.plan else None)
    manager_name = data.get_manager_name(profile.manager_id) if profile else "the manager"
    note = results.get("manager_note")
    # The intro outcome + buddy are now FOLDED INTO the cover note prose (the coordinator
    # asked for one note, not three repeating sub-cards). We keep a one-line collapsed
    # summary so the at-a-glance row still says what's inside.
    scheduled = isinstance(mp.intro_meeting, IntroMeetingScheduled)
    intro_txt = (f"intro booked ({_fmt_date(mp.intro_meeting.proposed_time)})" if scheduled
                 else "intro blocked — alternatives proposed")
    summary = (f"Ready to send to {manager_name} · draft 30-60-90 · {intro_txt} · "
               f"suggested buddy {mp.buddy_recommendation.name}")
    status = "awaiting_approval" if gate else "complete"

    # The three discrete actions Manager Prep took, surfaced explicitly so the coordinator
    # can see WHAT the agent did at a glance — not just read it inside the cover-note prose.
    if scheduled:
        intro_action = {
            "label": "Schedule intro meeting with the manager", "status": "done",
            "detail": f"{_fmt_date(mp.intro_meeting.proposed_time)} · {mp.intro_meeting.duration_minutes} min",
        }
    else:
        intro_action = {
            "label": "Schedule intro meeting with the manager", "status": "blocked",
            "detail": "Manager's calendar was full — proposed alternatives for you",
        }
    actions = [
        intro_action,
        {"label": "Identify an onboarding buddy", "status": "done",
         "detail": f"{mp.buddy_recommendation.name} · {mp.buddy_recommendation.tenure_years} yrs (a suggestion)"},
        {"label": "Generate the 30-60-90 onboarding plan", "status": "done",
         "detail": "Draft for the manager to own & customize"},
    ]

    details = {
        "manager_name": manager_name,
        # Lead with WHAT the agent did (the three actions), then the package to send.
        "actions": actions,
        # The cover note — it carries the general message, intro and buddy in prose.
        "note": ({"subject_line": note.subject_line, "body": note.body} if note else None),
        # Then the structured draft 30-60-90 the manager will own and customize…
        "thirty_sixty_ninety": {
            "thirty_days": mp.thirty_sixty_ninety.thirty_days,
            "sixty_days": mp.thirty_sixty_ninety.sixty_days,
            "ninety_days": mp.thirty_sixty_ninety.ninety_days,
        },
        # …and the full prep checklist last.
        "manager_checklist": mp.manager_checklist,
    }
    return _stage("manager_prep", "manager_prep", "Manager Prep", status, summary,
                  reasoning=mp.reasoning.steps, details=details, gate=gate)


def _welcome_stage(orch, results, gate_for, resolved) -> dict:
    gate = gate_for("welcome")
    w = results.get("coordinator_welcome")
    if w is None:
        return _stage("welcome", "coordinator", "Welcome message", "pending",
                      "Drafted once the specialists report back…")
    if w.send_strategy == "send_now":
        send_txt = "Starts within 2 weeks → sends on approval."
    else:
        send_txt = f"Scheduled to send {_fmt_date(w.scheduled_send_date)} (2 weeks before start)."
    summary = f"Personalized note ready. {send_txt}"
    status = "awaiting_approval" if gate else "complete"
    details = {
        "subject_line": w.subject_line, "body": w.body,
        "send_strategy": w.send_strategy,
        "scheduled_send_date": _fmt_date(w.scheduled_send_date),
    }
    return _stage("welcome", "coordinator", "Welcome message", status, summary,
                  reasoning=w.reasoning.steps, details=details, gate=gate)


def _readiness_stage(orch) -> dict:
    """The T-3 safety net. Modeled as a scheduled ALERT, not a decision gate — it's a
    status to act on, not a judgment to approve. This is the gate that catches the
    'no laptop on day one' failure the product exists to prevent."""
    active = orch.state in ("monitoring", "complete")
    summary = ("Runs 3 days before start. Surfaces anything still outstanding — "
               "the 'no laptop on day one' safety net.")
    return _stage("readiness", "coordinator", "Readiness check",
                  "scheduled" if active else "pending", summary)


def _validation_errors(orch) -> List[str]:
    try:
        return orch.validate().errors
    except Exception:
        return []
