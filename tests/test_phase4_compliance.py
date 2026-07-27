"""
Phase 4 tests — the real Compliance & Docs agent.

Same two-tier shape as Phase 3: wiring + pure-logic tests run without a key; live
GPT-4o behavior tests auto-skip without one.
"""

import pytest

from onboarding.agents.compliance_docs import build_compliance_agent, run_compliance_docs
from onboarding.config import MODEL, has_api_key
from onboarding.data_loaders import get_profile
from onboarding.models import ComplianceResult
from onboarding.tools.compliance_tools import _compute_deadline


# --- WIRING + PURE LOGIC (no key needed) ------------------------------------------

def test_agent_wiring():
    agent = build_compliance_agent()
    assert len(agent.tools) == 4
    assert agent.output_type is ComplianceResult
    assert agent.model == MODEL == "gpt-4o"


def test_deadline_is_computed_deterministically():
    # The deadline is start_date + offset — a fact computed in code, never by the LLM.
    assert _compute_deadline("2026-06-21", 3) == "2026-06-24"
    assert _compute_deadline("2026-06-21", 0) == "2026-06-21"
    assert _compute_deadline("2026-06-28", 30) == "2026-07-28"


# --- LIVE (needs a key; auto-skips without one) -----------------------------------

@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_us_fte_gets_i9_and_no_escalation():
    result = run_compliance_docs(get_profile("h_001"))  # Sarah, US FTE
    assert isinstance(result, ComplianceResult)
    names = " ".join(d.name for d in result.required_documents)
    assert "I-9" in names
    assert result.escalations == []


@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_uk_contractor_gets_ir35():
    result = run_compliance_docs(get_profile("h_002"))  # Marcus, UK contractor
    names = " ".join(d.name for d in result.required_documents)
    assert "IR35" in names
    assert "Right to Work" in names


@pytest.mark.skipif(not has_api_key(), reason="no OPENAI_API_KEY; skipping live LLM call")
def test_unknown_jurisdiction_escalates_not_guesses():
    result = run_compliance_docs(get_profile("h_005"))  # Yuki, Singapore (unknown)
    assert len(result.escalations) >= 1
    assert result.escalations[0].requires_human_review is True
