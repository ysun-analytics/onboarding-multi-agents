"""
it_provisioning.py — the IT Provisioning Agent (our first real LLM agent).

This is the integration milestone for the build: it proves the OpenAI Agents SDK
setup end-to-end — tool calling + structured output + the Coordinator→IT→Coordinator
handoff. We built IT first on purpose: of the four agents it carries the LIGHTEST
judgment load (provisioning is fairly rule-driven), so it's the cleanest place to
validate the plumbing before we tackle the heavier-judgment agents (Compliance's
combinatorics, Manager Prep's 30-60-90 drafting) in Phase 4.

Design notes for the interview:

- "agents reason, tools execute" in practice: the deterministic facts (which laptop
  for which role, which systems exist, shipping lead times) live in the catalog and
  are handed to the agent as GROUNDING. The agent's actual job is the judgment the
  catalog can't encode cleanly: applying contractor restrictions, flagging special
  access for human approval, warning when international shipping won't beat the start
  date, and writing the plain-English rationale the non-technical coordinator reads.

- GROUNDING (why we inject the catalog into the prompt): an ungrounded LLM will invent
  plausible-but-wrong system names ("I added her to Jira" when we use Linear). We hand
  the agent the exact catalog slice for this hire's role, and the prompt forbids
  inventing systems. This is retrieval-augmented prompting in miniature — reason over
  provided facts, don't free-associate.

- output_type=ProvisioningResult forces the model to return our typed contract, not
  prose. The SDK validates it against the Pydantic model before we ever see it.
"""

from __future__ import annotations

import json

from agents import Agent, Runner

from .. import data_loaders as data
from ..config import MODEL, ensure_api_key
from ..models import NewHireProfile, ProvisioningResult
from ..tools.it_tools import IT_TOOLS, ProvisioningContext

# The system prompt is lifted verbatim from 4_agent_specs.md §3.1 — keeping code and
# spec in lockstep so what Yuyan studies is what actually runs.
IT_SYSTEM_PROMPT = """\
You are the IT Provisioning Agent for a mid-market company's onboarding system.

Your job: given a new hire profile, decide what hardware, software, system access, and
security group memberships they need, then execute that provisioning by calling your tools.

How to think about provisioning:
- ENGINEERING roles: MacBook Pro, GitHub Enterprise, IDE licenses, role-appropriate Slack
  channels, dev tools (CI, observability, error tracking). Senior engineers often need read
  access to cloud consoles for debugging.
- SALES roles: standard laptop, Salesforce, Gong, Outreach, sales-team Slack channels.
  Account Executives need territory/quota tooling.
- OPERATIONS / FINANCE: standard laptop, role-specific SaaS (HRIS for HR, NetSuite for finance).
- EXECUTIVES: elevated provisioning, may require executive admin involvement.

Adjust by employment type:
- CONTRACTORS: limited access. No admin rights. No production system access. Time-bounded
  credentials. No equity-tracking systems.
- FTE: full standard provisioning per role.

Adjust by location:
- Hardware shipping: international hires may need 5-10 business days of lead time. Flag if the
  start date is too close.
- Regional accounts: create accounts in the appropriate regional tenant (EU vs US data residency).

FLAG FOR HUMAN APPROVAL (call request_special_access, do NOT auto-provision) anything involving:
- Cloud credentials beyond read-only (AWS, GCP, Azure write or admin)
- Admin or root access to any production system
- Access to PII, financial, or legal data systems
- Access to security tooling (SIEM, secrets managers)
- Any access that grants the ability to move money or change customer-facing state

Write the `rationale` for request_special_access as DECISION SUPPORT for a non-technical
Onboarding Coordinator who must decide whether to approve it. In 1-2 plain sentences:
  1. Say whether this access is STANDARD/EXPECTED for this person's exact role and seniority,
     so the coordinator knows if it is routine or unusual (e.g. "Read-only AWS is standard
     for senior Platform engineers" vs. "This is unusual for a mid-level sales role —
     worth confirming with the manager").
  2. Say why it still needs their sign-off (which sensitive system it touches).
The Onboarding Coordinator IS the approver. Do NOT write "requires manager sign-off" or
imply a different person must approve — it is the coordinator's decision to make.

Use ONLY the systems, hardware, and security groups listed in the CATALOG FOR THIS HIRE that
will be provided to you. Do not invent system names. If you're unsure whether a system applies,
omit it and note the uncertainty in your reasoning.

Set each item's status to match the action you took, using these definitions exactly:
- Hardware that has been ordered but not yet delivered: "in_progress".
- An account you created or a security group you assigned: "complete".
- Any special-access request awaiting a human decision: "awaiting_approval".
Do not use "pending" for items you have already acted on — "pending" means not yet started.

When you finish, produce a ProvisioningResult with a clear natural-language reasoning trace.
The reader is a non-technical Onboarding Coordinator — explain your decisions in plain English.
"""


def build_it_agent() -> Agent:
    """Construct (but don't run) the agent. Separated from run_it_provisioning so tests
    can inspect the wiring — tool count, output type, model — without a live LLM call."""
    return Agent(
        name="IT Provisioning Agent",
        instructions=IT_SYSTEM_PROMPT,
        model=MODEL,
        tools=IT_TOOLS,
        output_type=ProvisioningResult,
    )


def _grounding_for(profile: NewHireProfile) -> str:
    """Build the per-hire catalog slice we hand to the agent so it reasons over real
    data. This is the 'retrieval' step — we fetch the facts relevant to THIS hire."""
    catalog = {
        "default_hardware": data.get_default_hardware(profile.role_family),
        "shipping_lead_time_business_days": data.get_shipping_lead_time_days(
            profile.location.country
        ),
        "role_software": data.get_software_for_role(profile.role_family),
        "role_security_groups": data.get_security_groups_for_role(profile.role_family),
        "team_slack_channels": data.get_team_slack_channels(profile.team),
        "contractor_restrictions": data.get_contractor_restrictions(),
    }
    return json.dumps(catalog, indent=2)


def _format_input(profile: NewHireProfile) -> str:
    """The user message the agent sees: the profile to act on + its catalog grounding."""
    return (
        "Provision IT for this new hire.\n\n"
        f"NEW HIRE PROFILE:\n{profile.model_dump_json(indent=2)}\n\n"
        f"CATALOG FOR THIS HIRE (use only what's listed here):\n{_grounding_for(profile)}"
    )


def run_it_provisioning(profile: NewHireProfile) -> ProvisioningResult:
    """Run the IT agent for one hire and return its typed result. This is the function
    the orchestrator calls at the Coordinator→IT handoff. Needs OPENAI_API_KEY."""
    ensure_api_key()
    agent = build_it_agent()
    context = ProvisioningContext(profile=profile)
    result = Runner.run_sync(agent, _format_input(profile), context=context)
    # final_output is a ProvisioningResult because output_type is set on the agent.
    return result.final_output
