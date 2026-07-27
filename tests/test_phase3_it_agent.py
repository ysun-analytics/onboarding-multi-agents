"""
Phase 3 tests — the real IT Provisioning agent.

Split into two kinds:
  - WIRING tests (no API key): the agent is constructed correctly — right tools, right
    output type, right model — and grounding is built from real catalog data. These run
    in CI and on any machine, instantly.
  - LIVE test (needs OPENAI_API_KEY): actually calls GPT-4o and checks the agent makes
    the right decisions for Sarah. Auto-skips when no key is present, so the suite stays
    green on machines without a key.
"""

import pytest

from onboarding.agents.it_provisioning import (
    build_it_agent,
    _grounding_for,
    run_it_provisioning,
)
from onboarding.config import MODEL, has_api_key
from onboarding.data_loaders import get_profile
from onboarding.models import ProvisioningResult


# --- WIRING (no key needed) -------------------------------------------------------

def test_agent_has_exactly_five_tools():
    agent = build_it_agent()
    assert len(agent.tools) == 5  # the per-agent tool budget (CLAUDE.md)


def test_agent_uses_typed_output_and_pinned_model():
    agent = build_it_agent()
    assert agent.output_type is ProvisioningResult
    assert agent.model == MODEL == "gpt-4o"


def test_grounding_is_built_from_real_catalog():
    grounding = _grounding_for(get_profile("h_001"))  # Sarah, engineering
    # The engineering catalog facts must be present so the agent can't hallucinate them.
    assert "MacBook Pro" in grounding
    assert "GitHub Enterprise" in grounding
    assert "AWS Console" in grounding  # the approval-gated system


# --- LIVE (needs a key; auto-skips without one) -----------------------------------

@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_sarah_gets_macbook_and_aws_special_access():
    result = run_it_provisioning(get_profile("h_001"))
    assert isinstance(result, ProvisioningResult)
    # Engineer → a MacBook (not a Dell)
    assert "MacBook" in result.hardware.item
    # Senior engineer → AWS must be flagged for approval, not silently granted
    flagged = " ".join(r.system for r in result.special_access_requests)
    assert "AWS" in flagged


@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_contractor_gets_no_special_access():
    result = run_it_provisioning(get_profile("h_002"))  # Marcus, sales contractor
    assert isinstance(result, ProvisioningResult)
    assert result.special_access_requests == []
