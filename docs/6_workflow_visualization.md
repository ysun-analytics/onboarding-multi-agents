# Workflow Visualization

Three views of the same system, each useful for a different audience and demo moment.

| View | When to use it |
|------|----------------|
| **1. System architecture** | First slide — answers "what are the moving parts?" Good for the architectural-decisions narrative. |
| **2. End-to-end workflow** | Walkthrough slide — answers "how does a hire move through the system?" The detailed picture, with every HITL gate shown. |
| **3. Coordinator timeline** | Product-narrative slide — answers "what does the user actually experience?" The most persuasive view for an HR audience. |

All diagrams use Mermaid syntax. Render natively in GitHub, VS Code (Markdown Preview Mermaid extension), Obsidian, Notion, and most modern markdown viewers. For a polished slide, paste the Mermaid code into [mermaid.live](https://mermaid.live) and export to SVG or PNG.

## Color & shape legend (applies to all diagrams)

| Visual | Meaning |
|--------|---------|
| Yellow rounded box | **Decision gate** (HITL, three actions: Approve / Edit / Request changes) |
| Red rounded box | **Alert** (HITL, two actions: Acknowledge / Take action) |
| Blue box | **LLM call** (agent reasoning or content generation) |
| Gray box | **Deterministic Python** (rules, routing, validation) |
| Green box | **Specialist agent** |
| Stadium shape | Start or end of flow |

---

## 1. System architecture

The static system view. Four specialist agents, one orchestrator state machine, one dashboard, five mock data files.

```mermaid
graph TB
    User([Onboarding Coordinator])
    Dashboard[Streamlit Dashboard]

    subgraph Orchestrator["Coordinator State Machine (Python + 2 LLM calls)"]
        direction TB
        Validate[Validate profile]
        Plan[Build consolidated plan]
        LLM1[LLM call #1<br/>Render plan summary]
        Route[Route to specialists]
        LLM2[LLM call #2<br/>Draft welcome message]
        Readiness[Readiness check<br/>T-3 days]
    end

    subgraph Agents["Specialist Agents (OpenAI Agents SDK)"]
        direction LR
        IT[IT Provisioning Agent]
        MP[Manager Prep Agent]
        CD[Compliance and Docs Agent]
    end

    subgraph MockData["Mock Data (JSON)"]
        direction LR
        Profiles[profiles.json]
        Rosters[org_rosters.json]
        Calendars[calendars.json]
        Compliance[compliance_catalog.json]
        ITCat[it_catalog.json]
    end

    User <--> Dashboard
    Dashboard <--> Orchestrator
    Validate --> Profiles
    Route --> IT
    Route --> MP
    Route --> CD
    IT --> ITCat
    MP --> Rosters
    MP --> Calendars
    CD --> Compliance

    classDef llm fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    classDef python fill:#e5e7eb,stroke:#6b7280,color:#1f2937
    classDef agent fill:#d1fae5,stroke:#10b981,color:#064e3b
    classDef data fill:#fef3c7,stroke:#d97706,color:#78350f

    class LLM1,LLM2 llm
    class Validate,Plan,Route,Readiness python
    class IT,MP,CD agent
    class Profiles,Rosters,Calendars,Compliance,ITCat data
```

**Key narrative for this view:** the orchestrator is mostly Python (gray). The agents are LLM-driven specialists (green). The orchestrator only uses the LLM for two judgment-heavy content tasks (blue). Mock data lives in JSON (yellow) — in production, these become MCP connectors to HRIS, calendar, ITSM.

---

## 2. End-to-end workflow

The sequence a single new hire (e.g., Sarah Chen) flows through, with every HITL touchpoint shown.

```mermaid
flowchart TD
    Start([New hire profile arrives]) --> Validate{Validate profile}
    Validate -- Invalid --> Reject[Surface error<br/>missing or malformed data]
    Validate -- Valid --> BuildPlan[Build plan deterministically]
    BuildPlan --> LLM1[LLM #1: Render plan summary]
    LLM1 --> G1([Gate: plan_approval])

    G1 --> Fork{Parallel kickoff}
    Fork --> IT[IT Provisioning Agent]
    Fork --> CD[Compliance and Docs Agent]

    IT -. if requested .-> G2([Gate: special_access])
    G2 --> ITDone[IT complete]
    IT --> ITDone
    CD -. if unfamiliar combo .-> G3([Gate: escalation])
    G3 --> CDDone[Compliance complete]
    CD --> CDDone

    ITDone --> MP[Manager Prep Agent]
    MP -. if calendar fully booked .-> G3b([Gate: escalation - schedule])
    MP --> G4([Gate: 30_60_90_signoff])
    G3b --> G4
    G4 --> LLM2[LLM #2: Draft welcome message]
    LLM2 --> G5([Gate: welcome_message_review])
    G5 --> Schedule[Send or schedule welcome message]

    CDDone --> Wait{All tracks complete}
    Schedule --> Wait
    Wait --> TMinus3[T-3 days before start date]
    TMinus3 -. if anything outstanding .-> A1([Alert: readiness_at_risk])
    A1 --> Complete([Onboarding complete - new hire ready])
    TMinus3 --> Complete

    classDef gate fill:#fef3c7,stroke:#f59e0b,color:#78350f,stroke-width:2px
    classDef alert fill:#fee2e2,stroke:#ef4444,color:#7f1d1d,stroke-width:2px
    classDef llm fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    classDef agent fill:#d1fae5,stroke:#10b981,color:#064e3b
    classDef python fill:#e5e7eb,stroke:#6b7280,color:#1f2937
    classDef terminal fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef error fill:#fee2e2,stroke:#ef4444,color:#7f1d1d

    class G1,G2,G3,G3b,G4,G5 gate
    class A1 alert
    class LLM1,LLM2 llm
    class IT,MP,CD agent
    class Validate,BuildPlan,ITDone,CDDone,Schedule,TMinus3,Fork,Wait python
    class Start,Complete terminal
    class Reject error
```

**Key narratives for this view:**
- Two HITL touchpoints are **guaranteed** (plan_approval, welcome_message_review). Four are **conditional**.
- IT and Compliance run in **parallel** after plan approval — visible in the fork. Manager Prep waits because the 30-60-90 references the tools IT will provision.
- Yellow = decision gates (three actions). Red = the single alert.
- Dotted arrows = conditional paths. Solid arrows = always taken.

---

## 3. Coordinator timeline

What the Onboarding Coordinator actually experiences, plotted over calendar time. This is the most persuasive view for an HR audience because it shows touchpoints as a function of *time before the new hire starts* — the dimension the coordinator thinks in.

```mermaid
gantt
    title Sarah Chen — Coordinator touchpoints (start date June 21)
    dateFormat YYYY-MM-DD
    axisFormat %b %d

    section Coordinator gates
    Plan approval                :milestone, p1, 2026-06-07, 0d
    Special access — AWS         :milestone, p2, 2026-06-08, 0d
    30-60-90 sign-off            :milestone, p3, 2026-06-10, 0d
    Welcome message review       :milestone, p4, 2026-06-10, 0d

    section Agent execution
    IT Provisioning              :a1, 2026-06-07, 2d
    Compliance and Docs          :a2, 2026-06-07, 2d
    Manager Prep                 :a3, after a1, 2d

    section Pre-start window
    Welcome message sends        :milestone, w1, 2026-06-14, 0d
    Readiness check (T-3)        :milestone, r1, 2026-06-18, 0d
    Sarah starts                 :milestone, start, 2026-06-21, 0d
```

**Key narrative for this view:**
- Total coordinator touchpoints in the happy path: **4 quick approvals**, spread across 3-4 days, asynchronously.
- Compare against today: dozens of Slack messages and emails across IT, the manager, payroll, compliance, and facilities for the *same* hire.
- The product's value proposition isn't "agents" — it's "compressed coordination time, surfaced as 4 reviewable decisions instead of 50 unreviewable messages."

---

## How to use these in the demo

| Slide | Use this diagram |
|-------|------------------|
| Opening / what I built | View 1 (Architecture) |
| How it works | View 2 (End-to-end workflow) |
| Why it matters (ROI / UX) | View 3 (Coordinator timeline) |

**Export tip:** for the interview slide deck, render each Mermaid diagram at mermaid.live and export to SVG. SVG keeps text crisp at any zoom level — important if Andrew shares his screen at a non-standard resolution.

**Edit tip:** if you change the workflow (add a gate, rename an agent), update the diagrams here *first* — they're cheaper to revise than slides, and updating the source-of-truth doc prevents drift between the spec and the demo.
