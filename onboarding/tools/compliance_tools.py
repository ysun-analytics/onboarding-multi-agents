"""
compliance_tools.py — the Compliance & Docs Agent's four tools.

Design point (this is the "facts vs. judgment" line, applied deliberately):

  The required-document set for a given role × location × employment-type is a
  DETERMINISTIC lookup against the compliance catalog, and each document's DEADLINE is
  a DETERMINISTIC date computation (start_date + offset). So both live in a tool, not
  in the LLM. We learned in Phase 3 that letting the model choose mechanical facts
  causes drift — so here we never let it. The tool returns authoritative documents with
  computed deadlines; the agent's job is the genuine judgment: escalating jurisdictions
  we have no rules for, and explaining the combination in plain English.

  Why this is the right split: compliance is the domain where "I don't know" must reach
  a human, not get smoothed over. A rules engine would bury that; an agent surfaces it
  as an explicit escalation with a reasoning trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List

from agents import RunContextWrapper, function_tool

from .. import data_loaders as data
from ..models import NewHireProfile


@dataclass
class ComplianceContext:
    """Per-hire state. Carries the profile so tools can compute deadlines from the real
    start date without the LLM passing (or fabricating) it."""

    profile: NewHireProfile
    ledger: List[Dict[str, Any]] = field(default_factory=list)


def _compute_deadline(start_date: str, offset_days: int) -> str:
    """start_date + offset_days, as an ISO date string. Deterministic — a fact, not a
    judgment, so it's computed here and never left to the model."""
    start = date.fromisoformat(start_date)
    return (start + timedelta(days=offset_days)).isoformat()


@function_tool
def get_required_documents(
    ctx: RunContextWrapper[ComplianceContext],
    role_family: str,
    country: str,
    employment_type: str,
) -> dict:
    """Look up the authoritative set of documents this hire must complete, with each
    deadline already computed from their start date. Call this first.

    Returns a dict with:
      - documents: list of {name, category, deadline (ISO), rationale, status}
      - jurisdiction_known: bool — False if we have no rule set for this country
      - closest_known_jurisdiction: a suggested fallback when jurisdiction is unknown

    Args:
        role_family: e.g. "engineering", "sales", "executive".
        country: the hire's country code, e.g. "US", "UK", "SG".
        employment_type: "fte" or "contractor".
    """
    profile = ctx.context.profile
    catalog = data._load_json("compliance_catalog.json")
    known = country in catalog["known_jurisdictions"]

    documents: List[dict] = []
    if known:
        combo_key = f"{country}_{employment_type}"
        base = catalog["rules_by_combination"].get(combo_key, {}).get("required_documents", [])
        for doc in base:
            documents.append({
                "name": doc["name"],
                "category": doc["category"],
                "deadline": _compute_deadline(profile.start_date, doc["deadline_offset_days"]),
                "rationale": doc["rationale"],
                "status": "not_started",
            })
        # Deterministic add-ons: executive hires and sensitive-data roles get extra docs.
        if role_family == "executive":
            _add(documents, catalog["additions"]["executive_addons"], profile.start_date)
        if role_family in catalog["sensitive_data_role_families"]:
            _add(documents, catalog["additions"]["sensitive_data_role_addons"], profile.start_date)

    result = {
        "documents": documents,
        "jurisdiction_known": known,
        "closest_known_jurisdiction": "US" if not known else None,
    }
    ctx.context.ledger.append({"action": "get_required_documents", "count": len(documents)})
    return result


def _add(documents: List[dict], addons: List[dict], start_date: str) -> None:
    for doc in addons:
        documents.append({
            "name": doc["name"],
            "category": doc["category"],
            "deadline": _compute_deadline(start_date, doc["deadline_offset_days"]),
            "rationale": doc["rationale"],
            "status": "not_started",
        })


@function_tool
def check_document_status(ctx: RunContextWrapper[ComplianceContext]) -> dict:
    """Return the current completion status of this hire's documents. In the demo all
    documents start as 'not_started'; in production this reads the e-signature system."""
    return {"hire_id": ctx.context.profile.hire_id, "documents": ctx.context.ledger}


@function_tool
def send_reminder(ctx: RunContextWrapper[ComplianceContext], document_name: str) -> dict:
    """Send the new hire a reminder to complete a specific outstanding document.

    Args:
        document_name: The document to remind about, e.g. "Form I-9".
    """
    record = {"action": "send_reminder", "document": document_name, "sent": True}
    ctx.context.ledger.append(record)
    return record


@function_tool
def flag_overdue_documents(ctx: RunContextWrapper[ComplianceContext]) -> dict:
    """Return any documents whose deadline has passed without completion. In the demo
    nothing is overdue yet (we're determining docs at hire time); this exists for the
    ongoing-tracking part of the lifecycle."""
    return {"hire_id": ctx.context.profile.hire_id, "overdue": []}


COMPLIANCE_TOOLS = [
    get_required_documents,
    check_document_status,
    send_reminder,
    flag_overdue_documents,
]
