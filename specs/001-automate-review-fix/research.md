# Research Findings: Automated Review & Fix Loop

## Decision: Execute External Tooling via `uv run`
- **Decision**: Wrap all CodeRabbit, OpenCode, and validation commands with `uv run` invoked from the activity using `asyncio.create_subprocess_exec`.
- **Rationale**: Satisfies the UV-Based Development gate, guarantees a consistent Python-managed environment, and lets us centralize logging/timeout handling for every subprocess.
- **Alternatives considered**: Calling the binaries directly from `$PATH` (rejected because it violates the constitution and complicates dependency management); spawning shell pipelines (rejected due to determinism and quoting risks).

## Decision: Capture and Normalize CodeRabbit Output as Plain Text with Structured Envelope
- **Decision**: Request CodeRabbit CLI plain-text mode, capture full stdout/stderr, and wrap the transcript in a structured `CodeReviewFindings` object containing issue bullets extracted via regex heuristics plus the raw prompt with sanitization metadata.
- **Rationale**: Plain text mode is universally available and avoids coupling to undocumented JSON schemas; heuristics can still yield stable issue lists while preserving entire transcripts for audit.
- **Alternatives considered**: Depending on JSON output flags (rejected because availability varies by CLI version); parsing Markdown sections only (rejected since remediation prompts may mix prose and code fences, risking data loss).

## Decision: Sanitization Pipeline for Remediation Prompts
- **Decision**: Implement a sanitization pipeline that trims transcripts to a configurable max length, redacts tokens matching common secret patterns (AWS keys, GitHub tokens, PEM blocks), and collapses repeated whitespace before persisting or forwarding to OpenCode.
- **Rationale**: Meets FR-003 while keeping downstream prompts deterministic and safe; redact-and-note approach lets us surface that redactions occurred without leaking sensitive data.
- **Alternatives considered**: Passing transcripts verbatim (rejected due to security risk); building a full DLP integration (rejected as overkill for current scope).

## Decision: Fingerprinting Strategy for Idempotent Retries
- **Decision**: Compute a SHA-256 fingerprint from the sorted commit SHAs under review, the sanitized CodeRabbit findings hash, and the OpenCode task descriptor; store this fingerprint alongside attempt metadata.
- **Rationale**: Deterministic hash components allow safe retry detection without persisting large blobs; combining commits and findings ensures new code or different diagnostics trigger fresh runs.
- **Alternatives considered**: Timestamp-based fingerprints (rejected—non-deterministic); relying solely on commit hash (rejected because findings can change without new commits if CodeRabbit improves).

## Decision: Validation Command Orchestration
- **Decision**: Default validation to `uv run cargo test --all --locked`, with support for overriding the command via `ReviewLoopInput.validation_command` while retaining tolerant decoding and structured logging.
- **Rationale**: Aligns with current rust automation practices, enforces lockfile usage, and keeps execution within UV standards; configurability allows future scenarios (e.g., `cargo nextest`, custom scripts).
- **Alternatives considered**: Hard-coding `cargo test` without uv (rejected due to constitution); running validation inside workflow code (rejected because workflows must remain deterministic and side-effect free).

## Decision: Logging & Artifact Storage
- **Decision**: Use `src/utils/logging.get_structured_logger` for the activity, emit JSON logs with correlation IDs, and persist sanitized transcripts plus fingerprints through the existing `PhaseResultsStore` abstraction for downstream access.
- **Rationale**: Respects observability requirements, reuses established storage patterns, and keeps workflow state lean by storing only references and hashes.
- **Alternatives considered**: Writing ad-hoc JSON files in the workspace (rejected—hard to manage, risks determinism violations); logging via print statements (rejected by logging standards).
