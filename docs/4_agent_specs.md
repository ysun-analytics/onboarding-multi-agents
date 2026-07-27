# Agent Specifications

This is the implementation-level spec for the four agents and the orchestrator. It's the document you (and Claude Code) work from when writing the code on Day 2.

Companion docs: `3_PRD.md` (what to build and why), `2_agent_concepts_and_learning_guide.md` (concept refresher), `CLAUDE.md` (locked-in ground rules).

---

## 0. Conventions and shared concepts

A short concept refresher first, because the rest of the doc depends on these terms.

### Structured outputs (vs. free-text agents)

Every agent in this system returns a **typed JSON object**, not free-form prose. In code, this is enforced by Pydantic models passed to the OpenAI Agents SDK's `output_type` parameter.

**Why typed outputs:**
- Downstream code can read the result without parsing English.
- The model is constrained to fill the schema, which catches hallucinated fields.
- Reasoning traces (the natural-language "why") live in a dedicated `reasoning` field, so they're visible without polluting the structured data.

**Alternative considered:** free-text outputs parsed by a second LLM call. Rejected because it's slower, more expensive, and introduces a second failure point.

### Handoff contracts

When one agent's output becomes another agent's input, the shape of that data is a **handoff contract**. Both sides agree on the schema in advance. In this system, contracts are Pydantic models; in the doc below they're shown as TypeScript-like type signatures for readability.

**Why explicit contracts:** without them, a small change in one agent's output silently breaks the next. With them, schema mismatches surface as validation errors immediately, not as garbled behavior three steps later.

### Tools

A tool is a function the LLM can choose to call. The LLM sees the tool's name, description, and parameter schema, and decides when to invoke it. The tool's actual implementation runs in Python and returns a value to the LLM.

**Per-agent tool budget: 3-5 tools.** More than that and the agent's tool selection accuracy drops (this is empirically observed in agent research and a common interview talking point).

### The orchestrator is not an agent

The Onboarding Assistant is implemented as a **Python state machine**, not an LLM-driven agent. Its routing logic — *who runs when, in what order, in parallel or sequentially* — is deterministic. It does, however, use the LLM directly for two specific content-generation tasks where judgment is required: rendering the consolidated plan in natural language and drafting the welcome message. Everything else is `if/else`.

**Why this matters in the interview:** when asked "why agents at all?", the answer is that agents are reserved for judgment-heavy work. Routing is a rule, not a judgment, so it doesn't get an LLM.

### HITL response model: decision gates and alerts

HITL touchpoints come in two structurally different shapes. They are not interchangeable.

**Decision gates (three actions).** Used when an agent proposes a decision and the coordinator must approve, edit, or push back before the system proceeds.

- **Approve** → proceed.
- **Edit** → coordinator directly modifies the structured output (toggle an action off, change a date, override a recommendation). Bypasses the LLM. The edited (and thereby approved) output becomes the system of record, and the flow proceeds.
- **Escalate** → hand the item to a *person*: raise a servicedesk ticket (Jira Service Management / ServiceNow) or contact the manager (Slack / email). Used when the decision needs someone other than the coordinator. Escalate does **not** advance the flow and does **not** re-run the agent — it routes the item out and leaves the gate open so the coordinator can still approve once the person responds. *(In the demo these two routes are honest, deliberately-unwired stubs, labelled as such — they double as the integration roadmap.)*

**Alerts (two actions).** Used when the system surfaces a status the coordinator should act on, but there is no agent-generated proposed decision to revise.

- **Acknowledge** → mark seen, accept current trajectory.
- **Take action** → jump to the underlying outstanding task to resolve it.

**Which touchpoints are which:**

| Touchpoint | Type |
|------------|------|
| `plan_approval` | Decision gate |
| `special_access` | Decision gate |
| `30_60_90_signoff` | Decision gate |
| `welcome_message_review` | Decision gate |
| `escalation` | Decision gate |
| `readiness_at_risk` | Alert |

Only `readiness_at_risk` is an alert. Everything else is a decision gate.

