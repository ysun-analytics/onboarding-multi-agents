# Build Notes & Interview Prep

This doc tracks **what we've built, the concepts behind it, and the design decisions you need to be able to defend** in the GitHub interview with Andrew. It grows as we build. Each section is written so you can read it cold the night before and walk in able to explain *how you built this and why*.

Companion docs: `4_agent_specs.md` (the spec we build from), `CLAUDE.md` (ground rules), `3_PRD.md` (what & why).

---

## Where we are

| Phase | What it is | Status |
|-------|-----------|--------|
| **1** | Pydantic data contracts (`onboarding/models.py`) | ✅ Done |
| **2** | Data loaders + orchestrator state machine, agents stubbed (`onboarding/data_loaders.py`, `onboarding/orchestrator.py`) | ✅ Done |
| **3** | Real IT Provisioning agent (OpenAI Agents SDK) + Coordinator→IT handoff (`onboarding/agents/it_provisioning.py`, `onboarding/tools/it_tools.py`) | ✅ Done |
| **4a** | Real Compliance & Docs agent (`onboarding/agents/compliance_docs.py`, `onboarding/tools/compliance_tools.py`) | ✅ Done |
| **4b** | Real Manager Prep agent + Learn→Build→Deliver framework + calendar escalation (`onboarding/agents/manager_prep.py`, `onboarding/tools/manager_prep_tools.py`) | ✅ Done |
| **4c** | Coordinator's 2 LLM calls — plan summary + welcome message (`onboarding/agents/coordinator_llm.py`). **Whole pipeline now runs on real LLMs, no stubs.** | ✅ Done |
| **5** | Dashboard — HTML/CSS/JS frontend + thin FastAPI backend, generator-based HITL pause/resume, cached-replay + live-run (`onboarding/server.py`, `onboarding/view_model.py`, `static/`, `scripts/build_demo_cache.py`) | ✅ Done |
| 6 | Scenarios A & B polish + full narrated walkthrough | ⬜ Next |

**Run the dashboard** (use the venv — it has the SDK):
```bash
.venv/bin/python -m pytest -q                       # 44 passing; live tests skip without a key
.venv/bin/uvicorn onboarding.server:app --reload    # open http://127.0.0.1:8000

# Rebuild the cached demo runs after changing an agent/prompt:
.venv/bin/python scripts/build_demo_cache.py        # all demo profiles (real GPT-4o calls)
```

---

## Session log

A running journal of build sessions — what changed and what to study. The *depth* lives in the numbered concept sections below; these entries are the map.

### 2026-06-14 (overnight) — Phase 5 built: the working dashboard

Built the real dashboard end-to-end while you slept: **HTML/CSS/JS frontend + a thin FastAPI backend, driven by the real orchestrator.** 28 → **44 tests green.** The signed-off mockup is now a live product.

