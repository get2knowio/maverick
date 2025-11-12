# Research Findings: Per-Task Branch Switching

## Task: Research branch slug derivation rules for Speckit task descriptors
- **Decision**: Derive the git branch slug from the `specs/<slug>/` directory name when the descriptor omits an explicit branch, and always trust an explicit branch override when present.
- **Rationale**: Speckit feature specs already organize task collateral by slugged subdirectories. Using the directory name keeps automation aligned with human expectations and matches the clarification log. Honoring explicit overrides preserves operator control for exceptional cases.
- **Alternatives considered**: Parsing slugs from task file basenames (risk of drift when folders contain multiple files); hashing descriptor metadata (opaque to operators); prompting users for branch names (breaks automation).

## Task: Find best practices for safe git checkout in automation workers
- **Decision**: Implement `checkout_task_branch` to (1) assert a clean working tree via `git status --porcelain`, (2) fetch `origin <branch>` before checkout, (3) run `git switch <branch>` (or `git checkout <branch>` fallback) and verify `git rev-parse --abbrev-ref HEAD` equals the target.
- **Rationale**: Checking cleanliness prevents unintentional worktree mutations. Fetching ensures the worker sees the latest remote heads, which matches the clarification requirement. Using `git switch` simplifies detached-head handling while remaining compatible with modern git. Final verification guards against unusual git configs.
- **Alternatives considered**: Blind checkout without cleanliness check (risks data loss); skipping fetch (stale refs); using Temporal workers' `gitpython` wrapper (adds dependency bloat and slower than CLI as per past experience).

## Task: Research idempotent branch checkout behavior for retries
- **Decision**: Short-circuit when the repo is already on the target branch **and** the status check passes cleanly, returning a structured success payload without running additional git commands.
- **Rationale**: Temporal retries will re-run activities; avoiding redundant git operations keeps execution fast and prevents confusing logs while preserving determinism.
- **Alternatives considered**: Always re-run fetch/checkout (wastes time, more network calls); caching last branch outside activity (would complicate deterministic state if stored in workflow).

## Task: Find best practices for resetting to main after merge
- **Decision**: Implement `checkout_main` to `git switch main`, then `git pull --ff-only origin main`, fail fast if the pull diverges, and confirm the working tree is clean afterward.
- **Rationale**: The clarification explicitly calls for fast-forward-only sync. Checking cleanliness ensures the next task starts from a pristine state.
- **Alternatives considered**: Force-reset to origin/main (`git reset --hard`), which risks data loss and conflicts with Simplicity First; skipping the pull (could leave stale code on the worker).

## Task: Research safe branch deletion flows post-merge
- **Decision**: Implement `delete_task_branch` to detect whether the branch exists locally and skip deletion with a logged reason if missing. When present, delete via `git branch -D <branch>` after ensuring we are on `main`, and report results in structured output.
- **Rationale**: Using the capital `-D` handles rare cases where merge heuristics fail, preventing stuck branches during automation. Logging the reason when the branch is absent satisfies the spec's transparency requirement.
- **Alternatives considered**: Use `git branch -d` (fails if git mis-detects merge state); attempt remote deletion (out of scope per assumptions); raising errors when branch missing (violates spec clarification).

## Task: Ensure git subprocess integration meets Maverick logging standards
- **Decision**: Wrap git CLI calls in shared helpers that capture stdout/stderr with `errors='replace'`, time each invocation, and emit structured JSON logs including command, exit code, and sanitized output.
- **Rationale**: Aligns with the constitution's error-handling mandates and existing logging utilities. Centralizing helpers keeps activities concise and supports consistent retry semantics.
- **Alternatives considered**: Inline `subprocess.run` calls in each activity (duplicated error handling); adopt third-party git libraries (larger footprint, violates Simplicity First for this scope).
