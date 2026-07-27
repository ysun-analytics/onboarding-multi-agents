# PRD: Onboarding Multi-Agent Orchestration

**Status:** Draft v1
**Owner:** Yuyan Sun
**Purpose:** Interview demo for Senior AI Transformation Manager role, GitHub (Microsoft)
**Build window:** 7 days

---

## 1. Overview

A multi-agent orchestration system that automates the cross-functional coordination of new hire onboarding for mid-market companies. Four specialized AI agents — IT Provisioning, Manager Prep, Compliance & Docs, and an Onboarding Coordinator that routes between them — handle the work that today gets dropped between Slack threads, email chains, and HRIS tickets. An HR Onboarding Coordinator supervises the system through a dashboard, approving high-judgment decisions and intervening only when agents escalate.

This PRD specifies the demo build. Companion documents:
- `1_interview_context_and_product_idea.md` — strategic context and design rationale
- `2_agent_concepts_and_learning_guide.md` — conceptual foundations
- `CLAUDE.md` — engineering ground rules and locked-in decisions

---

## 2. Problem

At mid-market companies (500-5,000 employees), onboarding a single new hire requires coordination across 8-12 people and systems: HR, IT, manager, payroll, facilities, L&D, security, compliance. Today this coordination is manual — emails, Slack pings, spreadsheets, hand-off tickets. The result:

- **Things get dropped.** New hires routinely show up on day one with no laptop, no system access, or no manager intro scheduled.
- **The HR Onboarding Coordinator is the bottleneck.** A single coordinator handles 10-30 hires per month, spending the majority of their time chasing other people.
- **Quality is invisible.** Nobody knows what's been done, what's pending, and what's overdue until something breaks publicly.

This is universal, measurable, and largely unaddressed by existing point solutions. Recruiting tooling (Paradox, Gem, Ashby) ends at the offer letter. HRIS platforms (Workday, BambooHR) track state but don't *do* the work.

---

## 3. Target user

### Primary: The HR Onboarding Coordinator

The person responsible for making sure every new hire's day-one experience is smooth. Operates at the intersection of HR, IT, hiring managers, and compliance.

**Profile:**
- Non-technical. Lives in spreadsheets, Slack, and the HRIS.
- Low tolerance for software that fails opaquely. If the tool breaks, they cannot debug it — they revert to manual coordination and lose trust.
- Optimizes for *no surprises*. Would rather over-confirm than discover a problem at 9am on day one.
- Measured on time-to-productivity, day-one readiness, and new hire satisfaction.

**Jobs to be done:**
1. Make sure nothing falls through the cracks across all the systems and people involved.
2. Know the real-time status of every in-flight onboarding without chasing people.
3. Catch problems early, while there's still time to fix them.
4. Keep hiring managers and new hires informed without manually drafting every update.

### Secondary: The Hiring Manager

The new hire's direct manager. Cares about the new hire being productive quickly. Today receives an "onboarding checklist" email they often ignore until day-of. Wants the prep work done for them.

---

## 4. Goals & non-goals

### Goals (in scope for the demo)

1. Demonstrate that four specialized agents can coordinate an end-to-end onboarding without manual handoffs.
2. Show that the same agent architecture adapts cleanly to dramatically different inputs (engineer vs. sales rep, US vs. international, FTE vs. contractor).
3. Make every agent decision visible and reviewable in the dashboard.
4. Place human-in-the-loop gates at the high-judgment moments (special access, plan approval, escalations) — not at mechanical ones.
5. Be runnable end-to-end as a 45-minute walkthrough without crashes.

### Non-goals (explicit out of scope)

1. **Real system integrations.** HRIS, ITSM, calendar, identity provider connections are all mocked via JSON. Production would use MCP adapters; the demo does not.
2. **Authentication, multi-tenancy, role-based access control.** Single-user demo only.
3. **Persistence across runs.** Each demo run starts from a clean state.
4. **Production-grade error handling, retry, observability, alerting.** Failures surface in the dashboard but are not engineered for resilience.
5. **Bulk onboarding** (multiple hires at once beyond the side-by-side comparison demo).
6. **Offboarding, transfers, or mid-cycle role changes.**
7. **Mobile or responsive UI.** Demo runs on a laptop screen.
8. **Real LLM cost optimization, caching, or rate limiting.** Demo budget is ~$10 of OpenAI credits.

