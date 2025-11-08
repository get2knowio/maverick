# Research: PR CI Automation

## Decision Log

### Decision: Use `gh` CLI JSON output for PR discovery, polling, and merge
- **Rationale**: The spec standardizes on the `gh` CLI as the integration surface and it supplies structured JSON via `--json` flags for PR metadata, check runs, and merge results. Leveraging these commands keeps implementation consistent with existing automation and avoids duplicating GitHub REST clients.
- **Alternatives considered**:
  - GitHub REST/GraphQL APIs (rejected: violates clarified requirement to use `gh` exclusively, increases maintenance burden).
  - Git CLI plumbing commands (rejected: do not provide CI status or PR metadata).

### Decision: Apply deterministic exponential backoff for transient `gh` failures within activity timeout
- **Rationale**: GitHub frequently returns HTTP 403/502 responses under load. Encapsulating retries with capped exponential backoff (e.g., 2^n seconds up to the polling interval cap) maximizes resiliency while keeping activity execution time bounded by the configured timeout.
- **Alternatives considered**:
  - Immediate failure on rate limit (rejected: contradicts clarification to retry within budget and would cause noisy Temporal retries).
  - Delegating entirely to Temporal activity retries (rejected: loses fine-grained control and would restart from scratch without incremental progress).

### Decision: Track check runs by latest attempt per job name for mixed-status matrices
- **Rationale**: Matrix builds emit multiple runs with identical names but different attempt numbers. Selecting the latest attempt per job ensures the automation reports accurate current state, supports re-run scenarios, and aligns with remediation needs.
- **Alternatives considered**:
  - Aggregating by conclusion only (rejected: loses log URLs for individual failed jobs).
  - Treating every run separately (rejected: produces duplicate failure entries and confuses downstream remediation).
