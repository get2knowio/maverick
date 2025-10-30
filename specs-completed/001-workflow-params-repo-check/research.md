# Research: Parameterized Workflow & GitHub Repo Verification

## Decisions

- Parameter model: Accept `dict[str, Any]` at workflow start; expose typed accessor for steps/activities to retrieve required keys by name (MVP requires `github_repo_url`).
- URL normalization: Support HTTPS (`https://github.com/owner/repo[.git]`) and SSH (`git@github.com:owner/repo[.git]`) formats; normalize to `owner/repo` slug and infer `host`.
- Host support: Default `github.com`; allow GHES via URL host (e.g., `ghe.example.com`). Use the same host for `gh` commands with `-h` when needed.
- Auth pre-check: Require `gh` to be installed and authenticated for the target host before verification. Check with `gh auth status` (or `gh auth status -h <host>`). If not authenticated, fail fast with guidance (`gh auth login`).
- Verification command: Use `gh repo view <owner/repo>` (plus `-h <host>` when non-default). Success => repo exists; non-zero exit => not found or inaccessible.
- Retry policy: On transient failures (timeout/rate-limit/5xx), retry once with small backoff (e.g., 300–500ms). Total p95 target ≤ 5s.
- Timeouts: Each `gh` invocation limited to ~2.0s per attempt under normal conditions, adjustable via config if needed.
- Error taxonomy: `validation_error` (malformed/non-GitHub URL), `auth_error` (gh not installed/not authenticated), `not_found`, `access_denied`, `transient_error`.
- Observability: Structured logs with fields: `repo_slug`, `host`, `auth_ok`, `attempt`, `duration_ms`, `status`, `error_code`.
- Determinism: All I/O and `gh` calls run in activities. Workflows only orchestrate and use `workflow.now()` for timing.

## Rationale

- Using `gh` aligns with environment auth/host contexts and user expectation; avoids bespoke auth and API plumbing in MVP.
- Normalizing to `owner/repo` simplifies CLI invocation and logging while letting us consistently handle both SSH/HTTPS inputs.
- Auth pre-check prevents confusing failures from attempting `gh` commands without credentials and matches the user’s intent to “follow the validation of the gh CLI itself”.
- Transient retry improves robustness while respecting constitution’s simplicity: single retry, small backoff, clear failure after.

## Alternatives Considered

- Direct GitHub REST/GraphQL API:
  - Pros: Fine-grained control over errors; no external binary dependency.
  - Cons: Must manage tokens/hosts, rate-limit handling, and SDK/configuration; diverges from the “use gh” directive.

- `git ls-remote <url>` probe:
  - Pros: No GitHub-specific dependency; works with git remotes directly.
  - Cons: Requires SSH/HTTPS credentials and network; returns less precise cause (auth vs not found); less aligned with “follow gh CLI validation”.

- Skip explicit auth check and rely on `gh repo view` failure:
  - Pros: Fewer commands.
  - Cons: Error ambiguity; user asked to ensure auth before validation; explicit `gh auth status` gives clearer guidance.

## Clarifications Resolved

- Multi-parameter future readiness: Interface accepts a parameter map; steps read declared keys; missing keys error clearly. MVP uses only `github_repo_url`.
- Host handling: Use URL host; default `github.com`; pass `-h <host>` to `gh` for non-default.
- Validation boundary: Reject non-GitHub hosts unless they match detected GHES host(s) via URL. Malformed inputs are rejected before any `gh` call.
- Authentication gate: Verification does not proceed unless `gh` reports authenticated for the target host.
- Performance: 1 retry, short timeouts keeps p95 ≤ 5s under normal conditions.