---

## 5. User journey

### 5.1 Happy path, with HITL moments inline

1. **Trigger.** A new hire profile lands in the system (demo: coordinator picks from mock profiles or pastes one in; production: HRIS webhook). The Coordinator Agent reads the profile, validates required fields, and generates a *consolidated* onboarding plan — what each specialist agent will do, in what order, and which gates will trigger.

2. **HITL gate — Plan approval.** Coordinator reviews the consolidated plan in the dashboard. They see, in one view: IT will provision X, Manager Prep will draft Y, Compliance will collect Z, and which gates will surface during execution. **Actions: Approve · Edit · Request changes.** Approve sends the plan downstream as-is; Edit allows direct modifications to specific items; Request changes triggers a revised plan with the coordinator's free-text feedback in context (see §6.6 for the full three-action pattern and §6.6 for why this is one plan, not four).

3. **Parallel execution begins.** IT Provisioning and Compliance & Docs run in parallel. The dashboard shows live status indicators and natural-language reasoning traces ("I'm provisioning a MacBook Pro because the role is Senior Software Engineer; the team's standard is macOS").

4. **HITL gate — Special access.** When IT requests AWS, admin rights, or any sensitive system, a card surfaces with the agent's reasoning ("Senior engineers on Platform team historically need AWS read access for production debugging"). **Actions: Approve · Edit · Request changes.** Edit lets the coordinator narrow the scope (e.g., read-only instead of write); Request changes asks IT to revise the request.

5. **Manager Prep triggers.** Once IT confirms basic provisioning, the Coordinator routes to Manager Prep. The agent drafts the 30-60-90, identifies a buddy with reasoning, and proposes an intro meeting time from the manager's calendar.

6. **HITL gate — 30-60-90 sign-off.** The draft plan surfaces for review before it's shared with the new hire. **Actions: Approve · Edit · Request changes.** Edit allows inline tweaks to specific milestones; Request changes asks Manager Prep to revise the plan with feedback. In the demo, the coordinator acts on behalf of the manager; in production, this routes to the hiring manager.

7. **HITL gate — Welcome message review.** The Coordinator Agent drafts a personalized welcome message (role-aware, team-aware, mentions buddy and first-day logistics). **Actions: Approve · Edit · Request changes.** Edit allows direct text tweaks; Request changes asks the Coordinator Agent to redraft with feedback in context. Send timing: at most 2 weeks before start date — if the start date is further out, the dashboard shows "scheduled to send on [date]"; if within 2 weeks, it sends on approval.

8. **HITL alert — Readiness-at-risk check (T-3 days before start).** The Coordinator Agent surfaces a readiness summary: what's done, what's outstanding, what's at risk of slipping past day one. This is structurally an *alert*, not an approval gate — there's no decision to revise. **Actions: Acknowledge · Take action.** Acknowledge marks the coordinator as having seen and accepted the status; Take action opens the relevant agent's task to resolve the outstanding item (e.g., chase a missing document, re-trigger a stuck provisioning task). This is the gate that catches the "no laptop on day one" failure mode the product exists to prevent.

9. **Confirm readiness.** Dashboard moves to all-green. New hire is day-one ready.

### 5.2 Non-happy paths

- **Missing or malformed profile data.** Coordinator Agent flags the gap during plan generation — e.g., "Start date missing — required before agents can proceed." No specialist runs until the field is provided.
- **Agent escalation mid-flight.** A specialist hits a situation it can't resolve (manager calendar fully booked, unknown document type for a new jurisdiction, vendor system unreachable). It surfaces an escalation card with a *proposed alternative*, not a dead end. Coordinator accepts the alternative, overrides with their own, or marks the task for manual handling.
- **Coordinator rejects a gate.** When the coordinator rejects an approval (e.g., denies AWS access), the agent records the decision in the reasoning trace and proceeds without that item. No retry loops, no nagging.

---

## 6. Functional requirements

### 6.1 Onboarding Coordinator Agent (orchestrator)

**Inputs:** New hire profile (name, role, team, location, start date, employment type, manager).
**Outputs:** Consolidated onboarding plan, routing decisions, status updates, escalations, welcome message draft.

