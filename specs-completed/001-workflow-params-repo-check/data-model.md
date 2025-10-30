# Data Model

## Entities

- Parameters
  - Type: `dict[str, Any]`
  - Required keys (MVP):
    - `github_repo_url: str` — HTTPS or SSH GitHub URL

- VerificationResult
  - Fields:
    - `tool: Literal["gh"]`
    - `status: Literal["pass","fail"]`
    - `message: str` (human-readable)
    - `host: str` (e.g., `github.com` or GHES host)
    - `repo_slug: str` (`owner/repo`)
    - `error_code: Literal["none","validation_error","auth_error","not_found","access_denied","transient_error"]`
    - `attempts: int` (1 or 2)
    - `duration_ms: int`

- WorkflowState
  - `state: Literal["pending","verified","failed"]`
  - `verification: VerificationResult | None`

## Relationships

- A Workflow run holds one Parameters map.
- A Workflow run produces one VerificationResult (on success or failure) before running dependent steps.

## Validation Rules

- `github_repo_url` MUST be a non-empty string; HTTPS (`https://<host>/<owner>/<repo>[.git]`) and SSH (`git@<host>:<owner>/<repo>[.git]`) accepted.
- Host MUST be `github.com` or a GHES host extracted from the URL; all other hosts rejected.
- Normalization MUST derive `repo_slug = owner/repo` and `host` before invoking verification.

## State Transitions

- `pending` → `verified` when `VerificationResult.status == "pass"`.
- `pending` → `failed` when `VerificationResult.status == "fail"`.
- No transitions after `verified`/`failed` within MVP.

