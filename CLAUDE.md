# CLAUDE.md — Onboarding Multi-Agent Orchestration

## What this project is

A demo for an internal built product. Optimize for **demo legibility and narrative clarity**, not for production robustness, scale, or completeness. Integrations are mocked on purpose — the IP is in the agent design, not the plumbing.

If a request would expand scope beyond the one-week build plan in `1_interview_context_and_product_idea.md`, flag it and ask before implementing.

---

## Two personas — keep them distinct

### The end user: the Onboarding Coordinator

The person the product is *for*. A non-technical HR operator who today coordinates 8-12 people per hire through Slack and email. They want automation, fewer dropped balls, and less manual chasing.

Implications for what we build:
- **Low error tolerance.** If the demo throws a stack trace or an agent hallucinates a buddy who doesn't exist on the team, the credibility damage is large. Fail gracefully — surface the problem in the dashboard with a clear message, not a crash.
- **Cannot troubleshoot.** If something goes wrong, they will not open a terminal. The dashboard must show *what* the agent decided, *why*, and *what to do next* in plain language.
- **Trust is earned through visibility.** Reasoning traces, status indicators, and approval gates aren't UX polish — they are the product. The coordinator stays in control because they can see every decision before it commits.

### The developer: Yuyan (the person writing the code with you)

A PM and AI strategist.

Implications for how you communicate:
- **Explain every non-trivial technical decision.** Not just *what* you did, but *why it's better than the alternatives you considered*. "I used X because Y, instead of Z which would have caused problems with W." She needs to be able to defend the choice in an interview.
- **Teach concepts as they come up.** When introducing something new (handoff contracts, structured outputs, tracing, guardrails, async tool calls, etc.), give a brief plain-language explanation before using it. Assume strong product/strategy intuition and no prior implementation experience.
- **Surface alternatives even when she didn't ask.** "I could have done A or B here. I chose A because [reason]. The tradeoff is [tradeoff]." This is interview ammunition.
- **Plain language for code choices.** No jargon dumps. If you must use a term of art (idempotency, retry-with-backoff, semantic search), define it the first time.
- **Connect implementation back to product reasoning.** When she sees the code, she should be able to map it back to the design decisions in doc 1.

---

## Architectural decisions (locked in — do not re-litigate)

These were debated and settled. Don't propose collapsing, renaming, or restructuring unless explicitly asked.

- **The Onboarding Assistant (the orchestrator) directs three specialist agents named after HR functions**: IT Provisioning, Manager Prep, Compliance & Docs. Org-chart framing is intentional — it makes the demo legible to an HR audience. **Naming (locked 2026-06-14):** the product/orchestrator is the *Onboarding Assistant*; the human end-user is the *Onboarding Coordinator*. Kept distinct on purpose so the tool isn't named after the person using it — the Assistant does the work, the Coordinator approves. (Internal code identifiers still use `coordinator`/`coord` — a display-name vs. code-identifier split, not a rename of the architecture.)
- **Orchestrator is a state machine, not an agent.** Routing logic is deterministic. This is a feature, not a limitation — it's how we answer "why agents at all?"
- **Agents reason, tools execute.** If a decision is a deterministic rule, it belongs in a tool. If it requires judgment over edge cases (role-specific access, 30-60-90 drafting, compliance combinations), it belongs in an agent. This is the single most important design principle in the project.
- **Handoffs are JSON contracts, not free-text.** Every inter-agent message has a defined schema.
- **3-5 tools per agent maximum.** Larger tool sets degrade agent performance.
- **Human-in-the-loop gates at judgment moments**: plan approval, 30-60-90 sign-off, special access (AWS admin, etc.), unresolvable escalations.
- **Integrations are mocked.** HRIS, ITSM, calendar = JSON files. Do not propose building real ones.

---

## Tech stack (locked in)