Must:
- Validate the profile and flag missing/malformed fields *before* invoking any specialist agent.
- Generate a single consolidated onboarding plan summarizing what each specialist will do, for one-shot coordinator approval.
- Determine which specialist agents to invoke based on profile attributes (role, location, employment type).
- Kick off IT Provisioning and Compliance & Docs in parallel immediately upon plan approval.
- Trigger Manager Prep once IT provisioning confirms basic access (manager needs to know what the new hire will have).
- Track real-time status of every delegated task.
- Draft a personalized welcome message for the new hire (role-aware, team-aware, references buddy and first-day logistics). Surface for HITL approval. Send (or schedule send for) no more than 2 weeks before the start date.
- Surface a readiness-at-risk summary at T-3 days before start date if any task is outstanding.
- Escalate to the HR Coordinator (human) when an agent reports a blocker it cannot resolve.
- Provide a unified status summary to the dashboard.

Tools: `validate_profile`, `update_onboarding_status`, `escalate_to_human`, `draft_welcome_message`, `get_task_status`.

### 6.2 IT Provisioning Agent

**Inputs:** New hire profile from Coordinator.
**Outputs:** Provisioning plan, access decisions, completion status, special-access flags.

Must:
- Determine hardware (MacBook Pro for engineers; standard laptop for sales/ops) and software access based on role.
- Identify role-specific access (GitHub Enterprise for engineers; Salesforce/Gong for sales; etc.).
- Flag any request requiring special approval (admin access, AWS credentials, sensitive systems) and pause for HITL.
- Adjust provisioning for location (e.g., shipping logistics) and employment type (contractors get limited access).

Tools: `provision_laptop`, `create_accounts`, `assign_security_groups`, `request_special_access`, `check_provisioning_status`.

### 6.3 Manager Prep Agent

**Inputs:** New hire profile, IT provisioning summary, manager identifier.
**Outputs:** Draft 30-60-90 plan, scheduled intro meeting, buddy recommendation, manager prep checklist.

Must:
- Generate a 30-60-90 plan tailored to the role and team (not a generic template).
- Check the manager's calendar and propose an intro meeting time in the first week.
- Recommend an onboarding buddy from the team with reasoning (tenure, skill proximity, calendar availability).
- Send the manager a prep checklist with what they need to do before day one.
- Escalate if the manager has no calendar availability with a proposed alternative.

Tools: `generate_30_60_90_plan`, `check_calendar`, `schedule_meeting`, `find_onboarding_buddy`, `send_manager_checklist`.

### 6.4 Compliance & Docs Agent

**Inputs:** New hire profile (role, location, employment type, start date).
**Outputs:** Required document list, document status, reminders, overdue flags.

Must:
- Determine the correct document set for the combination of role × location × employment type. Examples:
  - US FTE engineer → I-9, W-4, IP assignment, NDA
  - UK FTE sales rep → Right to Work, contract, BPSS check (if applicable)
  - US contractor → W-9, contractor MSA, IP assignment
  - UK contractor → IR35 status check, contractor agreement
- Track which documents have been completed.
- Send reminders for outstanding items as the start date approaches.
- Flag overdue documents to the Coordinator for escalation.

Tools: `get_required_documents`, `check_document_status`, `send_reminder`, `flag_overdue_documents`.

### 6.5 Dashboard

The single interface the Onboarding Coordinator uses. Built for clarity at a glance — a non-technical user must understand state, decisions, and what's being asked of them without prior training.

**Must show:**

- **Profile input panel.** Paste/upload a new hire, or pick one from mock data.
- **Live pipeline view.** Which agents are running, their status (pending / in progress / awaiting approval / complete / blocked).
- **Agent reasoning traces.** For each agent, the natural-language explanation of what it decided and why. Plain English, no JSON dumps in the primary view (advanced toggle for raw output is fine).
- **HITL cards** (two distinct shapes — see below).
- **Failure state.** If an agent errors, show a readable message and what to do next. Never crash.

**Stretch:**
- Side-by-side comparison mode (Scenarios A and B running in two columns). Scenario B's narrative works without it — see §7. Build only if P0 is stable.

**HITL card structure — two shapes, intentionally different:**

