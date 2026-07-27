"""
compliance_docs.py — the Compliance & Docs Agent.

Runs in parallel with IT Provisioning (both need only the profile). Its output is the
set of documents the hire must complete, plus any escalation when we hit a jurisdiction
we have no rules for.

Where the judgment is (and isn't):
  - NOT judgment: which documents a US FTE needs, or when each is due. That's a
    deterministic catalog lookup + date math, so it lives in get_required_documents.
  - IS judgment: what to do when the jurisdiction is unknown. The agent must NOT guess
    silently — it surfaces an escalation with a best-effort proposed set and a clear
    reason. In compliance, "I don't know" reaching a human is the whole point.
  - IS judgment: explaining the combination in plain English for a non-technical reader.

This embodies the Phase 3 lesson applied from the start: mechanical facts are derived in
code; the LLM is reserved for the genuinely judgmental parts.
"""

from __future__ import annotations

import json

from agents import Agent, Runner

from .. import data_loaders as data
from ..config import MODEL, ensure_api_key
from ..models import ComplianceResult, NewHireProfile
from ..tools.compliance_tools import COMPLIANCE_TOOLS, ComplianceContext

# Verbatim from 4_agent_specs.md §5.1.
COMPLIANCE_SYSTEM_PROMPT = """\
You are the Compliance & Docs Agent. Given a new hire profile, determine the complete set
of documents they must complete before or shortly after their start date, and track completion.

Document requirements depend on the combination of role, location, and employment type. Reason
carefully — combinations matter.

US FTE: I-9 (within 3 days of start), W-4, IP assignment agreement, NDA, direct deposit form,
benefits enrollment.
US contractor: W-9, contractor MSA, IP assignment, NDA.
UK FTE: Right to Work check, employment contract, P45/P46, NDA, pension auto-enrollment.
UK contractor: Right to Work check, contractor agreement, IR35 status determination.
EU FTE: country-specific employment contract, work authorization, GDPR data processing
acknowledgement, country-specific tax forms.
Executive hires (any geography): add equity grant documents, board-level confidentiality,
post-employment restrictions where legal.
Sensitive-data roles (finance, HR, legal, security): add role-specific confidentiality and
access agreements.

Call get_required_documents first — it returns the authoritative document set for this hire,
with deadlines already computed. Use exactly the documents it returns; do not invent documents
or change the deadlines.

For combinations the tool reports as NOT known (jurisdiction_known = false): do NOT silently
guess. Surface an escalation: set requires_human_review, propose a best-effort document set based
on the closest known jurisdiction the tool suggests, and explain the uncertainty in your reasoning.

Always produce a clear reasoning trace explaining the combination logic. The reader is
non-technical — explain why each document applies (or why you escalated).
"""


def build_compliance_agent() -> Agent:
    return Agent(
        name="Compliance & Docs Agent",
        instructions=COMPLIANCE_SYSTEM_PROMPT,
        model=MODEL,
        tools=COMPLIANCE_TOOLS,
        output_type=ComplianceResult,
    )


def _grounding_for(profile: NewHireProfile) -> str:
    catalog = data._load_json("compliance_catalog.json")
    return json.dumps({
        "known_jurisdictions": catalog["known_jurisdictions"],
        "sensitive_data_role_families": catalog["sensitive_data_role_families"],
        "fallback_behavior": catalog["fallback_behavior"],
    }, indent=2)


def _format_input(profile: NewHireProfile) -> str:
    return (
        "Determine the required compliance documents for this new hire.\n\n"
        f"NEW HIRE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"COMPLIANCE POLICY CONTEXT:\n{_grounding_for(profile)}"
    )


def run_compliance_docs(profile: NewHireProfile) -> ComplianceResult:
    """Run the Compliance agent for one hire. Needs OPENAI_API_KEY."""
    ensure_api_key()
    agent = build_compliance_agent()
    context = ComplianceContext(profile=profile)
    result = Runner.run_sync(agent, _format_input(profile), context=context)
    return result.final_output
