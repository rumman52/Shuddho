# Rukh AI technical risk register — 4 November 2026

| ID | Risk | Severity | Evidence | Mitigation / owner |
|---|---|---|---|---|
| R-01 | Numeric structured facts can be omitted by offline quality evaluation | High | Reproduced by PR #619 RED run; fix in review | Merge only after heavy CI and independent review |
| R-02 | Coworker root route can fall back to workspace home when feature flag is off | High | `getWorkspaceAppRoute` and `VITE_COWORKER_ENABLED` | Verify staging configuration; owner authorizes activation |
| R-03 | Direct assistant replies are not streamed | Medium | DeepSeek request sets `stream: false` | Design a separate tested streaming contract |
| R-04 | Main branch protection is not confirmed | Critical | Main governance audit failure | Repository admin configures native protection and required checks |
| R-05 | Render staging service/database continuity unknown | Critical | Workspace not confirmed; no service inspection | User confirms workspace; owner verifies backup and restore |
| R-06 | Vercel preview visibility/deployment rate limit | High | Connector returned zero matching deployment records; #618 bot rate-limit error | Restore project access or wait for plan limit; do not bypass protection |
| R-07 | PostHog has no recent ingested events | High | Project 675660: `ingested_event=false`, no events seen in 30 days | Privacy-approved instrumentation and environment setup |
| R-08 | Live auth, owner isolation and deployed browser flows unverified | High | No staging E2E performed | Run authenticated cross-user and responsive tests in isolated staging |

Severity is an engineering prioritization, not a claim of exploitability. No production mutation was made.
