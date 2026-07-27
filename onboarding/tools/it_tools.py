"""
it_tools.py — the IT Provisioning Agent's five tools.

These are the "tools execute" half of the project's core principle ("agents reason,
tools execute"). Each tool performs ONE deterministic action and returns a result.
In the demo they return mocked tickets/ids; in production they'd be MCP calls to the
IT service desk. The agent (the LLM) decides WHAT to provision and WHY; these tools
just carry out the mechanical action and record it.

Two SDK concepts worth understanding for the interview:

1. `@function_tool` — this decorator turns a plain Python function into a tool the LLM
   can call. The SDK reads the function's name, type hints, and docstring to build the
   JSON schema the model sees. So the docstring is not a comment — it's the tool's
   user manual for the LLM. Write it for the model.

2. Context (`RunContextWrapper`) — the first parameter, `ctx`, is how a tool reaches
   shared run state WITHOUT the LLM seeing or filling it. The SDK strips `ctx` from the
   schema. We use it to pass the hire's profile and a "ledger" that accumulates what's
   been provisioned, so `check_provisioning_status` can report it. This keeps per-hire
   state out of the LLM's hands (it can't hallucinate a ticket that was never created).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents import RunContextWrapper, function_tool

from .. import data_loaders as data
from ..models import NewHireProfile


@dataclass
class ProvisioningContext:
    """Shared, per-hire state for one provisioning run. Passed to every tool via ctx;
    never exposed to the LLM."""

    profile: NewHireProfile
    ledger: List[Dict[str, Any]] = field(default_factory=list)  # record of tool actions

    def _next_id(self, prefix: str) -> str:
        """Deterministic id from the hire + how many actions we've recorded — no random
        or clock needed, so runs are reproducible (nice for demos and tests)."""
        return f"{prefix}-{self.profile.hire_id}-{len(self.ledger) + 1:02d}"


@function_tool
def provision_laptop(
    ctx: RunContextWrapper[ProvisioningContext], model: str, ship_to_country: str
) -> dict:
    """Open a hardware-provisioning ticket for the new hire's laptop.

    Args:
        model: The laptop model to provision, e.g. "MacBook Pro 16-inch (M-series)".
        ship_to_country: The hire's country code (e.g. "US", "UK", "SG"), used to
            estimate shipping lead time.
    """
    eta_days = data.get_shipping_lead_time_days(ship_to_country)
    ticket_id = ctx.context._next_id("HW")
    record = {
        "action": "provision_laptop", "ticket_id": ticket_id, "model": model,
        "ship_to": ship_to_country, "eta_business_days": eta_days, "status": "in_progress",
    }
    ctx.context.ledger.append(record)
    return record


@function_tool
def create_account(
    ctx: RunContextWrapper[ProvisioningContext], system: str, access_level: str
) -> dict:
    """Create a user account on a SaaS or internal system.

    Args:
        system: The system name, e.g. "GitHub Enterprise" or "Salesforce".
        access_level: The access tier, e.g. "developer", "user", "read".
    """
    account_id = ctx.context._next_id("ACCT")
    record = {
        "action": "create_account", "account_id": account_id, "system": system,
        "access_level": access_level, "status": "complete",
    }
    ctx.context.ledger.append(record)
    return record


@function_tool
def assign_security_group(
    ctx: RunContextWrapper[ProvisioningContext], group: str
) -> dict:
    """Add the new hire to a security/access group.

    Args:
        group: The security group name, e.g. "engineering-all" or "production-readonly".
    """
    record = {"action": "assign_security_group", "group": group, "status": "complete"}
    ctx.context.ledger.append(record)
    return record


@function_tool
def request_special_access(
    ctx: RunContextWrapper[ProvisioningContext],
    system: str,
    access_level: str,
    rationale: str,
) -> dict:
    """Open a request for ELEVATED or SENSITIVE access that requires human approval.
    Use this instead of create_account for anything touching cloud write/admin,
    production admin, PII/financial/legal data, or security tooling.

    Args:
        system: The system, e.g. "AWS Console".
        access_level: The elevated access requested, e.g. "read", "admin".
        rationale: Plain-English reason this access is needed — shown to the human
            approver on the dashboard card.
    """
    request_id = ctx.context._next_id("SPECIAL")
    record = {
        "action": "request_special_access", "request_id": request_id, "system": system,
        "access_level": access_level, "rationale": rationale, "status": "pending_approval",
    }
    ctx.context.ledger.append(record)
    return record


@function_tool
def check_provisioning_status(ctx: RunContextWrapper[ProvisioningContext]) -> dict:
    """Return everything provisioned for this hire so far in this run. Call this before
    finishing to confirm what was actually done."""
    return {
        "hire_id": ctx.context.profile.hire_id,
        "actions": ctx.context.ledger,
        "count": len(ctx.context.ledger),
    }


# Exported in the order the agent should generally consider them. Exactly 5 tools —
# the upper limit of our per-agent budget (CLAUDE.md: larger tool sets degrade tool
# selection accuracy).
IT_TOOLS = [
    provision_laptop,
    create_account,
    assign_security_group,
    request_special_access,
    check_provisioning_status,
]
