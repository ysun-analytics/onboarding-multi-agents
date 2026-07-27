"""
data_loaders.py — thin, typed access to the mock JSON files.

In production these functions would be MCP calls to the HRIS, ITSM, and calendar
systems. For the demo they read JSON from mock_data/. The KEY design point for the
interview: the rest of the codebase never touches raw JSON or knows where the data
lives. It calls get_profile("h_001") and gets back a validated NewHireProfile. So
when the integration is swapped from "read a file" to "call Workday," nothing
upstream changes. This is the "integrations are mocked, the orchestration is real"
narrative made concrete — the seam is right here.

We keep these functions deterministic and dumb on purpose. They fetch and validate;
they do not decide anything. All judgment lives in the agents, all routing in the
orchestrator. (CLAUDE.md: "agents reason, tools execute.")
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from .models import NewHireProfile

# mock_data/ sits next to the onboarding/ package, one level up from this file.
_DATA_DIR = Path(__file__).resolve().parent.parent / "mock_data"


@lru_cache(maxsize=None)
def _load_json(filename: str) -> dict:
    """Read and cache a mock-data file. lru_cache means each file is read from disk
    once per process — fine because the mock data never changes at runtime."""
    with open(_DATA_DIR / filename, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def get_raw_profile(hire_id: str) -> dict:
    """Return the unvalidated dict for a hire. Used by the validation gate, which
    must be able to inspect a malformed profile WITHOUT raising — so it can report
    the problem to the coordinator gracefully instead of crashing."""
    profiles = _load_json("profiles.json")
    if hire_id not in profiles:
        raise KeyError(f"No profile with hire_id={hire_id!r}")
    return profiles[hire_id]


def get_profile(hire_id: str) -> NewHireProfile:
    """Return a validated NewHireProfile. Raises pydantic.ValidationError if the
    underlying data is malformed (e.g. the test_malformed fixture)."""
    return NewHireProfile.model_validate(get_raw_profile(hire_id))


def list_profile_ids() -> List[str]:
    return list(_load_json("profiles.json").keys())


# ---------------------------------------------------------------------------
# Org roster (teams + members) — used to resolve manager names and find buddies
# ---------------------------------------------------------------------------

def get_team(team: str) -> Optional[dict]:
    return _load_json("org_rosters.json").get(team)


def get_team_members(team: str) -> List[dict]:
    t = get_team(team)
    return t["members"] if t else []


def get_manager_name(manager_id: str) -> str:
    """Resolve a manager_id to a display name by scanning the rosters. Returns the
    id itself if not found, so the dashboard degrades gracefully rather than
    throwing on an unknown manager."""
    for team in _load_json("org_rosters.json").values():
        for member in team["members"]:
            if member["user_id"] == manager_id:
                return member["full_name"]
    return manager_id


# ---------------------------------------------------------------------------
# Manager calendars — used by Manager Prep (Phase 4) and the orchestrator
# ---------------------------------------------------------------------------

def get_free_slots(manager_id: str) -> List[str]:
    """First-week free slots for a manager. Empty list = fully booked (the Scenario C
    edge case). We return [] rather than raising so the caller decides how to handle
    'no availability' — which for Manager Prep means escalate, not crash."""
    cal = _load_json("calendars.json").get(manager_id)
    return cal["free_slots_first_week_of_hire"] if cal else []


# ---------------------------------------------------------------------------
# IT catalog — read by the orchestrator's plan builder to ANTICIPATE which
# special-access gates will fire, and by the IT agent's tools in Phase 3.
# ---------------------------------------------------------------------------

def get_software_for_role(role_family: str) -> List[dict]:
    return _load_json("it_catalog.json")["software_by_role_family"].get(role_family, [])


def get_default_hardware(role_family: str) -> str:
    table = _load_json("it_catalog.json")["hardware_by_role_family"]
    entry = table.get(role_family, table["other"])
    return entry["default"]


def get_security_groups_for_role(role_family: str) -> List[str]:
    return _load_json("it_catalog.json")["security_groups_by_role_family"].get(role_family, [])


def get_team_slack_channels(team: str) -> List[str]:
    return _load_json("it_catalog.json")["team_slack_channels"].get(team, [])


def get_contractor_restrictions() -> dict:
    return _load_json("it_catalog.json")["contractor_restrictions"]


def get_shipping_lead_time_days(country: str) -> int:
    table = _load_json("it_catalog.json")["international_shipping_lead_time_days"]
    return table.get(country, table["default_unknown"])


# ---------------------------------------------------------------------------
# Compliance catalog — read by the plan builder to anticipate escalations and by
# the Compliance agent's tools in Phase 3.
# ---------------------------------------------------------------------------

def get_known_jurisdictions() -> List[str]:
    return _load_json("compliance_catalog.json")["known_jurisdictions"]