**Why three actions, not two, on gates:**
- Binary approve/reject treats the coordinator as a gatekeeper. Three actions treats them as a collaborator — *Edit* for mechanical tweaks the coordinator can make themselves, *Escalate* for when the decision genuinely belongs to someone else (the IT team, the manager).
- *Escalate* keeps the human in control without pretending the system can resolve everything: when a request needs a person, the honest move is to route it to that person, not to loop an LLM against feedback it may be structurally unable to satisfy.

**Design note — why Escalate, not a free-text "request changes" revise loop.** An earlier design had the third action be free-text feedback that *re-ran* the owning agent to produce a revised output, bounded by a 2-revision cap (unbounded revise loops are a known failure mode — the LLM chases its tail when feedback contradicts a hard rule like "skip the I-9" for a US FTE). We replaced it with **Escalate** for two reasons. (1) **Honesty:** in a mocked demo, "the agent revised it" would be theatre; routing to a person is a real, explainable affordance we can show without faking a result. (2) **It matches the coordinator's actual recourse:** when a draft isn't right, their real-world move is to hand it to the manager or open a ticket — not to argue with a model. The latent `request_changes` response type still exists in the contract (§1) but the shipped product surfaces **Approve / Edit / Escalate**.

**Cascade rule:** whatever the coordinator finalizes at a gate (approved as-is or edited) is the version that flows downstream. The gate's finalized output is the contract. Specialists do not re-render or second-guess it.

**Auditability:** every decision the coordinator makes at a gate is recorded — an edit leaves a visible "Approved with your edits" mark, and an escalation records where the item was routed. The coordinator can always see what was decided and why. Trust without auditability is a non-starter for non-technical operators.

**Notation:** throughout this doc, `[HITL: name] ⇄ Coordinator` represents the appropriate response loop for the touchpoint type — three actions for gates, two for alerts.

---

## 1. Shared types

These types appear in multiple agent contracts. Defined once here.

```ts
type EmploymentType = "fte" | "contractor"
type Location = { country: string; city: string }
type RoleFamily = "engineering" | "sales" | "operations" | "finance" | "executive" | "other"

type NewHireProfile = {
  hire_id: string
  full_name: string
  role_title: string                  // human-readable, e.g., "Senior Software Engineer"
  role_family: RoleFamily              // routable category, used by deterministic logic
  team: string
  manager_id: string                   // manager_name and other details are resolved via the org roster (mock data)
  location: Location
  employment_type: EmploymentType
  start_date: string                   // ISO 8601
  seniority: "junior" | "mid" | "senior" | "staff" | "principal" | "exec"
}

type AgentStatus = "pending" | "in_progress" | "awaiting_approval" | "complete" | "blocked"

type ReasoningTrace = {
  summary: string          // one-line plain English
  steps: string[]          // the agent's reasoning, step by step
}

type HITLRequest = {
  gate_type: "plan_approval" | "special_access" | "30_60_90_signoff" | "welcome_message_review" | "readiness_at_risk" | "escalation"
  agent: "coordinator" | "it_provisioning" | "manager_prep" | "compliance_docs"
  summary: string                    // one-line for the dashboard card
  proposed_decision: string          // what the agent recommends
  rationale: string                  // why
  alternatives?: string[]            // optional, for escalations
  payload: object                    // gate-specific data
  revision_state: RevisionState      // tracks how many times this gate has been revised
}

// Alerts (only readiness_at_risk) accept acknowledge / take_action. The dashboard
// renders the appropriate button set based on HITLRequest.gate_type.
//
// SHIPPED UI (see §2.7): decision gates surface Approve / Edit / Escalate. `request_changes`
// is retained below as a latent type but is NOT surfaced — Escalate (route to a person: a
// Jira/ServiceNow ticket, or the manager over Slack/email) replaced the free-text revise loop.
// Escalate is a client-side routing affordance and has no backend response action of its own.
type HITLResponse =
  | { action: "approve"; coordinator_note?: string }
  | { action: "edit"; edited_payload: object; coordinator_note?: string }
  | { action: "request_changes"; feedback: string }   // latent — not surfaced in the shipped UI
  | { action: "acknowledge"; coordinator_note?: string }
  | { action: "take_action"; target_task_id: string }

type RevisionState = {
  revision_count: number                 // 0 on first surfacing; capped at 2 before forced escalation
  history: {
    revision: number
    reasoning: ReasoningTrace
    coordinator_feedback?: string        // populated when prior action was "request_changes"
  }[]
}
```

