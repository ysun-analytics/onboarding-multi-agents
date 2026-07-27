# GitHub Interview Context & Onboarding Agent Product Idea

## The Interview

**Company:** GitHub (Microsoft-owned)
**Role:** Senior AI Transformation Manager, HR (Req 2026-5162)
**Hiring Manager:** Andrew Stonehill-Brooks, Sr. Director, People Consulting
**Interview Format:** 45-minute conversation
**Focus:** Walk through specific examples of agents you've built, including how you approached the build and the underlying technical decisions. Andrew wants to understand hands-on experience and technical capabilities in building agent-based solutions for HR use cases. Be ready to share/show details on HOW you built.

---

## The Product: HR Onboarding Orchestration Agent

### Problem Statement

When someone gets hired at a mid-market company (500-5,000 employees), onboarding involves 8-12 people and systems. HR enters the new hire in the HRIS. IT provisions a laptop and accounts. The manager creates a 30-60-90 plan. Facilities assigns a desk. L&D enrolls them in training. Payroll sets up direct deposit. This is all coordinated manually through emails and Slack messages. Things get dropped constantly. New hires show up on day one with no laptop and no access.

### Solution

A multi-agent orchestration system where specialized AI agents handle each domain of the onboarding process, coordinated by a central orchestrator, with human-in-the-loop checkpoints at high-judgment moments.

### Why This Idea

- Every company hires and onboards. The pain is universal.
- The recruiting AI space is crowded (Paradox, Gem, Ashby, HireVue). Onboarding orchestration is wide open.
- Directly relevant to GitHub's People Consulting team.
- ROI is measurable: time to productivity, reduced day-one failures, HR coordinator hours saved.


### Architecture: Four Agents, One Orchestrator

**Agent 1: Onboarding Coordinator (Orchestrator)**
- Receives the new hire profile (name, role, team, location, start date, employment type)
- Determines which tasks need to happen based on role/location/type
- Delegates to specialized agents
- Tracks overall onboarding status
- Escalates blockers to HR coordinator
- Tools: get_new_hire_profile, update_onboarding_status, escalate_to_human, get_task_status

**Agent 2: IT Provisioning Agent**
- Handles laptop request, software access, account creation, security group assignment
- Checks if the role requires special access (engineering vs. sales vs. finance) and adjusts
- Flags items requiring manager approval (e.g., AWS credentials, admin access)
- Tools: provision_laptop, create_accounts, assign_security_groups, request_special_access, check_provisioning_status

**Agent 3: Manager Prep Agent**
- Generates a draft 30-60-90 day plan tailored to the role
- Checks the manager's calendar and schedules an intro meeting
- Identifies a recommended onboarding buddy from the team based on tenure and role proximity
- Sends the manager a prep checklist
- Tools: generate_30_60_90_plan, check_calendar, schedule_meeting, find_onboarding_buddy, send_manager_checklist

**Agent 4: Compliance & Docs Agent**
- Determines which documents need to be completed based on role, location, and employment type (full-time vs. contractor, US vs. international)
- Tracks document completion status
- Sends reminders for outstanding items
- Tools: get_required_documents, check_document_status, send_reminder, flag_overdue_documents

### Handoff Logic

Sequential pipeline with parallel branches:

1. Coordinator receives new hire profile
2. Coordinator kicks off IT Provisioning and Compliance & Docs in parallel (both can start immediately)
3. Once IT confirms basic provisioning, Coordinator triggers Manager Prep (manager needs to know what tools/access the new hire will have)
4. All agents report status back to Coordinator
5. Coordinator surfaces the complete onboarding status to the HR coordinator dashboard

### Human-in-the-Loop Gates

- Recruiter/HR coordinator reviews and approves the onboarding plan before agents begin execution
- Manager approves the 30-60-90 day plan before it's shared with the new hire
- IT provisioning of special access (admin, AWS, sensitive systems) requires manager approval
- Escalation to HR when agents encounter situations they can't resolve

### Design Decision Rationale (talking points for interview)

"The first question I asked myself was whether this should be agents at all. A lot of onboarding is deterministic workflow — if you're a contractor in NY, you need these three documents. You don't need an LLM for that. I used agents specifically at the points where the work requires judgment: deciding what access a specific role needs, drafting a 30-60-90 tailored to the team and the person, reasoning over compliance edge cases. The orchestrator itself is closer to a state machine than an agent. The bar for 'this should be an agent' was: would a hard-coded rule embarrass us six months from now when the edge cases pile up?"

"I put human gates at the judgment moments, not the mechanical ones. Provisioning a standard laptop is safe to automate. Granting AWS admin access requires a human to decide. The distinction isn't about technical capability, it's about risk tolerance and organizational trust."