- **Agent framework:** OpenAI Agents SDK (Python). Do not suggest LangChain, LangGraph, CrewAI, or AutoGen.
- **Runtime LLM:** GPT-4o via OpenAI API. Do not suggest Claude/Anthropic for the runtime — the strategic framing for the interview is Microsoft/OpenAI alignment. (Claude Code is the build tool, separate question.)
- **Frontend:** ~~Streamlit~~ → **hand-built HTML/CSS/JS** (vanilla, no build step). *Superseded 2026-06-14 (Yuyan's call):* Streamlit's generic widget look read as a technical admin tool, not a purpose-built product for a non-technical HR coordinator. A hand-built frontend lets the agent flow, handoffs, and the two HITL shapes render exactly as designed. FastAPI (already locked) serves it.
- **Backend:** Python + FastAPI (kept thin — HTTP ⇄ orchestrator pause/resume; no business logic).
- **Data:** JSON files for mock candidates, org data, calendars.

---

## Demo invariants — P0 must work end-to-end

The interviewer will see these. If any break, the demo fails. See `3_PRD.md` §7 for full acceptance criteria.

**P0 — required:**

1. **Scenario A — single happy path run.** Sarah Chen (Sr Engineer, Seattle, FTE, starts in 2 weeks) flows through all four agents. Dashboard shows reasoning traces. HITL gates trigger and resolve cleanly for: plan approval (one consolidated plan), AWS special access, 30-60-90 sign-off, welcome message review.
2. **Scenario B — different profile, different reasoning (hero moment).** Marcus Webb (Account Executive, London, contractor, starts in 3 weeks) runs after Sarah. Same four agents produce visibly different outputs (standard laptop + Salesforce, sales-shaped 30-60-90, UK contractor docs incl. IR35, welcome message scheduled rather than ready-to-send). The narrative is "same agents, different reasoning" — narrate the difference against Scenario A. **Sequential runs are the default**; side-by-side two-column rendering is a stretch goal, not P0.
3. **Dashboard never crashes.** Agent failures surface as readable messages, not stack traces.

**P2 — stretch, build only if P0 is stable with time to spare:**

4. Scenario C — manager calendar fully booked → Manager Prep escalates with proposed alternative.
5. Scenario D — malformed profile → graceful error surfacing.
6. Side-by-side rendering of Scenarios A and B in two dashboard columns.

## HITL gates (locked in)

Five gates the system must support. Don't add others without flagging:

1. **Plan approval** — one consolidated plan from the Assistant covering all four agents' intended actions, approved in one click. **Not** four separate sub-plan approvals — the consolidated framing is the orchestrator's value proposition made visible.
2. **Special access** — IT Provisioning pauses on AWS, admin, or sensitive systems. This is a **binary grant/deny decision** *(reshaped 2026-06-14)*: the coordinator is the designated approver, and there's nothing to reword, so the gate shows **Approve / Deny** — not the approve/edit/escalate set of the content-review gates. Denying doesn't halt onboarding (the hire just doesn't get that grant); it records the denial. This makes **three** HITL shapes, each fitting its decision type: *content-review* (approve/edit/escalate — plan, 30-60-90, welcome), *binary decision* (approve/deny — special access), and *alert* (acknowledge/take-action — readiness).
3. **30-60-90 review & send to manager** *(workflow reframed 2026-06-14)* — Manager Prep produces a *draft* 30-60-90 (plus intro meeting + buddy); the Assistant packages it into an auto-drafted cover note to the **hiring manager**, folding the intro and buddy into one note (order: general message → intro → buddy → draft 30-60-90 → checklist). The coordinator reviews and **sends it to the manager**, who then owns and customizes the plan. The 30-60-90 is explicitly the manager's to make their own — *not* a finished plan pushed to the new hire. (Internal gate id stays `30_60_90_signoff`; the display is "Review & send to [manager]" — the same code-id-vs-display-name split as coordinator/Assistant.)
4. **Welcome message review** — the Assistant drafts a personalized welcome message; surfaces for approval; sends (or schedules send) at most 2 weeks before the start date.
5. **Readiness-at-risk summary** — at T-3 days before start, dashboard surfaces a readiness summary if anything is outstanding. This is the gate that catches the "no laptop on day one" failure mode the product exists to prevent.

---

## Testing

**Write unit tests that protect the demo invariants above.** This is not about general code coverage — it's about ensuring the four scenarios that the interviewer will see continue to work as code evolves through the week.

Minimum test coverage:
- Each agent produces valid output schema for at least 2 input profiles (engineer, sales contractor).
- The orchestrator routes the right agents in the right order for each profile type.
- The HITL gate triggers when an agent requests special access.
- The side-by-side comparison run produces distinct (non-identical) outputs for the two profiles.
- The calendar edge case produces an escalation, not a crash.

Run tests before declaring any change complete. If you change agent prompts or handoff schemas, re-run the full test suite — prompt changes can silently break downstream parsing.

---

## How to work in this repo

- Prefer editing existing files over creating new ones.
- When you make a non-trivial decision, write a one-line note in the relevant file or in your response explaining *why this over the alternative*.
- Do not add features beyond the one-week build plan without flagging.
- Do not add production-style error handling, retry logic, observability, or auth scaffolding unless it serves a demo invariant.
- Keep the code readable on a screen during a walkthrough — short functions, clear names, minimal nesting.
