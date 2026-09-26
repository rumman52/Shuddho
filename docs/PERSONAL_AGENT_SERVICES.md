# Personal agent service catalog

**Status: target product scope, 26 September 2026.** This catalog covers every service requested by the founder plus Shuddho's own services. It is a design artifact, not an executable tool registry or production availability list. Baseline: PR #204, commit `9c658742ac38c6a1f3bcaf7f6c92869be47ab4f2`.

“Bounded foundation” means code or a versioned contract exists, with the current limits and release gates. “New” means additional implementation is required. All services inherit the [architecture](PERSONAL_AGENT_ARCHITECTURE.md)'s owner isolation, budgets, provenance, approval and outcome rules. Follow the [delivery plan](PERSONAL_AGENT_IMPLEMENTATION.md) to qualify them.

**All 16 requested categories remain in scope.**

| ID | Service | Baseline and required addition | Completion evidence |
| --- | --- | --- | --- |
| S01 | Goal planning | Bounded single-run goals exist. Add persistent milestones, success criteria, linked runs, pause/resume and revisions. | Saved goal and plan; progress refers to completed tasks or user-confirmed milestones. |
| S02 | Email assistance | Drafting/approved sends exist. Add consented inbox reading, triage, thread synchronization and follow-up watches. | Summary cites owned messages; sending has the exact approval and provider receipt. |
| S03 | Calendar organization | Approved single-event creation exists. Add reading/free-busy, conflict handling, updates and recurrence as separate capabilities. | Proposal shows timezone/conflicts; mutation receipt matches approved attendees and times. |
| S04 | Deadline alerts | Bounded calendar reminders exist. Add durable standalone triggers and notification delivery. | Active owned trigger, explicit resolved deadline and recorded notification outcome. |
| S05 | Web research | One-query cited research exists. Add bounded query planning, follow-up retrieval and brokered browsing. | Sources, retrieval dates, grounded findings and explicit unresolved questions. |
| S06 | Form completion | New browser/provider workflow. Bind target site, identity, fields and final submission to scope. | Reviewed field values and submission confirmation, or explicit user takeover/blocker. |
| S07 | Travel assistance | Planning/research foundations exist. Add current inventory, traveler constraints and qualified booking operations. | Itinerary with source dates; any booking has fresh approved terms and confirmation. |
| S08 | Restaurant reservations | New provider or bounded browser workflow. Resolve venue, party size, date/timezone and cancellation terms. | Reservation confirmation matching the approved request; availability research alone is incomplete. |
| S09 | Shopping assistance | Research foundation exists. Add product matching, cart state, final price verification and approved checkout. | Item/variant/quantity, merchant, taxes/shipping/currency and receipt match approval. |
| S10 | Household organization | Daily/personal planning foundation exists. Add recurring household goals, menus, grocery lists and family tasks. | Owned checklist/plan and active requested reminders; family sharing uses explicit ACLs. |
| S11 | Document creation | Official letters, reports and native exports exist. Expand templates, revision fidelity, webpages and layout checks. | Valid accessible artifacts with sources, version, correct language and rendered-layout verification. |
| S12 | Interactive tools | New isolated artifact runtime for trackers, study guides and dashboards. | Working private artifact, validated input/output behavior and no privileged app access. |
| S13 | Coding and custom tools | New isolated execution pool, bounded dependencies and export checks. | Executed result/tests and verified outputs; generated tools remain sandbox-local. |
| S14 | Negotiation assistance | Drafting/research foundation exists. Add scoped counterparty/channel, offer history, user limits and reviewable proposals. | Communication receipts and explicit approval of any binding commitment; no invented savings. |
| S15 | Recurring/background work | Durable finite runs exist. Add goal triggers, Temporal Schedules, event intake, dedupe and notifications. | Occurrences persist through restarts, reuse their accepted run and follow cancellation/expiry policy. |
| S16 | Personalized suggestions | Explicit memory exists. Add scoped retrieval, proposed memories, relevance scoring and user controls. | Suggestion cites permitted context; activating work or accepting memory follows user control. |

**Retain Shuddho's own services as first-class capabilities.** Shared categories are referenced rather than introducing duplicate execution paths.