"I structured handoffs as JSON contracts between agents because unstructured text creates downstream parsing failures. Each agent knows exactly what data format it receives and produces."

"I gave each agent 3-5 tools maximum. Research shows agent performance degrades with larger tool sets. Narrow, focused tools lead to better decisions."

### Demo Walkthrough Scenario

**Warm-up: single happy path (~5 min)**

"Meet Sarah Chen. She's a new Senior Software Engineer starting in two weeks, reporting to James in the Platform team, based in Seattle."

- Input Sarah's profile into the system
- Coordinator Agent kicks off and recognizes she's an engineer, routes to IT Provisioning first (engineers need access before day one)
- IT Agent provisions a MacBook Pro, requests GitHub Enterprise access, adds her to Platform team Slack channels, flags that she needs AWS credentials (requires manager approval) -- human-in-the-loop gate triggers
- Manager Prep Agent pulls James's calendar, drafts a 30-60-90 plan tailored to a senior platform engineer, identifies Tom as onboarding buddy based on team tenure
- Compliance Agent determines she needs I-9, W-4, and IP assignment agreement
- Dashboard shows all of this in real time with status indicators, reasoning traces, and approval buttons

**Hero moment: side-by-side comparison run (~5 min)**

Run two profiles simultaneously in two columns of the dashboard: Sarah (Sr Engineer, Seattle, FTE) on the left, a London sales contractor on the right. Same four agents, dramatically different reasoning traces and outputs:

- IT Agent: MacBook Pro + GitHub Enterprise + AWS request vs. standard laptop + Salesforce + Gong, no engineering systems
- Manager Prep Agent: 30-60-90 anchored on shipping platform infrastructure vs. anchored on pipeline and quota ramp; different buddy logic (tenure + skill proximity vs. territory overlap)
- Compliance Agent: I-9 + W-4 + IP assignment vs. UK Right to Work + contractor MSA + IR35 status check
- Coordinator: parallel branches kick off in different orders based on role urgency

This is the moment that proves it's not a script — same agents, the *reasoning* adapts to the input. Narrate the traces side-by-side as they run.

**Edge case live (~3 min):** Re-run Sarah's flow with James's calendar fully booked for week one. Manager Prep Agent escalates with a proposed alternative (delegate intro meeting to skip-level, or push first 1:1 to day 4). Shows HITL working as designed.

**Additional test scenarios to prepare as backups:**
- A contractor in New York (limited access, different employment docs)
- An executive hire (elevated provisioning, board-level compliance docs)

### Tech Stack

- **Agent Framework:** OpenAI Agents SDK (Python)
- **LLM:** GPT-4o (via OpenAI API, ~$5-10 in credits for development and demo)
- **Frontend:** Streamlit (recruiter dashboard)
- **Backend:** Python + FastAPI
- **Data:** Mock candidate profiles, org data, calendars as JSON files
- **Candidate search:** OpenAI embeddings for semantic matching (optional)
- **Repo:** GitHub (clean README, architecture diagram, recorded backup demo video)
- **Build tool:** Claude Code (to write the code)

Note: GitHub is Microsoft-owned/OpenAI ecosystem. Building on OpenAI's stack is strategically aligned. Use Claude Code as the development tool, OpenAI as the runtime LLM.

### One-Week Build Plan

- **Day 1:** Write PRD and architecture doc. Define all four agents' instructions, tools, and handoff contracts. Create mock data (5-6 new hire profiles across different roles/locations).
- **Day 2:** Build Agent 1 (Coordinator) and Agent 2 (IT Provisioning) with tools. Get the first handoff working.
- **Day 3:** Build Agent 3 (Manager Prep) and Agent 4 (Compliance). Wire up all handoffs.
- **Day 4:** Build the Streamlit dashboard: new hire input form, pipeline view, agent reasoning traces, approval checkpoints.
- **Day 5:** Test with different scenarios (engineer in Seattle, sales rep in London, contractor in NYC). Show agents adapting decisions based on inputs.
- **Day 6:** Polish UI, add edge case handling, clean up repo and README, write architecture diagram.
- **Day 7:** Rehearse walkthrough. Record a backup video demo.

### Interview Narrative

"I built this in a week to demonstrate how I think about agent architecture. The integrations are mocked, but the orchestration is real. In production, you'd swap the mock tools for MCP connections to your HRIS, IT ticketing system, and calendar. The agent logic, handoff design, and human-in-the-loop gates wouldn't change."

"Onboarding is one of the most operationally complex, cross-functional workflows in People teams. A sourcer spends hours coordinating across IT, managers, and compliance. I built a system where specialized agents handle each domain, with human checkpoints at the high-judgment moments, so the HR coordinator stays in control of quality while agents handle the coordination."

