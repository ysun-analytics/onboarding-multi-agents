# Onboarding Multi-Agent Orchestration

A demo of multi-agent orchestration for **HR onboarding**. When someone is hired at a mid-market
company, onboarding touches 8–12 people and systems (IT, the hiring manager,
compliance, payroll, facilities), coordinated by hand through Slack and email.
Things get dropped; new hires show up with no laptop and no access. This system
puts a specialized AI agent on each domain, coordinated by a deterministic
orchestrator, with human approval at the high-judgment moments.

> **Scope:** This is a demo optimized for *narrative clarity*, not
> production scale. Integrations (HRIS, ITSM, calendar) are mocked as JSON on
> purpose — the IP is in the agent design and handoff contracts, not the plumbing.

---

## Architecture

The **Onboarding Assistant** — a deterministic orchestrator — directs three specialist
agents named after HR functions. (The Assistant is the product/orchestrator; the human
end-user is the *Onboarding Coordinator* — kept distinct so the tool isn't named after
the person using it.)

| Component | What it does | How it's built |
|-----------|--------------|----------------|
| **Onboarding Assistant** | Routes work, surfaces one consolidated plan, drafts the welcome message | Python **state machine** (+ 2 LLM calls for content) — *not* an agent |
| **IT Provisioning** | Hardware, accounts, security groups; flags special access | LLM agent + tools |
| **Manager Prep** | 30-60-90 plan, intro meeting, onboarding buddy | LLM agent + tools |
| **Compliance & Docs** | Required documents by role × location × employment type | LLM agent + tools |

**Core design principle:** *agents reason, tools execute.* Deterministic rules
(routing, document lookups) are Python; judgment over edge cases (access decisions,
30-60-90 drafting, compliance combinations) is an agent. The orchestrator is a state
machine because routing is a *rule*, not a *judgment* — which is the answer to "why
agents at all?"

Handoffs between components are **typed JSON contracts** (Pydantic), and humans
approve at five gates: plan approval, special access, 30-60-90 sign-off, welcome
message review, and a readiness-at-risk check.

---

## Project structure

```
onboarding/            The Python package — the real IP
  models.py              Pydantic data contracts (the spine; everything imports this)
  data_loaders.py        The single seam over mock data → swap for MCP in production
  orchestrator.py        The deterministic state machine
  agents/                LLM agents (Phase 3)
  tools/                 Agent tools (Phase 3)
mock_data/             Mock HRIS / IT / calendar data as JSON (the "fake integrations")
tests/                 Tests that guard the demo invariants
docs/                  Planning docs, agent specs, and the interview study guide
  7_build_notes_and_interview_prep.md   ← read this to understand the "why"
README.md  CLAUDE.md  pyproject.toml  requirements.txt
```

---

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run the test suite (guards the demo invariants)
.venv/bin/python -m pytest -q

# Start the dashboard (open http://127.0.0.1:8000)
# Use `python -m uvicorn` (not `.venv/bin/uvicorn`): the space in this folder's path makes
# the bare-uvicorn launcher fragile, and it can silently run under system Python (no SDK →
# "live run" fails with ImportError). `-m` always uses the venv interpreter.
.venv/bin/python -m uvicorn onboarding.server:app --reload
```

The dashboard defaults to **cached mode** — it replays a real, frozen agent run per
hire, so the demo is instant and never fails mid-walkthrough. Tick **"Live run"** in
the top-right to drive the real GPT-4o agents on demand (needs `OPENAI_API_KEY` in
`.env`). Cached = reliability; live = proof it's real.

To (re)build the cache after changing an agent or prompt:

```bash
.venv/bin/python scripts/build_demo_cache.py          # all demo profiles
.venv/bin/python scripts/build_demo_cache.py h_001    # just one
```

You can still watch the orchestrator route a hire from a one-liner:

```bash
.venv/bin/python -c "from onboarding.orchestrator import Orchestrator; \
from onboarding.models import ApproveResponse; \
o=Orchestrator('h_001'); o.run(lambda r: ApproveResponse(action='approve')); \
print(chr(10).join(o.events))"
```

## Build status

- ✅ **Phase 1** — Pydantic data contracts
- ✅ **Phase 2** — data loaders + orchestrator state machine (agents stubbed)
- ✅ **Phase 3** — real IT Provisioning agent (OpenAI Agents SDK) + Assistant→IT handoff
- ✅ **Phase 4** — Compliance, Manager Prep, and the Assistant's two LLM calls; **whole pipeline runs end-to-end on real LLMs.**
- ✅ **Phase 5** — dashboard: HTML/CSS/JS frontend + thin FastAPI backend, generator-based pause/resume for the HITL gates, cached-replay + live-run. **44 tests green** (live tests skip without a key)
- ⬜ **Phase 6** — Scenarios A & B polish + full narrated walkthrough

## Tech stack

OpenAI Agents SDK (Python) · GPT-4o · Pydantic · Python state machine · FastAPI ·
vanilla JS (no build step) · pytest