---

## 2. Onboarding Assistant (orchestrator)

**Implementation:** Python state machine + two LLM calls.

### 2.1 State machine routing logic

```
1. Receive NewHireProfile.
2. validate_profile(profile) → if invalid, surface error, halt.
3. Build OnboardingPlan deterministically from profile attributes.
4. LLM call #1: render_plan_summary(plan, profile) → natural language summary.
5. Surface HITL plan_approval gate. Halt until coordinator approves.
6. On approval: invoke IT Provisioning and Compliance & Docs IN PARALLEL.
7. Wait for IT Provisioning to report at least "basic provisioning confirmed".
8. Invoke Manager Prep.
9. Collect all specialist outputs as they complete.
10. LLM call #2: draft_welcome_message(profile, specialist_outputs) → personalized welcome message.
11. Surface HITL welcome_message_review gate.
12. On approval: if start_date is within 14 days, mark message as ready-to-send; otherwise schedule for start_date - 14 days.
13. Schedule readiness_at_risk check for start_date - 3 days. If any task is still outstanding at that time, surface HITL readiness_at_risk gate.
14. When all tasks complete → mark onboarding complete.
```

### 2.2 LLM call #1 — Plan summary generation

**System prompt:**
```
You are the Onboarding Coordinator. You have just generated an onboarding plan for a new hire by applying rules to their profile. Your job now is to render that plan as a clear, scannable summary the HR Onboarding Coordinator can review in under 30 seconds.

For each of the four specialist agents, write:
- Two to three bullets covering the most important actions they will take.
- A single line naming which HITL approval gates will surface during their work.

Use plain English. The reader is non-technical. Do not invent actions that are not in the plan you were given. Do not editorialize or recommend changes — your job is to render, not to advise.
```

**Input:** `{plan: OnboardingPlan, profile: NewHireProfile}`
**Output type:** `PlanSummary`

```ts
type PlanSummary = {
  reasoning: ReasoningTrace
  it_provisioning: { actions: string[]; gates: string[] }
  manager_prep:    { actions: string[]; gates: string[] }
  compliance_docs: { actions: string[]; gates: string[] }
  coordinator:     { actions: string[]; gates: string[] }
}
```

### 2.3 LLM call #2 — Welcome message drafting

**System prompt:**
```
You are the Onboarding Coordinator drafting a personalized welcome message from the hiring manager and team to a new hire.

The message must:
- Address the new hire by first name.
- Reference their specific team and role.
- Name their onboarding buddy (provided in input).
- Mention 2-3 concrete things they can expect on day one (provided in input).
- Convey warmth without sounding corporate or generic.
- Be 120-180 words. Not longer.

The message must NOT:
- Invent details about the team, company, or buddy beyond what is provided.
- Make promises about compensation, equity, or HR matters.
- Include calendar invites, document attachments, or anything beyond plain text.
```

**Input:** `{profile: NewHireProfile, buddy_name: string, day_one_logistics: string[]}`
**Output type:** `WelcomeMessageDraft`

```ts
type WelcomeMessageDraft = {
  reasoning: ReasoningTrace
  subject_line: string
  body: string
  send_strategy: "send_now" | "schedule"
  scheduled_send_date?: string  // ISO 8601, populated if send_strategy = "schedule"
}
```

### 2.4 Tools

The Assistant (Python code, not LLM) calls these directly. They are not exposed to an LLM as a tool surface — they are plain functions.

