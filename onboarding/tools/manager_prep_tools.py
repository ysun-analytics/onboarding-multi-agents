"""
manager_prep_tools.py — the Manager Prep Agent's four tools.

Note what is and isn't a tool here — it's the cleanest illustration of the project's
core principle:

  - check_calendar / schedule_meeting / find_onboarding_buddy / send_manager_checklist
    are tools, because they're mechanical actions or data fetches (read the calendar,
    book a slot, list teammates, send a checklist).

  - The 30-60-90 plan is NOT a tool, even though the spec originally listed one. Drafting
    a tailored 30-60-90 is the judgment — the entire reason Manager Prep is an agent. So
    the agent writes it directly into its structured output. Making it a "tool" would
    imply it's a deterministic action, which is exactly backwards.

Facts-vs-judgment, applied:
  - find_onboarding_buddy returns CANDIDATES (a fact from the org roster). The agent picks
    one and writes the rationale (judgment). The spec calls this out explicitly: buddy
    data lives in a tool because it depends on org data the LLM doesn't have; the choice
    and the why are the agent's.
  - check_calendar returns real free slots (a fact). Whether to schedule or escalate when
    there are none is the agent's judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents import RunContextWrapper, function_tool

from .. import data_loaders as data
from ..models import NewHireProfile, ProvisioningSummary


@dataclass
class ManagerPrepContext:
    """Per-hire state for a Manager Prep run. force_empty_calendar drives the Scenario C
    edge case (manager fully booked) without mutating the mock data."""

    profile: NewHireProfile
    provisioning_summary: ProvisioningSummary
    force_empty_calendar: bool = False
    ledger: List[Dict[str, Any]] = field(default_factory=list)


@function_tool
def check_calendar(ctx: RunContextWrapper[ManagerPrepContext]) -> dict:
    """Return the hiring manager's free meeting slots during the new hire's first week.
    An empty list means the manager is fully booked — in that case you must escalate
    rather than schedule."""
    if ctx.context.force_empty_calendar:
        free_slots: List[str] = []
    else:
        free_slots = data.get_free_slots(ctx.context.profile.manager_id)
    ctx.context.ledger.append({"action": "check_calendar", "free_count": len(free_slots)})
    return {"manager_id": ctx.context.profile.manager_id, "free_slots": free_slots}


@function_tool
def schedule_meeting(
    ctx: RunContextWrapper[ManagerPrepContext], slot_start: str, duration_minutes: int
) -> dict:
    """Book the manager↔new-hire intro meeting in a chosen free slot. Only call this
    when check_calendar returned at least one free slot.

    Args:
        slot_start: The start time to book, copied from check_calendar's free_slots
            (ISO 8601, e.g. "2026-06-22T14:00").
        duration_minutes: Meeting length, typically 30.
    """
    meeting_id = f"MTG-{ctx.context.profile.hire_id}-{len(ctx.context.ledger) + 1:02d}"
    record = {
        "action": "schedule_meeting", "meeting_id": meeting_id,
        "slot_start": slot_start, "duration_minutes": duration_minutes, "status": "scheduled",
    }
    ctx.context.ledger.append(record)
    return record


@function_tool
def find_onboarding_buddy(ctx: RunContextWrapper[ManagerPrepContext]) -> dict:
    """Return candidate onboarding buddies from the new hire's team. Excludes the hiring
    manager and any other managers (never assign the manager or skip-level as buddy). You
    choose the best candidate and explain why — consider tenure (1-3 years is the sweet
    spot), skill overlap with the new hire, and calendar load."""
    profile = ctx.context.profile
    candidates = []
    for member in data.get_team_members(profile.team):
        if member["is_manager"] or member["user_id"] == profile.manager_id:
            continue
        candidates.append({
            "name": member["full_name"],
            "role_title": member["role_title"],
            "tenure_years": member["tenure_years"],
            "expertise": member.get("expertise", []),
            "calendar_load": member.get("calendar_load", "unknown"),
        })
    ctx.context.ledger.append({"action": "find_onboarding_buddy", "candidate_count": len(candidates)})
    return {"team": profile.team, "candidates": candidates}


@function_tool
def send_manager_checklist(
    ctx: RunContextWrapper[ManagerPrepContext], checklist: List[str]
) -> dict:
    """Send the hiring manager their pre-start prep checklist.

    Args:
        checklist: The checklist items you composed for the manager.
    """
    record = {"action": "send_manager_checklist", "items": len(checklist), "sent": True}
    ctx.context.ledger.append(record)
    return record


MANAGER_PREP_TOOLS = [
    check_calendar,
    schedule_meeting,
    find_onboarding_buddy,
    send_manager_checklist,
]