**What got built (files):**
- `onboarding/orchestrator.py` — **generator refactor.** `run()`'s body became `run_steps()`, a generator that `yield`s each gate and resumes on `.send(response)`. `run()` is now a thin synchronous driver over it (so all prior tests pass unchanged). New helper `_emit_gate()`.
- `onboarding/view_model.py` — **one rendering contract.** Pure function: orchestrator state → the flat JSON the frontend draws (hire header, orchestrator band, ordered stages with status/summary/reasoning/details, one pending gate). Both cached and live paths emit the identical shape.
- `scripts/build_demo_cache.py` → `demo_cache/*.json` — runs the **real agents once** per profile and freezes every screen. Committed so the demo is instant and key-free.
- `onboarding/server.py` — FastAPI: `/api/profiles`, `/api/run`, `/api/session/{id}/gate`, serves `static/` + `/diagrams`. In-memory sessions. Two drivers: **cached** (replay) and **live** (drive the real generator over HTTP).
- `static/index.html` · `app.css` · `app.js` — the dashboard, ported from the mockup, now data-driven. Two views (Dashboard + How it's built), agent identities, handoff connectors, both HITL shapes, graceful-failure banner.
- Tests: `tests/test_phase5_generator.py` (gate sequence, pause/resume, halt-on-non-approve), `tests/test_phase5_api.py` (cached flow to complete, malformed → graceful, Sarah≠Marcus hero moment).

**New concepts to study (added below):** §15 generator-based pause/resume (why a generator is the right tool for a HITL gate over HTTP); §16 cached-replay vs. live-run (reliability vs. proof); §17 the view-model seam (one shape, two engines).

**Decisions made solo overnight (please ratify):**
1. **Dropped Streamlit for hand-built HTML/CSS/JS** (FastAPI backend). Logged in CLAUDE.md with the reasoning. This was implied by your "build the frontend with HTML + FastAPI" — flagging it explicitly because it changes a "locked" line.
2. **Cached-replay is the default demo path**; "Live run" is a top-right toggle. Cached = never fails mid-walkthrough; live = proves it's real.
3. **Cached all 5 valid profiles** (not just Sarah+Marcus) so no picker option triggers a slow live call by surprise.
4. **Vanilla JS, no framework/build step** — nothing to explain in the walkthrough but the agent design.

**⚠ One thing for you to decide (demo-narrative):** the welcome-message send timing is computed from *today's* date. With today = Jun 14, **Marcus starts exactly 14 days out, so his welcome computes `send_now`, same as Sarah** — the specific "Marcus = scheduled, Sarah = send-now" contrast in Scenario B is currently lost (Diana/Yuki, starting later, *do* show the scheduled path). Options: (a) pin a fixed "demo today" so scenarios are deterministic regardless of run date — cleanest, and a good interview talking point; (b) push Marcus's start date a few days later in the mock data; (c) drop that one narrative beat and lean on hardware/docs/buddy differences (which are vivid: Dell+Salesforce+IR35 vs MacBook+AWS+I-9). **My recommendation: (a).** It needs your call because it touches the Scenario B story you'll narrate.

**Next session:** ratify the above, decide the send-timing question, then Phase 6 — rehearse the narrated A→B walkthrough and tighten any copy.

### 2026-06-14 — dashboard UX design (signed off)

Designed the coordinator dashboard and got visual sign-off. Artifact: `design/onboarding_assistant_mockup.html` (a static HTML/CSS mockup — built because Yuyan is a visual learner and wanted to sign off on the look, not a wireframe). Grounded in **PRD §6.5** (dashboard requirements) and **agent_specs §6** (handoff sequence).

**Design decisions worth defending in the interview:**
- **One clean dashboard for a *non-technical* HR coordinator** (PRD §3). No raw JSON, tool lists, or model names in the primary view — that was the mistake in the first draft. A technical "admin panel" doesn't belong in front of this persona; technical depth lives in a separate **"How it's built"** view *for the interviewer*, plus an optional "show raw output" toggle (the PRD's sanctioned advanced toggle).
- **The Coordinator is the orchestrator, not a peer.** It's rendered as the orchestrating band that owns the flow; the *three specialists* (IT, Compliance, Manager Prep) are what it delegates to. Showing the Coordinator as a fourth status lane was conceptually wrong.
- **Handoffs are the backbone of the view** — parallel IT+Compliance, the **IT→Manager Prep provisioning-summary handoff** called out explicitly, and report-back to the Coordinator. This makes the orchestration legible.
- **Two HITL shapes, visually distinct:** decision gates (3 actions: Approve/Edit/Request-changes) vs. the readiness **alert** (2 actions: Acknowledge/Take-action); plus the **consolidated plan card** (one plan, four sections, one approval — not four sub-approvals).
- **Agent visual identities** (color + icon per agent) for at-a-glance legibility.

**Open decision (next):** implementation stack — the locked choice was Streamlit, but the signed-off design is closer to a real web app than Streamlit can render. Deciding HTML+FastAPI vs. Streamlit-with-CSS before building Phase 5.

### 2026-06-13 — the build session (Phases 1 → 4, complete)

The prior session (2026-06-07) produced the design docs and diagrams. **This session wrote all the code through the end of Phase 4 — the entire agent pipeline now runs on real LLMs, no stubs.**

**Built:**
- **Phase 1** — Pydantic data contracts (`models.py`).
- **Phase 2** — data loaders (the mock-data seam) + the orchestrator state machine, with agents stubbed.
- **Project reorg** — moved docs to `docs/`, kept a flat `onboarding/` package (chose flat over `src/` layout deliberately), added `README.md`, `pyproject.toml`, `.gitignore`.
- **Phase 3** — IT Provisioning agent (first real LLM agent, OpenAI Agents SDK) + the status-drift bug fix.
- **Phase 4a** — Compliance & Docs agent (escalate-don't-guess).
- **Phase 4b** — Manager Prep agent (Learn→Build→Deliver framework + calendar-escalation union type).
- **Phase 4c** — the Coordinator's two LLM calls (plan summary + welcome message), with deterministic send-timing override. **Whole pipeline runs end-to-end on real LLMs.**
- **Environment** — created `.venv` (openai-agents, openai, python-dotenv, eval_type_backport), set up `.env` for the API key. **28 tests** (wiring + deterministic logic run key-free; live tests run with a key).

**Things to study from this session, in priority order:**
1. **§2 — the orchestrator is a state machine, not an agent.** This is the spine answer to "why agents at all?" Expect it to be probed hardest.
2. **§8 — how an agent is actually built** (Agent + Runner + `@function_tool` + context).
3. **§1 — typed contracts (Pydantic)** catching hallucinations at the boundary.
4. **§9 — grounding** (inject the catalog) to stop hallucinated system names.
5. **§12 — Compliance: derive facts, escalate the unknown.** Strongest "why an agent" example.
6. **§13 — Manager Prep: framework-grounded creative output + the union type** for escalation.
7. **§14 — agent vs. single LLM call** (the Coordinator's two content-generation calls) — closes the loop on §2.
8. **§11 — the status-drift debugging story** (fix the *definition*, not the *type*).
9. **§10 — dependency injection** to test an LLM system without calling the LLM.
10. **§3 / §4** — deterministic gate anticipation; graceful failure via the type system.

**The single thread that ties it together** (and recurs in §9, §12, §13): the **facts / actions / judgment** split. Deterministic facts → grounding or computed in code; mechanical actions → tools; genuine judgment → the agent. If you can apply that lens to any part of the system on the spot, you'll handle most "why is this an agent / why isn't that?" questions.

**Open / next:** Phase 4c (the Coordinator's two LLM calls — plan summary + welcome message), then Phase 5 (Streamlit dashboard), Phase 6 (scenarios + full test pass).

---

## Concepts you need to be able to explain

### 1. Typed contracts with Pydantic — "why not just use dictionaries?"

**Plain-language concept.** Pydantic is a Python library where you declare the *shape* of your data as a class (field names + types), and it checks real data against that shape at runtime. If something's missing or the wrong type, it raises an error immediately.

**Why we used it.** Every message between agents in this system is a **typed JSON contract**, not free text. The contract is a Pydantic model. Three payoffs:
1. **Hallucination catching.** When an LLM returns an agent's output, we hand it to Pydantic. If the model invented a field or dropped a required one, we find out *at the boundary*, not three steps later when the dashboard renders garbage.
2. **Downstream code reads data, not English.** The next agent gets `result.hardware.item`, not a paragraph it has to re-parse.
3. **Reasoning lives in its own field.** Every output has a `reasoning` field (`ReasoningTrace`), so the human-readable "why" is visible without polluting the machine-readable data.

**Alternative considered & rejected.** Free-text agent outputs parsed by a *second* LLM call. Rejected: slower, more expensive, and it adds a second place things can go wrong. The type system does for free what a second LLM would do unreliably.

**The one-liner for the interview:** *"Handoffs are typed JSON contracts. A schema mismatch surfaces as a validation error at the boundary, not as garbled behavior three steps downstream."*

---

### 2. The orchestrator is a STATE MACHINE, not an agent — "why agents at all?"

This is the single most important talking point. Andrew will probe it.

**The decision.** The Onboarding Coordinator — which decides who runs, in what order, in parallel or sequentially, and which human gates to surface — is plain Python (`onboarding/orchestrator.py`). No LLM drives the routing.

**Why.** Routing is a **rule**, not a **judgment**. The bar we set for "should this be an agent?" was: *would a hard-coded rule embarrass us six months from now when the edge cases pile up?* Routing fails that test — the order agents run in is stable and knowable. So it stays deterministic. Using an LLM there would add latency and non-determinism while removing the thing we most want from an orchestrator: predictability.

**The nuance that makes the answer strong.** The orchestrator *does* call the LLM twice — to render the plan summary in plain English and to draft the welcome message. Those are **content generation**, where natural language is the actual product. Routing is not. So the rule is consistent: *LLMs are reserved for judgment and language; everything mechanical is deterministic.*

**Where "agents" earn their place (Phase 3-4):** role-specific access decisions, drafting a tailored 30-60-90, reasoning over compliance edge-case combinations. Judgment over fuzzy, edge-case-heavy inputs — exactly what rules are bad at and LLMs are good at.

**The one-liner:** *"I reserved agents for judgment-heavy work and kept the plumbing deterministic. The orchestrator is closer to a state machine than an agent — and that's a feature, because it's how I answer 'why agents at all?'"*

**What makes it visibly a state machine in the code:** there's an explicit `OnboardingState` (received → awaiting_plan_approval → provisioning_and_compliance → manager_prep → drafting_welcome → monitoring → complete, plus halted_invalid). At any moment the dashboard reads `orchestrator.state` and knows exactly where the hire is. That's the difference between a state machine and a tangle of boolean flags.

---

### 3. Deterministic gate *anticipation* — the orchestrator's value made provable

**What it does.** `build_plan()` reads the profile **and the IT/compliance catalogs** to predict which human-approval gates will fire — *before any agent runs*. From Sarah's profile alone it knows she'll trip the AWS special-access gate; from Yuki's it knows Singapore will trigger a compliance escalation.

**Why this matters for the demo.** This is the proof that the routing is *real logic, not a script*. A scripted demo can't look at a new profile and correctly predict its gates. The consolidated, pre-computed plan is "the orchestrator's value proposition made visible": one plan the coordinator approves in one click, instead of four agents each surfacing their own.

**Why a single consolidated plan, not four sub-plans.** If each agent surfaced its own plan, you'd put the coordinator back in the job of stitching the picture together — which is exactly what the product exists to eliminate.

**The one-liner:** *"Before a single agent runs, the orchestrator can already tell you which approval gates this specific hire will trip. That's not a script reading lines — it's rules reading data."*

---

### 4. Graceful failure through the type system — Scenario D for free

**What happens.** The `test_malformed` profile is missing `start_date`. Because `start_date` is a required field on the `NewHireProfile` model, validation *rejects* it. The orchestrator catches that, moves to `halted_invalid`, and logs a plain-language reason — **it never crashes**.

**Why it matters.** The end user is a non-technical HR coordinator who cannot read a stack trace. CLAUDE.md is explicit: agent/input failures must surface as readable messages, not crashes. Here the **type system itself** is the guardrail — we didn't write special validation code, we just declared the field required and handled the error at one chokepoint.

**The one-liner:** *"The malformed-profile case is handled by the type system. start_date is required, so a profile without it is rejected at the boundary and surfaced as a readable message — the dashboard never sees a stack trace."*

---

### 5. Human-in-the-loop has TWO shapes: gates vs. alerts

**The distinction (from `4_agent_specs.md` §0).**
- **Decision gates** (3 actions: approve / edit / request-changes) — used when an agent *proposes a decision* the coordinator can revise. Five of the six touchpoints: plan_approval, special_access, 30_60_90_signoff, welcome_message_review, escalation.
- **Alerts** (2 actions: acknowledge / take-action) — used when there's a *status to act on* but no agent proposal to revise. Only one: readiness_at_risk.

**Why three actions on gates, not two.** Binary approve/reject treats the coordinator as a gatekeeper. Three actions treat them as a *collaborator*: a direct **edit** for mechanical tweaks (toggle an action off, change a date), or free-text **request-changes** for judgment-level pushback ("Sarah doesn't need AWS yet"). The request-changes path is what makes the system feel agentic rather than form-driven — the coordinator pushes back in their own words and the agent revises.

**Why bounded to 2 revisions.** Unbounded revision loops are a known agent failure mode: the LLM chases its tail when feedback contradicts a hard rule (e.g. "skip the I-9" for a US FTE — legally impossible). After 2 cycles we force escalation back to a human. *(Phase 2 implements the gate plumbing; the edit / request-changes / revision-cap logic lands in Phase 4.)*

**The one-liner:** *"I made HITL a three-action surface — approve, edit, request-changes — instead of binary approve/reject, and bounded revisions to two cycles. Three actions treat the human as a collaborator; the cap stops the LLM chasing its tail when feedback contradicts a hard rule."*

---

### 6. The mock-data seam — "the integrations are mocked, the orchestration is real"

**What it is.** `onboarding/data_loaders.py` is the *only* place that touches the JSON files. Everything else calls `get_profile("h_001")` and receives a validated object. In production these functions become MCP calls to Workday / the ITSM / the calendar — and **nothing upstream changes**.

**Why it's designed this way.** It isolates the part that's fake (the plumbing) from the part that's the real IP (the agent logic, handoff design, HITL gates). It's also the honest version of the interview narrative: you're not claiming you built HRIS integrations — you're showing the orchestration is real and the integration is a swap at one clean seam.

**The one-liner:** *"There's exactly one seam between the system and the outside world. Today it reads JSON; in production it's MCP calls to the HRIS. The agent logic, handoffs, and gates don't change — that's the boundary I designed for."*

---

### 7. Project layout — flat package vs. "src layout" (knowing when a best-practice doesn't apply)

This one is less about onboarding and more about showing engineering judgment. The package lives in a **flat `onboarding/` folder at the repo root**, not in a `src/onboarding/` folder. The src layout is the widely-recommended best-practice for production libraries — so be ready to explain why you didn't use it.

**Concept — what the src layout solves.** When your package sits at the repo root (flat), the project root is automatically on Python's import path whenever you run from there. So `import onboarding` works *even though you never installed the package* — you're always testing the raw source folder. The src layout deliberately removes that: the package lives one level down in `src/`, which is **not** on the path by default, so you must `pip install -e .` (an "editable install") before you can import it at all.

**Why that's "more correct" for a shipped library.** A real library gets `pip install`ed into `site-packages`, and the installed copy contains *only the files your packaging config explicitly declares*. Suppose you forget to declare a data file (e.g. `mock_data/*.json`):
- **Flat layout** → tests still pass (they read the file straight from the source folder), so you ship a broken package and it crashes for your *users*. The bug reached production because your test environment didn't match your shipped environment.
- **src layout** → the package is only importable via the editable install, which exercises your real packaging config. The missing file fails *your* tests immediately, before anyone installs it.

So the src layout's whole value is: **it makes your test environment behave like your users' install**, catching missing-file/packaging bugs early. It also stops stray top-level files (a loose `utils.py`, a `setup.py`) from being importable and shadowing things.

**Why flat is the right call *here*.** That protection only pays off if you actually build a **distributable artifact** someone else `pip install`s. This demo is never packaged — it only ever runs from its own folder during a walkthrough. The src layout would charge real friction (you'd have to install the package to develop against it) to defend against a failure mode that **can't happen in this project**. So flat wins, and `pyproject.toml` pins `pythonpath = ["."]` so tests resolve reliably regardless of where they're run.

**The one-liner:** *"I used a flat layout deliberately. The src layout is the best-practice — it forces tests to run against the installed package so you catch missing-file bugs before shipping. But that only matters for a distributable library, and this demo is never pip-installed. Knowing when a best-practice doesn't earn its cost is the actual skill."*

---

### 8. The OpenAI Agents SDK — how an agent is actually built (Phase 3)

The IT Provisioning Agent is the first *real* LLM agent. Three SDK concepts make it work, and you should be able to name all three.

**(a) `Agent` = instructions + tools + typed output + model.** An agent is a configuration object:
```python
Agent(name=..., instructions=SYSTEM_PROMPT, model="gpt-4o",
      tools=IT_TOOLS, output_type=ProvisioningResult)
```
`instructions` is the system prompt (how it thinks). `tools` are the functions it may call. `output_type` forces the final answer into our Pydantic contract. `Runner.run_sync(agent, input, context=...)` executes it and returns a `RunResult` whose `.final_output` is a validated `ProvisioningResult`. **The agent doesn't run itself — the `Runner` runs it.** That separation is what lets the loop (model → tool call → model → …) live in the SDK instead of our code.

**(b) `@function_tool` turns a Python function into a tool the model can call.** The SDK reads the function's name, type hints, and **docstring** to build the JSON schema the model sees — so the docstring is the tool's user-manual *for the LLM*, not a code comment. The model decides *when* to call it; the Python body executes and returns a value the model reads. This is "agents reason, tools execute" at the line level: `request_special_access(...)` is a tool because opening a ticket is mechanical; deciding *that AWS needs approval* is the agent's judgment.

**(c) Context — passing state the LLM must not touch.** Each tool's first parameter, `ctx: RunContextWrapper[ProvisioningContext]`, is stripped from the schema the model sees. We use it to carry the hire's profile and a "ledger" of what's been provisioned. Why this matters: the LLM literally *cannot* invent a ticket id or a hire id, because those come from `ctx`, not from the model. State the model shouldn't control lives in context, not in tool arguments.

**The one-liner:** *"An agent is instructions plus tools plus a typed output schema, run by a Runner. Tools are decorated Python functions whose docstrings are the schema the model reads. Anything the model shouldn't be able to fabricate — ids, the hire's identity — I pass through context, which the SDK hides from the model."*

---

### 9. Grounding — why I feed the agent the catalog (Phase 3)

**The problem.** An ungrounded LLM hallucinates plausible-but-wrong specifics: "I added her to Jira" when the company uses Linear; "MacBook Air" when engineers get Pros. In onboarding, a confidently-wrong system name is exactly the credibility hit the non-technical coordinator can't catch.

**The fix.** Before running the agent, `_grounding_for(profile)` fetches the exact catalog slice for *this* hire — the hardware, the role's software list, security groups, Slack channels, contractor restrictions, shipping lead time — and injects it into the input message. The system prompt then says: *use only what's listed here; do not invent system names.* The agent reasons **over provided facts** instead of free-associating. This is retrieval-augmented prompting in miniature.

**Where the line sits between tool and grounding.** Deterministic *facts* (which laptop, which systems exist) are grounding/data. Deterministic *actions* (open the ticket) are tools. *Judgment* (does this contractor's seniority change what they get? will shipping miss the start date? how do I phrase the approval rationale?) is the agent. That three-way split — facts vs. actions vs. judgment — is the cleanest way to answer "why is this part an agent and that part not?"

**Honest framing (have this ready).** IT is the *lightest-judgment* of the four agents — provisioning is fairly rule-driven, so much of its decision is close to deterministic. That's *why* we built it first: it's the simplest place to validate the whole SDK setup end-to-end before tackling the genuinely judgment-heavy agents (Compliance's role×location×type combinatorics, Manager Prep's 30-60-90 drafting). If asked "couldn't IT be pure rules?": *largely yes today — its value grows with edge cases (odd role/location/contractor combinations, shipping risk), and keeping it an agent means those don't require a code change. But the heavier reasoning lives in Compliance and Manager Prep."*

**The one-liner:** *"I ground the agent by handing it the role's real catalog slice and forbidding invented system names. It reasons over facts I retrieved, it doesn't free-associate — that's what stops a confident hallucination from reaching the coordinator."*

---

### 10. Dependency injection — how I test an LLM system without calling the LLM (Phase 3)

**The problem.** LLM calls are slow, cost money, need an API key, and return different text every time. If my routing tests called GPT-4o, they'd be flaky, expensive, and un-runnable in CI.

**The fix.** The `Orchestrator` takes its IT agent as an injected parameter: `Orchestrator(hire_id, it_runner=...)`. In the demo it defaults to the real agent; in tests I inject `fake_it_runner` — a few lines of deterministic Python that reproduce the *routing-relevant* behavior (a senior engineer trips special access; a contractor doesn't). The same state machine runs against the real agent and the fake one.

**Why this is the right seam.** The routing tests are testing *the orchestrator's decisions*, not *the LLM's output quality*. So I replace the LLM with a fake at exactly the boundary where the orchestrator calls out to it. The agent's actual GPT-4o behavior is covered separately by the live tests, which **auto-skip when there's no key** (`@pytest.mark.skipif`) so the suite stays green everywhere.

**Two kinds of test, on purpose:** *wiring tests* (no key — does the agent have 5 tools, the right output type, the right model?) and *live tests* (key required — does it actually give Sarah a MacBook and flag AWS?). Fast feedback every run; real verification when a key is present.

**The one-liner:** *"I dependency-inject the agents into the orchestrator, so routing tests run against a deterministic fake instead of a live LLM — fast, free, key-free. The real GPT-4o behavior is covered by separate live tests that auto-skip without a key. You test the orchestrator's logic and the agent's output as two different things."*

---

### 11. When an LLM output drifts: fix the *definition*, not the *type* (Phase 3 debugging)

This came out of a real bug in the live run, and it's a sharp piece of judgment to be able to walk through.

**The symptom.** Running the IT agent twice, Sarah's `hardware.status` came back `"pending"` once and `"in_progress"` another — same situation (a just-ordered laptop), different label.

**The wrong instinct (worth naming, because it's the obvious one).** "The type is too permissive — narrow the allowed values." But the status enum is `pending | in_progress | awaiting_approval | complete | blocked`, and hardware **legitimately needs several of those** across its lifecycle (`in_progress` shipping → `complete` delivered → `blocked` if a problem). Narrowing the enum would *delete valid states* to patch a cosmetic drift. The type isn't the problem.

**The actual diagnosis.** Both `pending` and `in_progress` are *defensible* labels for "a laptop I just ordered," because we never **defined** which one applies when. It wasn't an over-wide type — it was an **undefined semantic**, so the model chose differently each run. The drift is a symptom of ambiguity, not permissiveness.

**Two real fixes, and why each is right at a different time:**
- **Define the semantic in the prompt** (what we did now): one line — *"hardware ordered but not delivered is `in_progress`; an account you created is `complete`; a special-access request is `awaiting_approval`; don't use `pending` for things you've acted on."* Cheap, removes the ambiguity, made both profiles consistent immediately. Still leans on the model following instructions.
- **Derive the fact in code** (the principled fix, scheduled for Phase 4): the status is a *fact about what the tool did* — `provision_laptop` already returns `"in_progress"` — so it shouldn't be the LLM's choice at all. This is the **agents-reason / tools-execute** line again: a mechanical fact belongs to the tool, not the agent's free-text judgment. We're holding this for Phase 4 so the "which fields are facts vs. judgment?" rule gets applied *uniformly across all four agents* — patching only IT now would create a new inconsistency, not remove one.

**Process note:** per `CLAUDE.md`, any prompt change triggers a full test re-run, because prompts can silently break downstream parsing. We did — 14/14 green after the edit.

**The one-liner:** *"The status field drifted between runs. The tempting fix — narrow the enum — would have deleted valid lifecycle states; the bug wasn't a loose type, it was an undefined semantic. I defined it in the prompt as the immediate fix, and the deeper fix is to derive mechanical facts in code instead of letting the LLM choose them — which I'm applying across all agents in one pass for consistency."*

---

### 12. The Compliance agent — derive the facts, reserve the LLM for "I don't know" (Phase 4a)

Compliance is where the "facts vs. judgment" split (lesson §11) gets applied *from the start*, and it's the cleanest example of why some work is an agent and some isn't.

**What's deterministic → lives in the tool (`get_required_documents`):**
- *Which* documents a US FTE vs. a UK contractor needs — a catalog lookup against role × location × employment-type.
- *When* each is due — `start_date + offset_days`, computed in code. In the live demo, Sarah's I-9 came back due exactly start+3 days, Benefits at start+30. **Zero drift, every run**, because the model never touches the date.
- The executive / sensitive-data add-on documents — also a deterministic rule.

**What's genuine judgment → lives in the agent:**
- **Escalating an unknown jurisdiction instead of guessing.** Singapore has no rule set. The agent recognized that, *refused to fabricate* a document list, proposed the closest known set (US contractor) as a labeled starting point, and flagged `requires_human_review = True`. In compliance, a confident guess is worse than an honest "I don't know" — so we made "I don't know" a first-class, structured output (`ComplianceEscalation`), not a silent fallback.
- **Explaining the combination in plain English** for the non-technical coordinator.

**Why this is the strongest "why an agent?" example in the project.** A pure rules engine *can* do the known combinations — that's exactly why those are a tool. But a rules engine handles the unknown case by either crashing or silently picking a default. The agent's value is precisely at the boundary of its knowledge: it can recognize "this combination isn't one I have rules for" and escalate with a reasoned best-effort. That judgment-at-the-edge is what you can't get from `if/else`.

**The one-liner:** *"For compliance I put every deterministic fact — which documents, what deadlines — in a tool, so there's no drift. The agent exists for one thing rules can't do: recognizing a jurisdiction it has no rules for and escalating with a reasoned best-effort instead of guessing. The known cases are a lookup; the unknown case is the whole reason it's an agent."*

---

### 13. The Manager Prep agent — grounding creative output in a framework (Phase 4b)

This is the agent where the LLM does the most *creative* work (drafting a 30-60-90), which makes it the best place to talk about controlling creative output. Four things worth being able to explain:

**(a) Why I grounded the 30-60-90 in a framework.** The biggest risk with a creative task is generic AI filler — and the spec literally says *"generic plans signal lack of care."* So instead of "write a 30-60-90," the prompt grounds the model in an established structure: **Learn → Build → Deliver**, with three dimensions per phase (Learning / Contribution / Relationships) and a **SMART** requirement (specific + measurable). I found this by checking how onboarding practitioners actually structure these plans (multiple converging sources), rather than inventing it. Result: Sarah's plan anchors on platform infrastructure, Marcus's on pipeline/quota — *same framework, role-tailored content*. The grounding gives the model rails so the creativity goes into the tailoring, not the structure.

**(b) Why the 30-60-90 is NOT a tool** (a deliberate deviation from the spec's tool list). The spec listed `generate_30_60_90_plan` as a tool. I dropped it: drafting the plan *is* the judgment — the whole reason this is an agent. Calling it a "tool" would imply it's a deterministic action, contradicting the core principle. So the agent writes the plan directly into its typed output, and the 4 tools are reserved for mechanical actions (calendar, scheduling, buddy candidates, checklist). *Knowing what should NOT be a tool is as important as knowing what should.*

**(c) The buddy split — facts from a tool, judgment from the agent.** `find_onboarding_buddy` returns *candidates* from the org roster (a fact the LLM can't know). The agent *picks one and writes the rationale* (judgment). Crucially, I withheld the planted `buddy_notes` hints from the candidate data — so when the agent picked Tom for Sarah, it reasoned genuinely from tenure + skill overlap + calendar load, not by reading a label. That's the difference between an agent reasoning and an agent parroting.

**(d) The union type earning its keep — escalate, don't crash.** `intro_meeting` is a union: a *scheduled* meeting OR a *blocked* escalation with alternatives. When the manager's calendar is empty, the agent must produce the blocked shape (skip-level intro, async doc, push to day 4) — never an empty "scheduled." Modeling the failure as a *distinct shape* (not an empty success) forces the dashboard to render it explicitly; we can't accidentally treat a scheduling failure as a soft success. This is why the union type in the contract was worth the small extra complexity.

**The one-liner:** *"Manager Prep does the most creative work, so I grounded it: the 30-60-90 follows an established Learn-Build-Deliver framework with SMART, role-tailored goals — the creativity goes into tailoring, not structure. I deliberately did NOT make the plan a tool, because drafting it is the judgment. And the intro-meeting is a union type so a fully-booked calendar escalates as a distinct shape instead of faking a soft success."*

---

### 14. The Coordinator's two LLM calls — an "agent" vs. a single LLM call (Phase 4c)

This closes the loop on the project's defining claim — *the orchestrator is a state machine, not an agent* (§2) — by showing exactly where it *does* use the LLM, and why that doesn't make it an agent.

**An agent vs. a single LLM call — be able to draw this line crisply.** An *agent* runs a loop and uses tools: it decides, calls a tool, reads the result, decides again, until it's done. A *single LLM call* does neither — it's one shot: data in, structured text out. The Coordinator's two LLM calls (`render_plan_summary`, `draft_welcome_message`) are the second kind. Mechanically they're built as **tool-less Agents** (an `Agent` with `output_type` and no tools is just the SDK's clean way to get one validated typed result), but architecturally they are *not agents* — no tools, no loop, no actions. The test asserts `agent.tools == []` to make the point.

**Why the orchestrator reaches for the LLM at exactly these two points.** Routing is a rule (deterministic). But *rendering a plan in plain English* and *writing a warm welcome note* are content generation — language is the actual product. That's the consistent rule across the whole system: **LLMs for language and judgment; deterministic code for everything else.** Two LLM calls inside a state machine isn't a contradiction — it's the rule applied precisely.

**The send-timing override — facts-vs-judgment, one more time.** The welcome message's *words* are the LLM's job. Its *send timing* (send now if start is within 14 days, else schedule for start − 14) is a date computation — a fact. So the orchestrator computes it in `_compute_send_strategy` and **overrides** whatever the model returned. The LLM writes the words; code decides the when. (We even tell the model in the prompt not to bother deciding it.)

**The orchestrator as synthesizer.** The welcome message's "day-one logistics" are stitched together by the orchestrator from *different* specialists' outputs — the hardware from IT, the buddy and intro time from Manager Prep. That stitching is the orchestrator's core value proposition made concrete: the coordinator (and the new hire) get one consolidated picture instead of four disconnected ones. Same reason the plan summary is ONE consolidated plan, not four separate sub-plans.

**The one-liner:** *"The orchestrator stays a state machine, but it makes two single LLM calls — not agents, no tools, no loop — for the two things that are pure content generation: rendering the plan in plain English and writing the welcome note. Even there, the send timing is a date calculation, so code computes it and overrides the model. LLMs for language, code for facts — applied right down to the last field."*

---

### 15. Generator-based pause/resume — how a human stays in the loop *over HTTP* (Phase 5)

This is the cleverest piece of Phase 5, and a likely "how does the human-in-the-loop actually work technically?" question.

**The problem.** A HITL gate has to *stop the whole machine* and wait for a person to click a button in a browser. But over HTTP there's nothing to block on: the request that started the run returned long ago, and the click arrives in a *separate* request minutes later. A normal function can't pause in the middle and pick up where it left off. So how do you "wait for a human" without freezing a server thread or rewriting the orchestrator as a tangle of callbacks?

**The tool that fits the shape of the problem: a Python generator.** A generator is a function that can *suspend itself* with `yield` and be resumed later with `.send(value)`. So the orchestrator's flow became `run_steps()`, a generator: when it reaches a gate it does `response = yield request` — that **freezes the entire machine exactly where it is**, hands the gate out to whoever's driving, and the function's local state (which agents have run, what they returned) just sits there in memory. When the human clicks, the server calls `gen.send(their_response)` and the machine *thaws* and continues from that line. The gate's `yield` literally becomes the human's answer.

**Why this is better than the alternatives.** (a) *Blocking a thread* until the click comes — wastes a worker, doesn't survive a page refresh, and ties up the server. (b) *A big state variable + re-entering a function from the top each time* (a hand-rolled state machine on top of the state machine) — you'd have to manually save and restore "where was I," which is exactly the bookkeeping a generator does for free. (c) *Callbacks/promises everywhere* — turns one readable top-to-bottom flow into spaghetti. The generator keeps the flow **linear and readable** — you read `run_steps()` top to bottom and see the whole onboarding — while still being pausable.

**The "one engine, two drivers" payoff.** Because the pause is just `yield`, the *same* `run_steps()` generator runs two completely different ways without changing a line: the tests and the cache-builder use the thin synchronous `run()` driver (answer each gate immediately in a loop); the web server drives it by hand (`next()` to the first gate, return it over HTTP, `send()` the answer when the click lands). One state machine, driven synchronously in tests and asynchronously in the browser. That's the cleanest possible separation between *the logic* and *who's answering the gates*.

**The one-liner:** *"A human gate means 'stop and wait for a click that arrives in a later HTTP request.' A Python generator is exactly that primitive — `yield` freezes the whole flow with its local state intact, `send()` resumes it with the human's answer. So the orchestrator reads as one linear top-to-bottom flow, but it's fully pausable. The same generator is driven synchronously by the tests and asynchronously by the web server — one engine, two drivers."*

### 16. Cached-replay vs. live-run — reliability for the demo, proof on demand (Phase 5)

A product/PM-flavored decision with a clean engineering answer — exactly the kind of thing this role probes.

**The tension.** The live pipeline calls GPT-4o ~6 times per hire (plan summary, IT, compliance, manager prep, welcome — plus each agent's internal tool loop). That's 20-40 seconds and a non-zero chance of a transient API hiccup. In a 45-minute interview you want the dashboard to feel *instant* and *never* fail mid-click. But a purely faked demo invites the fair challenge "is any of this actually real?"

**The resolution: do both, and be explicit about which is which.** `scripts/build_demo_cache.py` runs the **real agents once**, captures every screen the dashboard will show, and commits it to `demo_cache/*.json`. The dashboard replays that by default — instant, deterministic, key-free, crash-proof. A **"Live run" toggle** in the top-right drives the genuine agents on demand. So: **cached = reliability, live = proof.** You narrate Scenario A from cache, then flip the toggle once to show the same screens being generated for real. (This is the PRD §9 risk mitigation, made concrete.)

**Why this is honest, not a fake.** The cache isn't hand-written fixtures — it's *real agent output, frozen*. Same code path produced it; the live toggle regenerates it in front of the interviewer. The analogy: a recorded demo of a real system vs. a mockup. We have the recording *and* the live system, and we can switch between them.

**The one-liner:** *"Cached-replay is the default so the demo is instant and can't fail mid-walkthrough; a live-run toggle proves it's genuine. The cache is real agent output captured by a script, not fixtures — the same code path, frozen. Reliability and proof, instead of choosing one."*

### 17. The view-model seam — one shape the frontend draws, two engines behind it (Phase 5)

**What it is.** `onboarding/view_model.py` is a *pure function*: it reads the orchestrator's state (plan, results, which gate is pending) and returns one flat, JSON-serializable structure — hire header, orchestrator band, an ordered list of stages (each with status, summary, reasoning trace, structured details), and at most one pending gate. The frontend knows *only* this shape. It never sees Pydantic, the OpenAI SDK, or how the orchestrator advances.

**Why a dedicated seam, instead of letting the frontend read agent outputs directly.** Three payoffs. (1) **One render path for two engines:** cached-replay and live-run both produce the identical view-model, so `app.js` has a single `render(view)` function regardless of which engine answered. (2) **Decoupling:** I can change an agent's internal output shape without touching the frontend, as long as the view-model stays stable — and vice-versa. (3) **It's the natural test surface:** the API tests assert on the view-model (e.g. "exactly one stage carries the pending gate," "Sarah's IT summary ≠ Marcus's"), which is far more stable than asserting on raw LLM output.

**The pattern has a name:** this is essentially the *view-model* / *presenter* pattern (as in MVVM) — a translation layer between domain objects and what the UI renders. Worth naming in the interview: it shows you reached for an established pattern, not an ad-hoc dict.

**The one-liner:** *"The frontend draws one shape — a view-model — produced by a pure function over the orchestrator's state. Cached and live runs both emit it, so there's a single render path; the agents and the UI can each change without touching the other; and it's the clean surface the tests assert on. It's the presenter/view-model pattern, applied to an agent system."*

---

## Design decisions log (the "I chose A over B because..." ammunition)

| Decision | Chose | Over | Because |
|----------|-------|------|---------|
| Data validation | Pydantic models | plain dicts / dataclasses | runtime validation catches LLM hallucinations at the boundary; dataclasses don't validate |
| `role_family` | coarse 6-value enum | fine-grained job-title enum | LLMs are good at fuzzy categorization, type systems aren't — keep nuance in the prompt, routing in the type |
| Orchestrator | Python state machine | an LLM-driven agent | routing is a rule not a judgment; determinism is the feature |
| Enums | `Literal[...]` | Python `Enum` class | serializes to plain JSON strings the LLM/mock-data already use; no `.value` plumbing |
| HITL surface | 3 actions (approve/edit/request-changes) | binary approve/reject | treats coordinator as collaborator, not gatekeeper; enables the agentic feel |
| Revision loops | capped at 2 then escalate | unbounded | bounds the "LLM chases its tail against a hard rule" failure mode |
| Malformed input | required field + validation error | manual if/else checks | the type system *is* the guardrail; one chokepoint, no scattered validation |
| Gate resolution | `gate_handler` callback into the orchestrator | gates hard-wired in the orchestrator | same state machine drives the live dashboard and the tests — inversion of control |
| `intro_meeting` | union of scheduled-vs-blocked shapes | one shape with optional fields | forces the dashboard to render the escalation case explicitly; can't fake a failure as a soft success |
| Project layout | flat `onboarding/` package | `src/onboarding/` layout | src layout only earns its cost for distributable libraries; this demo is never pip-installed, so flat avoids friction for no real benefit |
| First real agent | IT Provisioning | Compliance or Manager Prep | IT carries the lightest judgment load, so it's the cleanest place to validate SDK plumbing before the hard agents |
| Agent grounding | inject the role's catalog slice into the prompt | let the agent recall systems from training | stops confident hallucination of system names — agent reasons over retrieved facts |
| Testing LLM system | dependency-inject a fake agent into the orchestrator | call the real LLM in every test | routing tests stay fast/free/key-free; live behavior covered by separate skippable tests |
| Secrets | `.env` file (gitignored) + `python-dotenv` | hard-code key / commit it | keeps the key out of source control; `.env.example` documents the shape |
| Python 3.9 + SDK | `eval_type_backport` shim | install a new Python 3.12 | lowest-friction fix for a demo; production would just use 3.12 |
| LLM status drift | define the semantic in the prompt (now) + derive in code later | narrow the status enum | narrowing would delete valid lifecycle states; the bug was an undefined semantic, not a loose type |
| 30-60-90 structure | ground in Learn→Build→Deliver framework | free "write a 30-60-90" prompt | grounding stops generic AI filler; creativity goes into role-tailoring, not inventing structure |
| `generate_30_60_90` | NOT a tool — agent writes it into output | tool, as the spec listed | drafting the plan IS the judgment; calling it a tool implies it's deterministic |
| Buddy `buddy_notes` | withheld from candidate data | include the planted hint | forces genuine reasoning over tenure/skill/load instead of parroting a label |
| Coordinator content gen | tool-less Agents (single LLM calls) | full agents with tools | rendering a plan / writing a note is one-shot content generation, not a tool-using loop |
| Welcome send timing | computed in code, overrides the LLM | let the LLM decide it | send timing is a date calculation (a fact), not a judgment |

---

## Likely interview questions & crisp answers

**"Why is this multi-agent and not one big prompt?"**
Because the four domains (IT, manager prep, compliance, coordination) have different knowledge, different tools, and different failure modes. One mega-prompt would blur them, and agent performance degrades with large tool sets — so I gave each agent 3-5 focused tools. Separation also maps to the org chart, which makes the demo legible to an HR audience.

**"Why a state machine for the orchestrator — isn't that just a workflow engine?"**
Yes, deliberately. Routing is deterministic, so it should be predictable and testable. I reserve LLMs for the two places inside the orchestrator where language is the product. "Agentic" doesn't mean "an LLM decides everything" — it means an LLM decides the things that need judgment.

**"How do you stop an agent from doing something dangerous, like granting AWS admin?"**
Human gates at the judgment moments, not the mechanical ones. Provisioning a standard laptop auto-completes; anything touching cloud/admin/PII/security tooling is a *typed* special-access request that pauses for human approval. It's typed, not a flag, so the dashboard can show the agent's rationale on the approval card.

**"What happens when an agent gets input it can't handle?"**
Two layers. Malformed structural input is rejected by the type system and surfaced as a readable message (never a crash). Semantic uncertainty — e.g. a compliance jurisdiction we have no rules for — is an explicit *escalation*, not a silent guess. "I don't know" must reach a human in a compliance domain.

**"What would you change for production?"**
Swap the mock loaders for MCP integrations at the one seam; add real auth and audit logging; persist state (currently in-memory); add retries/backoff on the integration calls. None of the agent logic, handoff contracts, or gates would change — which is the point.

---

## Glossary (terms of art, defined once)

- **Pydantic model** — a class declaring data shape; validates real data against it at runtime.
- **Structured / typed output** — forcing an LLM to return data matching a schema, not free prose.
- **Handoff contract** — the agreed schema for data passed from one agent to the next.
- **State machine** — code that's always in exactly one named state and moves between them by defined rules.
- **HITL (human-in-the-loop) gate** — a pause where a human approves/edits/pushes back before the system proceeds.
- **Inversion of control** — the orchestrator calls *out* to a handler for the human decision, instead of containing it; lets tests and the dashboard plug into the same machine.
- **Seam** — the single boundary where the system meets an external integration; designed so it can be swapped without touching anything else.