1. **Plan approval card (consolidated, fires once per hire).** A single card titled "Onboarding plan for [name] — review and approve." Contains four collapsible sections — one per specialist agent — showing the actions each agent will take and the gates that will surface during execution. **One set of buttons at the bottom: Approve · Edit · Request changes.** One click approves the entire plan. The four-section structure is for *legibility*, not for granular approval. Splitting approval back into four cards would put the coordinator back into the role of stitching the picture together across siloed views — which is precisely the problem the orchestrator exists to eliminate.

2. **Mid-flight gate cards (fire individually as specialist agents surface them).** One card per gate: special access request, 30-60-90 sign-off, welcome message review, readiness-at-risk summary, escalations. Each card shows the agent's recommendation, plain-English rationale, and the same three actions (Approve · Edit · Request changes). These arrive asynchronously as specialist agents complete their work, spread across hours or days — not all at once.

**Target coordinator effort per hire (happy path): 3-5 touchpoints.**

| Profile | Touchpoints | Card sequence |
|---------|-------------|---------------|
| Sarah (US FTE Sr Engineer, AWS needed) | 4 | plan approval → AWS special access → 30-60-90 sign-off → welcome message review |
| Marcus (UK contractor, no special access) | 3 | plan approval → 30-60-90 sign-off → welcome message review |

Compare against today's state: the same hire requires the coordinator to send/receive dozens of Slack messages and emails across IT, the manager, payroll, compliance, and facilities. **8-12 people coordinated manually → 3-4 quick approvals** is the product's central value proposition, and the dashboard is where it becomes visible.

### 6.6 Human-in-the-loop touchpoints

The coordinator interacts with the system through two structurally different touchpoint types:

- **Decision gates** require a coordinator decision before the system proceeds. Three actions: **Approve · Edit · Request changes**.
- **Alerts** surface a status the coordinator should act on. There is no proposed decision to revise. Two actions: **Acknowledge · Take action**.

#### Decision gates (three actions)

1. **Plan approval — one consolidated plan, not four.** Before any specialist runs, the Coordinator Agent presents a single plan summarizing what each of the four agents will do for *this specific new hire*. The coordinator approves once. Design rationale: splitting approval into four sub-plans would put the coordinator back into the role of stitching the picture together across siloed views, which is the exact problem the orchestrator exists to eliminate. The consolidated plan is the orchestrator's value proposition made visible. The plan must include: each agent's intended actions, the gates that will surface mid-flight, and the inputs each agent will use.
2. **Special access.** IT Provisioning pauses on AWS, admin rights, or sensitive systems. Edit lets the coordinator narrow scope (e.g., read-only); Request changes asks IT to revise the request.
3. **30-60-90 sign-off.** Manager Prep surfaces the draft before it's shared with the new hire. Edit allows inline tweaks to milestones; Request changes asks Manager Prep to redraft with feedback.
4. **Welcome message review.** Coordinator Agent surfaces the draft welcome message. Sent (or scheduled to send) at most 2 weeks before start date. Edit allows direct text tweaks; Request changes asks for a redraft.
5. **Escalation.** Any agent that hits an unresolvable situation surfaces it with a proposed alternative — never a dead-end error. Approve accepts the proposed alternative; Edit overrides with the coordinator's own resolution; Request changes asks the agent for a different alternative.

#### Alerts (two actions)

6. **Readiness-at-risk (T-3 days before start).** If any task remains outstanding 3 days before the new hire starts, the dashboard surfaces a readiness summary. Coordinator can **Acknowledge** (mark seen, accept current trajectory) or **Take action** (jump to the outstanding task to resolve it). No revision applies — the summary is a deterministic computation over current task state, not an agent-generated proposal. This is the touchpoint that catches the "no laptop on day one" failure mode the product exists to prevent.

---

## 7. Demo acceptance scenarios

Scenarios A and B are **P0 — required for demo readiness**. Scenarios C and D are **P2 — build only if A and B are functioning smoothly with time to spare**. Each P0 scenario is also a test target.

### Scenario A (P0): Single happy path

**Profile:** Sarah Chen, Senior Software Engineer, Seattle, FTE, reports to James (Platform team), starts in 2 weeks.