| ID | Shuddho service | Integration into the personal agent | Completion evidence |
| --- | --- | --- | --- |
| S17 | Writing correction | Keep spelling, grammar, punctuation, spacing and local Bangla support in the fast editor path; allow reviewed document steps to use it. | Exact-span suggestions, preserved meaning and explicit AI failure diagnostics. |
| S18 | Rewriting, tone and multilingual writing | Reuse language/style capabilities; qualify specialized translation and explanation tasks before marketing them. | Requested language/tone, preserved facts and human-rated language quality. |
| S19 | Reports and professional communication | Reuse report/email workflows with approved source handoffs. | Grounded editable report and distinct email draft; sending uses S02. |
| S20 | CVs, resumes and career documents | Reuse career workflow; add job-specific tailoring with user-approved facts. | Editable document without invented employment/qualifications; application submission uses S06. |
| S21 | Meeting agendas, minutes and Zoom support | Reuse meeting preparation from notes. Add Zoom meeting creation and consented transcription as separately qualified integrations. | Agenda/minutes distinguish proposals from decisions; a new meeting has a provider ID/link; transcription requires an actual source. |
| S22 | Presentations | Reuse editable PPTX, notes and charts; improve layouts, sources and render quality. Current bounded output is 1–8 slides. | Editable deck, requested content, grounded figures and visual QA; a PDF handout is not a slide-identical export. |
| S23 | Spreadsheets and data work | Reuse XLSX/CSV/calculation workflows; extend analysis through qualified sandbox tools. Current output is one worksheet, up to 40 rows. | Recalculated formulas, known missing values, validated charts and editable workbook. |
| S24 | Social writing and publishing | Reuse drafts and separately gated LinkedIn personal-text publishing. Other networks, media and scheduling require new capability work. | Correct draft; publishing requires approved account/content and provider receipt. |
| S25 | Document sharing | Reuse separately gated owned-document sharing; extend destinations/roles independently. | Exact artifact version, recipient, access level and verified provider permission result. |
| S26 | Daily and personal plans | Reuse existing plan generation and connect it to S01/S04/S15. | Saved plan clearly distinguishes proposed tasks from scheduled events or active reminders. |

Email drafts map to S02, official documents to S11, and existing research to S05. None of these services bypass their existing implementation limits or feature gates. Production LinkedIn Agent proposal enablement remains independently gated and off unless separately qualified.

**Operations within a service have different permissions.**

| Automatic within a granted scope | Requires exact approval in the initial design |
| --- | --- |
| Draft a message; summarize permitted messages | Send the message or disclose attachments |
| Read a consented calendar; propose a time | Create/change an event or invite people |
| Compare products; assemble a private comparison | Purchase, accept changed price or cancel with a fee |
| Research an itinerary; prepare booking details | Confirm a reservation or accept binding terms |
| Prepare a negotiation strategy or counteroffer | Send external negotiation messages or accept an agreement |
| Generate private files, dashboards and code outputs | Publish, share, deploy or give another party access |
| Run an explicitly activated watcher and notify its owner | Widen its sources, audience, permissions or spending limit |

A private cart or form can itself create remote state or disclose data; classify actual provider/site behavior before deciding that preparation is automatic. An operation labeled “read” is not automatically harmless if its query exports private data.

**Compose services into complete workflows.** These examples describe target behavior rather than currently available automation.

1. A weekday briefing combines S02, S03, S04, S15 and S16. Read only approved inbox/calendar scopes, assemble a private briefing, surface due items, and deliver once within the user's notification policy. Suggested external replies remain approval-bound.
2. A student goal combines S01, S11, S22 and S26 with S04/S15. Use the owned syllabus, prepare an editable study plan and deck, and deliver due briefings after app closure or worker restart. Calendar writes require a separate approved action.
3. Travel combines S05, S07, S08 and optionally S09. Research within the budget, show source freshness and remaining uncertainty, prepare exact options, then pause for approval of bookings or purchases. Price changes force a new preview.
4. Career support combines S05, S20, S02 and S06. Retrieve relevant public positions, tailor materials from verified user facts, prepare an application and obtain approval before external submission.
5. Household organization combines S10, S03, S04 and S15. Keep family data within explicit sharing rules, produce menus/lists and schedule authorized reminders. Purchases and invitations use approved external actions.
6. Negotiation combines S05, S14 and S02 or a qualified browser channel. Record the user's limits and counterparty identity, propose offers, retain communication history and obtain approval for external messages and commitments.

**Each service needs a reviewed implementation contract.** Record service/version, currently available operations, schemas, permitted resource scopes, required connectors, model profile, limits, deadlines, expected artifacts, approval class, receipt validator, failure/reconciliation behavior and evaluation fixtures. Service availability is the intersection of implemented registry entries, feature flags, cohort admission, provider health, account permissions and remaining budget.

Do not dynamically register tools from a service description, webpage, email, generated skill or MCP response. Unsupported providers or site flows yield a specific blocker, not simulated success. The catalog contains product categories; the existing runtime registries and release contract remain the authority for execution.

Repository evidence:

- [Work services](PART_3_WORK_SERVICES.md)
- [Presentations/spreadsheets](PART_3_PRESENTATIONS_SPREADSHEETS.md)
- [Research](PART_3_RESEARCH.md)
- [Approved actions](PART_3_APPROVED_ACTIONS.md)
- [Calendar reminders](APPROVED_CALENDAR_REMINDERS.md)
- [Structured memory](PART_3_AGENT_MEMORY.md)
- [Action registry](../services/coworker/action_registry.py)
- [Agent tool registry](../services/coworker/agent_tools.py)
