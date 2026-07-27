# Mock Data

JSON fixtures that power the demo. These replace what would be real integrations in production (HRIS, calendar, ITSM, compliance rules engine). The build plan calls for these as Day 1 deliverables so Day 2 coding has data to work against from the first commit.

## Files

| File | What it contains | Used by |
|------|------------------|---------|
| `mock_data/profiles.json` | 5 new hire profiles + 1 malformed for graceful-failure testing | Coordinator (input) |
| `mock_data/org_rosters.json` | Team rosters with tenure, expertise, calendar load — feeds buddy recommendation logic | Manager Prep |
| `mock_data/calendars.json` | Manager free-slot calendars, plus one fully-booked variant for the stretch scenario | Manager Prep |
| `mock_data/compliance_catalog.json` | Document requirements indexed by (location × employment type), plus add-ons for executive and sensitive-data roles | Compliance & Docs |
| `mock_data/it_catalog.json` | Provisionable hardware, software, security groups by role family; contractor restrictions; special-access triggers | IT Provisioning |

## The 5 profiles

Selected to span the dimensions the agents must reason over: role family, location, employment type, seniority. Each profile maps to a specific demo intent.

| Profile | Role | Location | Employment | Demo intent |
|---------|------|----------|------------|-------------|
| Sarah Chen | Sr Software Engineer | Seattle, US | FTE | **Scenario A (P0).** Triggers full happy path. AWS read access triggers the `special_access` HITL gate. Recommended buddy: Tom Brennan (Platform, ~3yr tenure, shipped auth migration). |
| Marcus Webb | Account Executive | London, UK | Contractor | **Scenario B (P0).** Hero comparison vs. Sarah — different role family, geography, employment type. No AWS request. UK contractor doc set incl. IR35. |
| Diana Okafor | Sr Data Scientist | New York, US | Contractor | Backup: showcases US-contractor compliance (W-9, IP assignment, no I-9) and contractor restrictions on engineering provisioning (no production write, time-bounded credentials). |
| Rachel Steinberg | VP Engineering | San Francisco, US | FTE | Backup: showcases executive-tier provisioning (Carta admin → triggers `special_access`) and executive compliance add-ons (equity grant, board-level confidentiality). |
| Yuki Tanaka | Account Executive | Singapore | Contractor | Backup: **the most interview-rich profile.** Singapore is intentionally *not* in `compliance_catalog.json::known_jurisdictions`, so the Compliance Agent must surface an `escalation` gate ("unfamiliar combination, proposing document set X, requires human review"). This is the demo moment for the unfamiliar-combination pattern. |
| `test_malformed` | Sr Software Engineer | Seattle, US | FTE | Profile missing `start_date`. Used to test Scenario D (graceful failure — Coordinator validation rejects before any specialist runs). |

## Design choices worth defending

- **Org roster carries structured signal for buddy logic** (`tenure_years`, `expertise`, `calendar_load`) rather than letting the LLM hallucinate from names alone. The Manager Prep Agent reads the structured data and writes the rationale in natural language. Separating *data lookup* from *natural-language reasoning* is what keeps the buddy recommendation defensible.
- **One calendar variant is fully-booked** to enable the Scenario C stretch without changing code paths — same `check_calendar` tool, different mock data.
- **Singapore profile + compliance catalog without Singapore rules** is intentional design, not a gap. It's the demo case for the unfamiliar-combination escalation pattern (`4_agent_specs.md` §5.5). Without this profile, the capability has no demo moment.
- **The malformed profile is named with `test_` prefix** so a demo audience can see at a glance that it's a fault-injection fixture, not a real candidate. Useful when you're showing failure modes live.
- **No real PII.** No salaries, SSNs, or real email addresses. All affiliations and managers are invented. Reduces risk if the repo gets shared and signals you've thought about data hygiene.

## What's NOT in the mock data, and why

- **No real integration credentials.** Mock tools return fake ticket IDs and account IDs.
- **No timezone math.** `Location.timezone` was trimmed in §1; the demo doesn't reason about TZ math, only about country.
- **No salary or comp data.** Agents don't need it. Even mocked, this would create an awkward optic in a screen-share demo.
- **No real Slack workspace IDs, AWS account numbers, etc.** Plain string descriptors (`"Slack (engineering channels)"`, `"AWS Console (read access)"`) are enough for the dashboard to render.

## How to extend

Adding a new profile to the demo:
1. Append to `profiles.json` with a unique `hire_id`.
2. Make sure their `team` exists in `org_rosters.json` (so Manager Prep can find a buddy).
3. Make sure their `manager_id` has an entry in `calendars.json` (so intro meetings can be scheduled).
4. If their `location.country` is not in `compliance_catalog.json::known_jurisdictions`, they'll exercise the escalation path automatically — no further work needed.