**Pass criteria:**
- Coordinator generates consolidated plan → coordinator approves → IT + Compliance kick off in parallel → Manager Prep triggers after IT confirms.
- IT provisions MacBook Pro + GitHub Enterprise + Platform Slack channels; flags AWS access for approval.
- HITL card appears for AWS access with agent reasoning visible.
- Manager Prep produces a Platform-specific 30-60-90, books an intro with James, recommends Tom as buddy with rationale.
- Compliance returns I-9, W-4, IP assignment.
- Coordinator drafts personalized welcome message; HITL approval surfaces; on approval, dashboard shows "ready to send" (within 2-week window).
- Dashboard ends in all-green state.

### Scenario B (P0): Different profile → different reasoning (hero moment)

**Profile:** Marcus Webb, Account Executive, London, contractor, reports to Priya (EMEA Sales), starts in 3 weeks.

The demo narrative is: "watch how the same four agents produce a fundamentally different onboarding for a fundamentally different hire." This is most easily shown by running Scenario A, then running Scenario B, and narrating the differences in the dashboard — no parallel two-column UI required. Side-by-side rendering is a stretch goal, not a requirement.

**Pass criteria:**
- IT Provisioning produces visibly different outputs from Scenario A: standard laptop, Salesforce + Gong + Outreach, no AWS request, no engineering systems.
- Manager Prep produces a sales-shaped 30-60-90 (quota ramp, territory familiarization, first calls) — not platform infrastructure — and applies a sales-appropriate buddy logic.
- Compliance returns UK contractor docs (Right to Work, contractor MSA, IR35 status check) — not US FTE docs.
- Coordinator drafts welcome message; since start date is 3 weeks out, dashboard shows "scheduled to send on [date 2 weeks before start]."
- Reasoning traces make the differences from Scenario A legible when narrated.

### Scenario C (P2 — stretch): Edge case, manager calendar fully booked

Build only if A and B are stable and there is build time remaining.

**Profile:** Sarah Chen, but James has zero calendar availability in week one.

**Pass criteria:**
- Manager Prep Agent does not crash or return an empty result.
- Agent escalates with a proposed alternative (skip-level intro, push first 1:1 to day 4, or async intro doc).
- HITL card surfaces in dashboard with the alternative and a rationale.

### Scenario D (P2 — stretch): Graceful failure

Build only if A and B are stable and there is build time remaining.

**Profile:** Any profile with a deliberately malformed field (e.g., missing start date).

**Pass criteria:**
- System surfaces a readable error in the dashboard ("Start date missing — please provide before agents can proceed").
- No stack trace, no crash, no silent failure.

---

## 8. Success metrics

### For the demo (Day 7)

- All four acceptance scenarios run cleanly in a single 45-minute session.
- Interviewer can articulate, after the walkthrough, what each of the four agents does and why they're separate.
- The "why agents vs. workflow?" question, if asked, has a one-paragraph answer baked into the demo narrative.
- No crashes during the live walkthrough. (Recorded backup video as fallback.)

### For the product (hypothetical, used in interview narrative only)

- Time-to-day-one-readiness: hours saved per hire.
- Day-one failure rate: % of hires showing up without required access/equipment.
- Coordinator capacity: hires/month a single coordinator can handle.

---

## 9. Open questions & risks

### Open questions
- For Scenario B, if we do attempt the side-by-side stretch rendering, do we want a "diff highlight" that visually marks where the two reasoning traces diverged? (Adds UI complexity.)

### Decisions logged
- **Welcome message: in scope.** Coordinator Agent drafts; HITL approval gate; send (or scheduled send) at most 2 weeks before start date.
- **Plan approval: one consolidated plan**, not per-agent sub-plans (see §6.6 rationale).
- **Scenario B does not require side-by-side rendering.** Sequential run + narrated comparison is sufficient.

### Risks
- **GPT-4o reasoning variability.** Same input may produce subtly different reasoning across runs. Mitigation: low temperature, structured outputs, recorded backup demo.
- **Streamlit limitations for the side-by-side view.** Two-column live updates may be janky. Mitigation: prototype this on Day 2, not Day 4, to validate feasibility early.
- **Demo runtime length.** Four agents per profile × two profiles in parallel may take longer than feels good live. Mitigation: cache outputs for the demo profiles; live-run one fresh to show it's real.
