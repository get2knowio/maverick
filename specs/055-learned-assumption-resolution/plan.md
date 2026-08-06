# Implementation Plan: Learned Assumption Resolution

**Branch**: `055-learned-assumption-resolution` | **Date**: 2026-08-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/055-learned-assumption-resolution/spec.md`

## Summary

Persist every human-initiated terminal assumption-ledger outcome as a decision record
in the runway knowledge store, deterministically match newly recorded assumptions
against that corpus, and attach a suggested resolution (with provenance and confidence)
to matching entries — surfaced in `review --list --json` and as the default option in
the maverick-review skill's sweep. Rejections lower a pairing's future confidence.
An opt-in policy may auto-waive low-severity entries above a strict confidence
threshold; because auto-resolution always waives (never answers), the existing land
classification (`classify()` downgrades any waived entry to conditionally-verified)
and reconcile detection (answered-only) are correct **unchanged**.

The entire feature is deterministic library + CLI code: **zero model calls, zero
agents, zero Burr changes** (the fly graph's existing `record_assumptions` action and
the spec-chain workflow gain one post-recording library call each).

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)

**Primary Dependencies**: Existing only — Pydantic (frozen models), Click + Rich
(CLI), structlog, aiofiles (runway store I/O), stdlib `difflib` + tokenization for
matching. No new dependencies.

**Storage**: Two new append-only JSONL files in the git-committed runway store
(`.maverick/runway/decisions.jsonl`, `.maverick/runway/match-feedback.jsonl`) —
deliberately **outside** `episodic/` so `runway consolidate` never prunes them
(FR-002). Per-entry suggestion state persists as one JSON-encoded bd state key
(`assumption_suggestion`) so the non-atomic per-key `BeadClient.set_state` writes it
atomically in a single bd invocation.

**Testing**: pytest + pytest-asyncio + xdist (`make test`, `make test-fast`);
red-green TDD per Principle V.

**Target Platform**: Linux/macOS developer checkout (same as all Maverick commands).

**Project Type**: CLI + library (existing single-project layout).

**Performance Goals**: SC-006 — suggestion evaluation adds < 1s to recording or
listing with a 500-record corpus. Pairwise `difflib.SequenceMatcher` + token Jaccard
over ≤150-char normalized questions is ~µs/pair; 500 pairs ≪ 50ms.

**Constraints**: Zero model calls (FR-008, Guardrail X.10); matching deterministic
given (entry, corpus, feedback state); degradation never blocks capture, review, or
landing (FR-021); corpus admission is human-initiated resolutions only (FR-005);
no cross-repository state (FR-022).

**Scale/Scope**: Corpus of hundreds to low-thousands of decision records per
repository; entries per sweep in the tens.

## Constitution Check

*GATE: evaluated pre-Phase-0 and re-evaluated post-Phase-1 — PASS, no violations.*

| Gate | Assessment |
|---|---|
| I. Async-first | All new I/O paths are async (`RunwayStore` methods, `BeadClient.set_state`); matching itself is pure sync CPU work called from async contexts. No `subprocess.run` anywhere. |
| II. Separation of concerns | Matching/scoring is a pure library module (`assumptions/matching.py`); orchestration (load corpus → score → persist) is a library helper (`assumptions/suggestions.py`) called from existing workflow actions and CLI commands. No business logic in CLI modules beyond invocation + rendering; no agents involved at all. |
| III. Dependency injection | `RunwayStore` and `BeadClient` are constructed at boundaries and passed in; no globals, no module state. |
| IV. Fail gracefully | Decision-record write failure warns and never blocks the ledger write (FR-004); store unavailability degrades to no-suggestion (FR-021); corrupt JSONL lines skipped via the store's existing `_read_jsonl` tolerance. |
| V. Test-first | Every new public function gets red-green tests; regression tests bind to real code paths (matching module is pure and directly testable). |
| VI. Typed contracts | New frozen Pydantic models (`DecisionRecord`, `MatchFeedbackRecord`) with `to_dict`/`from_dict`, matching runway conventions; suggestion projection is a frozen dataclass; no `dict[str, Any]` blobs on public surfaces. |
| VII. Simplicity & DRY | Reuses `entry_to_dict` (one shared projection — FR-011 falls out for free), the runway store's append/read/rewrite patterns, `ledger.waive()` for auto-resolution, and the 054 config-block template. No new wrappers. |
| X.0 / X.7. cwd threading | Store path and `BeadClient` cwd resolved at CLI/workflow boundary and passed down; no `Path.cwd()` in workflows. |
| X.2. Agents own no side effects | Stronger: no agents at all — the whole feature is deterministic. |
| X.8. Canonical libraries | structlog via `get_logger`, existing store atomics; no new git/gh/bd wrappers. |
| X.10 / XIII. Determinism | The feature's core constraint. Matching is corpus-independent-scored (`difflib` + Jaccard, documented formula), zero model calls, reproducible. |
| XI. Modularize early | New logic lands in two new focused modules (`matching.py`, `suggestions.py`) instead of growing `ledger.py` (already 1347 LOC — no new features added to it beyond parsing one state key). |

**Post-design re-check**: PASS. The design adds no agents, no new external systems,
no new subprocess wrappers, and keeps `classify()`/the land gate untouched.

## Project Structure

### Documentation (this feature)

```text
specs/055-learned-assumption-resolution/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions R1–R13
├── data-model.md        # Phase 1 — entities, fields, state transitions
├── quickstart.md        # Phase 1 — end-to-end validation guide
├── contracts/
│   ├── decision-records.md        # Runway file formats + matching formula
│   ├── entry-row-suggestion.md    # entry_to_dict / review --list --json additions
│   ├── config-schema.md           # assumptions.resolution block
│   └── skill-review-console-delta.md  # maverick-review sweep changes
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/maverick/
├── runway/
│   ├── models.py                  # + DecisionRecord, MatchFeedbackRecord
│   └── store.py                   # + append/get/rewrite for decisions & feedback
├── assumptions/
│   ├── matching.py                # NEW — normalize_question, score, thresholds (pure)
│   ├── suggestions.py             # NEW — attach/back-fill/auto-resolve + decision capture
│   ├── models.py                  # + KEY_SUGGESTION, KEY_AUTO_RESOLVED, Suggestion dataclass,
│   │                              #   AssumptionReportEntry.suggestion/auto_resolved
│   ├── ledger.py                  # parse suggestion state key into report entries
│   └── serialize.py               # + "suggestion", "auto_resolved" row keys
├── cli/commands/review/
│   ├── listing.py                 # back-fill suggestions on --list
│   └── entry_actions.py           # decision capture + accept/reject feedback (single + bulk)
├── workflows/
│   ├── fly_beads/actions.py       # record_assumptions → attach_suggestions call
│   └── spec_chain/workflow.py     # standalone recording → attach_suggestions call
├── config.py                      # + AssumptionResolutionConfig / AutoResolvePolicyConfig
└── skills/review_console/SKILL.md # suggestion-as-default sweep behavior

tests/
├── unit/runway/test_store_decisions.py          # NEW
├── unit/assumptions/test_matching.py            # NEW
├── unit/assumptions/test_suggestions.py         # NEW
├── unit/assumptions/test_serialize.py           # extend
├── unit/cli/review/…                            # extend listing + entry_actions tests
├── unit/workflows/fly_beads/…                   # extend record_assumptions tests
└── unit/test_config.py                          # extend for new block
```

**Structure Decision**: single-project layout, existing packages. New behavior is
concentrated in two new `assumptions/` modules plus additive changes to the runway
store, keeping `ledger.py` growth to one read-side parse and honoring Principle XI.

## Complexity Tracking

No constitution violations — table intentionally empty.