```python
validate_profile(profile: NewHireProfile) -> ValidationResult
update_onboarding_status(hire_id: str, status_update: StatusUpdate) -> None
escalate_to_human(hire_id: str, request: HITLRequest) -> None
get_task_status(hire_id: str) -> dict[str, AgentStatus]
draft_welcome_message(profile: NewHireProfile, buddy: str, logistics: list[str]) -> WelcomeMessageDraft
draft_manager_note(profile: NewHireProfile, manager_name: str, mp: ManagerPrepResult) -> ManagerNoteDraft
```

`draft_welcome_message` and `draft_manager_note` wrap LLM calls #2 and #3 (the welcome message to the new hire, and the cover note that hands the draft 30-60-90 to the manager). LLM call #1 is `render_plan_summary`, called when the plan is built. The other four functions above are pure Python. *(There is no `revise_plan_summary`: the free-text revise loop it once backed was replaced by Escalate — see §0 and §2.7.)*

### 2.5 Handoffs

- **To IT Provisioning:** `{profile: NewHireProfile}` (the full profile; IT decides what's relevant)
- **To Manager Prep:** `{profile: NewHireProfile, provisioning_summary: ProvisioningSummary}` (Manager Prep needs to know what tools the new hire will have)
- **To Compliance & Docs:** `{profile: NewHireProfile}`

### 2.6 Design notes for the interview

- "I made the orchestrator a state machine because routing is a rule, not a judgment. Using an LLM here would add latency and non-determinism without adding capability."
- "The two LLM calls inside the orchestrator are for content generation (plan summary, welcome message) where natural language is the product. That's where LLMs earn their keep."
- "The consolidated plan is the orchestrator's value proposition made visible. If I'd let each agent surface its own plan, I'd be putting the coordinator back into the role of stitching the picture together — which is exactly what the system is supposed to eliminate."

### 2.7 The three-action decision gate (Approve / Edit / Escalate)

When the `plan_approval` HITL gate surfaces, the coordinator chooses one of the three actions defined in §0. Plan approval is the canonical implementation; the other decision gates (special access, 30-60-90 review-&-send, welcome message review) follow the same shape.

**Action 1 — Approve.** The Assistant proceeds with the gated output as-is. For plan approval, the specialist agents are invoked with the approved plan as input.

**Action 2 — Edit.** The coordinator directly modifies the gated output in the dashboard — toggles an action off, changes a date, rewrites the welcome message body, adjusts a recommendation. No LLM call: the edit is the coordinator's, applied as-is. The edited output is *also* an approval (an approval of *their* version), so the flow proceeds, and the card carries an "Approved with your edits" badge so the change is visible after the fact. The edited output becomes the system of record passed downstream.

**Action 3 — Escalate.** The coordinator hands the item to a *person* — because some decisions aren't theirs to make. The dashboard offers two routes:
- **Raise a servicedesk ticket** → in production, a **Jira Service Management / ServiceNow** ticket to the IT team.
- **Contact the manager** → in production, a **Slack** message or email to the hire's manager to weigh in.

Escalate is a *routing* affordance, not a revision: it does **not** re-run the agent and does **not** advance the flow. It records that the item was handed off and leaves the gate open, so once the person responds the coordinator can still Approve (or Edit). In the demo both routes are deliberately **unwired stubs**, labelled plainly ("nothing was actually sent") — honest about what's mocked, and a ready-made roadmap for the real integrations.

**Cascade.** Whatever is finalized at the gate — approved as-is or edited — is what flows downstream to IT Provisioning, Compliance & Docs, and Manager Prep. The handoffs in §2.5 use the finalized output, not the original.

**Pattern reuse across the decision gates.** The same three-action surface applies to every decision gate; the alert (`readiness_at_risk`) is the only two-action touchpoint.

| Touchpoint | Type | On Escalate, routes to |
|------------|------|------------------------|
| plan_approval | Decision gate | IT servicedesk ticket *or* the manager |
| special_access | Decision gate | IT servicedesk ticket (grant/deny the access) *or* the manager |
| 30_60_90_signoff (review & send) | Decision gate | the manager (it's their plan to own) *or* a ticket |
| welcome_message_review | Decision gate | the manager *or* a ticket |
| escalation (e.g. unfamiliar jurisdiction) | Decision gate | the manager *or* a ticket — the agent has already proposed a best-effort option |
| readiness_at_risk | **Alert** | N/A — two-action surface (Acknowledge / Take action). Computed deterministically over current task state; no LLM call. |

### 2.8 Design notes on HITL (for the interview)

- "I designed HITL as a three-action surface — Approve, Edit, Escalate — rather than the usual binary approve/reject. Binary approval treats the human as a gatekeeper; three actions treats them as a collaborator. *Edit* lets them fix a draft themselves; *Escalate* lets them route a decision that genuinely isn't theirs to someone who owns it."
- "Escalate replaced an earlier free-text 'request changes' loop that re-ran the agent. I cut it deliberately. In a mocked demo, 'the agent revised it' is theatre — and worse, an unbounded revise loop is a real failure mode where the LLM chases its tail against feedback that contradicts a hard rule (e.g. 'skip the I-9' for a US FTE). Routing to a person is the honest, real-world recourse, and I'd rather show something true than fake a revision."
- "Escalate doesn't advance the flow — it leaves the gate open. That's intentional: handing an item to a person doesn't resolve it, so the system shouldn't pretend it did. The coordinator stays in control and approves once the person responds."

---

## 3. IT Provisioning Agent

**Implementation:** OpenAI Agents SDK `Agent` with tools and structured output.

### 3.1 System prompt

```
You are the IT Provisioning Agent for a mid-market company's onboarding system.

Your job: given a new hire profile, decide what hardware, software, system access, and security group memberships they need, then execute that provisioning by calling your tools.

How to think about provisioning:
- ENGINEERING roles: MacBook Pro, GitHub Enterprise, IDE licenses, role-appropriate Slack channels, dev tools (CI, observability, error tracking). Senior engineers often need read access to cloud consoles for debugging.
- SALES roles: standard laptop, Salesforce, Gong, Outreach, sales-team Slack channels. Account Executives need territory/quota tooling.
- OPERATIONS / FINANCE: standard laptop, role-specific SaaS (HRIS for HR, NetSuite for finance).
- EXECUTIVES: elevated provisioning, may require executive admin involvement.

Adjust by employment type:
- CONTRACTORS: limited access. No admin rights. No production system access. Time-bounded credentials. No equity-tracking systems.
- FTE: full standard provisioning per role.

Adjust by location:
- Hardware shipping: international hires may need 5-10 business days of lead time. Flag if start date is too close.
- Regional accounts: create accounts in the appropriate regional tenant (EU vs US data residency).

FLAG FOR HUMAN APPROVAL (do not provision automatically) any request involving:
- Cloud credentials beyond read-only (AWS, GCP, Azure write or admin)
- Admin or root access to any production system
- Access to PII, financial, or legal data systems
- Access to security tooling (SIEM, secrets managers)
- Any access that grants the ability to move money or change customer-facing state

When you finish, produce a ProvisioningResult with a clear natural-language reasoning trace. The reader is a non-technical Onboarding Coordinator — explain your decisions in plain English.

Do not exceed the tools you've been given. Do not invent system names. If you're unsure whether a system applies to a role, omit it and note the uncertainty in your reasoning.
```

### 3.2 Input contract

```ts
type ITProvisioningInput = {
  profile: NewHireProfile
}
```

### 3.3 Output contract

```ts
type ProvisioningResult = {
  reasoning: ReasoningTrace
  hardware: { item: string; status: AgentStatus; notes?: string }
  software_access: { system: string; access_level: string; status: AgentStatus }[]
  security_groups: { group: string; status: AgentStatus }[]
  special_access_requests: {
    system: string
    requested_access: string
    rationale: string
    status: "awaiting_approval"
  }[]
  warnings: string[]   // e.g., "International shipping may not arrive by start date"
}
```

### 3.4 Tools

```ts
provision_laptop(hire_id: string, model: string, ship_to: Location) -> {ticket_id: string, eta: string}
create_account(hire_id: string, system: string, access_level: string) -> {account_id: string, status: string}
assign_security_group(hire_id: string, group: string) -> {status: string}
request_special_access(hire_id: string, system: string, access_level: string, rationale: string) -> {request_id: string, status: "pending_approval"}
check_provisioning_status(hire_id: string) -> {tasks: list[{name: string, status: AgentStatus}]}
```

Five tools, at the upper limit of the per-agent budget. All return mocked data in the demo.

### 3.5 Handoff

Returns `ProvisioningResult` to the orchestrator. The orchestrator passes a derived `ProvisioningSummary` (subset of fields relevant to Manager Prep) downstream.

```ts
type ProvisioningSummary = {
  hardware_summary: string                  // "MacBook Pro, shipping by [date]"
  systems_provisioned: string[]             // ["GitHub Enterprise", "Slack: #platform", ...]
  pending_special_access: string[]          // ["AWS read access"]
}
```

### 3.6 Design notes for the interview

- "I made the role-family enum coarse on purpose (engineering, sales, etc.) so the agent can apply broad rules and rely on its system prompt for nuance. Encoding every role variation as a separate enum would push complexity from the LLM (good at fuzzy categorization) into the type system (bad at fuzzy categorization)."
- "Special access is a *typed* output, not just a flag. That's because the dashboard needs structured data to render the HITL card, including the agent's rationale. Free-text 'flag this' would lose the why."
- "I gave the agent five tools rather than building one mega-tool because each tool has a single clean responsibility. Smaller tools = better LLM tool selection accuracy."

---

## 4. Manager Prep Agent

### 4.1 System prompt

```
You are the Manager Prep Agent. Your job is to prepare the hiring manager for a new direct report by producing four artifacts:

1. A **draft** 30-60-90 day plan — a starting proposal the *manager* will own, edit, and make their own. It is NOT a finished plan, and it does NOT go straight to the new hire.
2. A scheduled intro meeting in the manager's calendar.
3. An onboarding buddy **suggestion** (a recommendation the manager can accept or swap — not a final assignment), with reasoning.
4. A prep checklist for the manager.

How to think about the 30-60-90:
- It's a DRAFT the manager owns: opinionated enough to be useful, not so rigid it leaves them nothing to adjust. Speak to the manager in the reasoning ("here's a draft ramp you can tailor…").
- Anchor it in the new hire's specific role and team. Generic plans signal lack of care.
- 30 days: ramp, context, relationships, low-stakes contributions.
- 60 days: own a small project end-to-end; build a working model of how the team operates.
- 90 days: ship something visible; have a point of view on what the role should accomplish.
- For engineering roles: anchor in shipping infrastructure or features.
- For sales roles: anchor in pipeline ramp, territory familiarization, quota readiness.
- For executive roles: anchor in stakeholder mapping and 100-day strategy artifacts.

How to pick a buddy:
- Same team, ideally similar function or adjacent skillset.
- Tenure: 1-3 years is the sweet spot (long enough to know things, recent enough to remember being new).
- Calendar availability matters — check before recommending.
- Avoid the manager and skip-level.

If the manager has zero calendar availability in the first week:
- Do NOT crash or return an empty result.
- Escalate with at least one proposed alternative: skip-level intro, push first 1:1 to day 4, async intro doc.

Always include a natural-language reasoning trace for a non-technical reader.
```

### 4.2 Input contract

```ts
type ManagerPrepInput = {
  profile: NewHireProfile
  provisioning_summary: ProvisioningSummary
}
```

### 4.3 Output contract

```ts
type ManagerPrepResult = {
  reasoning: ReasoningTrace
  thirty_sixty_ninety: {
    thirty_days: string[]
    sixty_days: string[]
    ninety_days: string[]
    status: "draft_awaiting_signoff"
  }
  intro_meeting: {
    proposed_time: string         // ISO 8601
    duration_minutes: number
    status: AgentStatus
  } | { status: "blocked"; reason: string; alternatives: string[] }
  buddy_recommendation: {
    name: string
    tenure_years: number
    rationale: string
    status: AgentStatus
  }
  manager_checklist: string[]
}
```

Note the union type on `intro_meeting`: the "happy path" case and the "blocked with alternatives" case are different shapes. This is intentional — it forces the dashboard to render the escalation case differently rather than treating an empty `proposed_time` as a soft failure.

### 4.4 Tools

```ts
check_calendar(manager_id: string, window_start: string, window_end: string) -> {free_slots: list[{start: string, end: string}]}
schedule_meeting(manager_id: string, hire_id: string, slot: object) -> {meeting_id: string, status: string}
find_onboarding_buddy(team: string, hire_role_family: RoleFamily, exclude: list[string]) -> {candidates: list[{name: string, tenure_years: number, role: string, calendar_load: string}]}
send_manager_checklist(manager_id: string, checklist: list[string]) -> {sent: bool}
```

**Four tools — and note what is *not* one.** There is deliberately no `generate_30_60_90_plan` tool. Drafting the 30-60-90 is the agent's *judgment* — the entire reason Manager Prep is an agent and not a rule — so the agent writes it straight into its structured output. Making it a tool would imply it's a deterministic action, which is exactly backwards (see §13 in the build notes).

### 4.5 The hand-off to the manager (cover note + review-&-send gate)

Manager Prep produces the four artifacts above as *structured data*. It does not write the message that delivers them — that's the **Assistant's** job (LLM call #3, `draft_manager_note`, §2.4), keeping the project's split intact: **specialists produce structured results; the Assistant writes the human-facing prose.**

The Assistant packages the four artifacts into one **cover note to the hiring manager**, in a fixed order — *general message → intro meeting → onboarding buddy → draft 30-60-90 → checklist* — folding the intro and buddy into the note's prose so the manager gets one message, not three sub-cards. The coordinator then reviews it at the **`30_60_90_signoff` gate, which surfaces as "Review & send to [manager]"** (Approve / Edit / Escalate, per §2.7). On approval the note goes to the manager, who owns and customizes the draft. The 30-60-90 and the buddy are both *suggestions the manager owns* — the system proposes, the human decides. (The manager's own customization is a downstream step, not simulated in the demo.) *Internal gate id stays `30_60_90_signoff`; the display label is "Review & send" — a code-identifier-vs-display-name split.*

### 4.6 Design notes for the interview

- "Manager Prep is sequenced *after* IT Provisioning because the 30-60-90 references the tools and systems the new hire will have. Drafting it before provisioning is decided produces a generic plan that doesn't reflect reality."
- "The 30-60-90 is framed as a *draft the manager owns*, not a finished plan pushed to the new hire. Same for the buddy — it's a suggestion the manager can swap. That's the product's whole HITL philosophy in miniature: agents propose, humans decide. I changed the workflow to this mid-build because handing a manager a fait-accompli plan is exactly the kind of false automation that erodes trust."
- "Buddy logic is in a tool, not the prompt, because it depends on org data (tenure, calendar load) the LLM doesn't have. The tool returns candidates; the LLM picks and writes the rationale."
- "The intro_meeting union type is one of the small structural choices that pays off in the dashboard — the 'blocked' shape forces an explicit alternative-rendering path, so we can't accidentally treat a scheduling failure as a soft success."

---

## 5. Compliance & Docs Agent

### 5.1 System prompt

```
You are the Compliance & Docs Agent. Given a new hire profile, determine the complete set of documents they must complete before or shortly after their start date, and track completion.

Document requirements depend on the combination of role, location, and employment type. Reason carefully — combinations matter.

US FTE: I-9 (within 3 days of start), W-4, IP assignment agreement, NDA, direct deposit form, benefits enrollment.
US contractor: W-9, contractor MSA, IP assignment, NDA.
UK FTE: Right to Work check, employment contract, P45/P46, NDA, pension auto-enrollment.
UK contractor: Right to Work check, contractor agreement, IR35 status determination.
EU FTE: country-specific employment contract, work authorization, GDPR data processing acknowledgement, country-specific tax forms.
Executive hires (any geography): add equity grant documents, board-level confidentiality, post-employment restrictions where legal.
Sensitive-data roles (finance, HR, legal, security): add role-specific confidentiality and access agreements.

For combinations you have not been given explicit rules for: surface as an escalation with a proposed document set and request human review. Do NOT silently guess.

Track which documents have been sent, signed, and outstanding. Send reminders as the start date approaches. Flag overdue items.

Always produce a clear reasoning trace explaining the combination logic. The reader is non-technical — explain why each document applies.
```

### 5.2 Input contract

```ts
type ComplianceInput = {
  profile: NewHireProfile
}
```

### 5.3 Output contract

```ts
type ComplianceResult = {
  reasoning: ReasoningTrace
  required_documents: {
    name: string
    deadline: string                    // ISO 8601
    status: "not_started" | "sent" | "in_progress" | "completed" | "overdue"
    rationale: string                   // "Required because role is in US and employment is FTE"
  }[]
  escalations: {
    reason: string                      // e.g., "Unfamiliar combination: contractor in Brazil"
    proposed_document_set: string[]
    requires_human_review: true
  }[]
}
```

### 5.4 Tools

```ts
get_required_documents(role_family: RoleFamily, location: Location, employment_type: EmploymentType) -> {documents: list[object], unknown_combinations: list[string]}
check_document_status(hire_id: string) -> {documents: list[{name: string, status: string}]}
send_reminder(hire_id: string, document_name: string) -> {sent: bool}
flag_overdue_documents(hire_id: string) -> {overdue: list[string]}
```

Four tools, comfortably within budget.

### 5.5 Design notes for the interview

- "The compliance combinatorics — role × location × employment_type — are exactly the kind of edge-case-heavy logic where deterministic rules embarrass you six months in. New jurisdictions, new contract types, new sensitive-data role definitions. The agent's reasoning trace makes the logic auditable; a rules engine would have buried it in code."
- "I made 'unfamiliar combination' an explicit escalation, not a silent fallback. Compliance is a domain where 'I don't know' must surface to a human, not get smoothed over by the LLM's tendency to guess."

---

## 6. End-to-end handoff sequence

```
[Profile lands]
  ↓
Assistant.validate_profile  (Python)
  ↓
Assistant.build_plan  (Python rules)
  ↓
Assistant → LLM call #1: render_plan_summary  →  PlanSummary
  ↓
[HITL: plan_approval]  ⇄  Coordinator
  ↓ (approved)
  ├─→ IT Provisioning Agent  →  ProvisioningResult
  │     ↓
  │     [HITL: special_access  if any]  ⇄  Coordinator
  │
  └─→ Compliance & Docs Agent  →  ComplianceResult
        ↓
        [HITL: escalation  if unfamiliar combo]
  ↓
[After IT confirms basic provisioning]
  ↓
Manager Prep Agent (with ProvisioningSummary)  →  ManagerPrepResult
  ↓
[HITL: 30_60_90_signoff]  ⇄  Coordinator
  ↓
Assistant → LLM call #2: draft_welcome_message  →  WelcomeMessageDraft
  ↓
[HITL: welcome_message_review]  ⇄  Coordinator
  ↓
[Scheduled at T-3 days before start_date]
  ↓
[HITL: readiness_at_risk  if anything outstanding]  ⇄  Coordinator
  ↓
[All green → onboarding complete]
```

---

## 7. What to build first (Day 2 sequence)

When coding starts on Day 2, build in this order:

1. **Shared types as Pydantic models.** `NewHireProfile`, `HITLRequest`, the `ReasoningTrace`. Everything else depends on them.
2. **Mock data.** At least Sarah Chen and Marcus Webb. Org rosters, calendars, document templates.
3. **Assistant state machine** — without LLM calls yet. Just routing and stubs.
4. **IT Provisioning Agent** — first real agent. Validates the SDK setup and tool calling end-to-end.
5. **First handoff working: Assistant → IT → Assistant.** This is the integration milestone for Day 2.
6. **Compliance, Manager Prep, LLM calls in the Assistant** — Day 3.
