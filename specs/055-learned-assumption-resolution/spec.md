# Feature Specification: Learned Assumption Resolution

**Feature Branch**: `055-learned-assumption-resolution`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Feed resolved assumption-ledger entries into runway as reusable knowledge, so that when an agent adopts an assumption closely matching one the human has already answered, the prior answer is proposed as the default during review — and eventually the fleet stops asking questions the human has already answered. Two capabilities: (1) Decisions as labels — every terminal ledger outcome (answered, waived, edited-then-answered) is persisted as a structured decision record in runway, carrying the question, the adopted answer, the human's resolution, severity, and the owning spec; records survive across specs and runs. (2) Suggested answers at review time — when a new assumption is recorded, it is matched against prior decision records; a sufficiently close prior decision attaches a suggested resolution with provenance, surfaced in `maverick review --list --json` and presented as the default option in the maverick-review skill's sweep; the land gate is unchanged and a suggestion never auto-answers an entry. An explicit opt-in policy may allow auto-resolution for low-severity entries above a configured confidence threshold, marked with provenance and rendering a land at most conditionally-verified. Matching quality matters more than coverage; the feature must define what closely matching means, how confidence is scored, and how false suggestions are suppressed after rejection. Out of scope: cross-repository knowledge sharing; any change to how assumptions are captured."

## Clarifications

### Session 2026-08-06

- Q: When the human rejects a suggestion, what exactly identifies the "pairing" whose future confidence is lowered? → A: Pairing = (normalized question text of the new entry, source decision record identity); normalization is deterministic (case-fold, collapse whitespace, strip punctuation).
- Q: When the auto-resolution policy fires, does it resolve the entry by writing an answer or by waiving it with a rationale? → A: Always waive, with a recorded rationale citing the matched prior decision; auto-resolution never writes an answer, so machine decisions can never enter reconcile's answered-entry detection or drive history rewriting.
- Q: Is the presentation threshold user-configurable, or a built-in fixed default? → A: Built-in fixed default, not configurable in v1; only the auto-resolution threshold is configurable and must be at least as strict as the built-in presentation threshold.
- Q: Which resolutions feed the decision-record corpus — do machine-initiated waives and human bulk waives count? → A: Only human-initiated resolutions feed it — individual answers/waives and human-invoked bulk waives (one record per entry); scheduler auto-waives and this feature's auto-resolutions are excluded.
- Q: When is an entry's suggestion computed and stored? → A: Computed and persisted at recording time; listing back-fills entries that have no stored suggestion; an existing stored suggestion is never silently replaced.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Terminal ledger outcomes become durable decision records (Priority: P1)

Whenever a human resolves an assumption-ledger entry — answering it, waiving it, or
re-answering it after an earlier answer — the resolution is persisted as a structured
decision record in the project's knowledge store. Each record carries the original
question, the answer the agent had adopted, the human's actual resolution (answer text
or waive reason), the resolution type, the entry's severity, the owning spec, and when
it was resolved. Records accumulate across specs and runs: a decision made while
landing spec 060 is still available when spec 072 raises a similar question months
later.

**Why this priority**: This is the foundation every other capability builds on —
without a durable corpus of decisions there is nothing to match against. It also
delivers standalone value on day one as an auditable history of human judgment: "what
did we decide about retry semantics, and on which spec?"

**Independent Test**: Answer one entry, waive a second, and re-answer a third via
`maverick review`; verify three decision records exist in the knowledge store with
correct question, resolution, resolution type, severity, and owning spec, and that
they persist after the run ends and across an unrelated new spec's lifecycle.

**Acceptance Scenarios**:

1. **Given** an open assumption-ledger entry, **When** the human answers it via
   `maverick review <id> --answer`, **Then** a decision record is persisted carrying
   the question, the adopted answer, the human's answer text, resolution type
   "answered", the entry's severity, and the owning spec.
2. **Given** an open entry, **When** the human waives it with a reason, **Then** a
   decision record is persisted with resolution type "waived" and the waive reason as
   the resolution.
3. **Given** an entry that was previously answered, **When** the human re-answers it
   with different text, **Then** the decision record for that entry reflects the
   latest answer as authoritative for future matching, and the earlier resolution
   remains visible as history.
4. **Given** the knowledge store is unwritable at resolution time, **When** the human
   answers an entry, **Then** the answer itself still succeeds and is recorded on the
   ledger, and the missed decision record is reported as a warning — never a failure
   of the review action.

---

### User Story 2 - Prior decisions surface as suggested resolutions at review time (Priority: P2)

When an agent records a new assumption that closely matches a question the human has
already resolved, the new ledger entry carries a suggested resolution with full
provenance: which prior entry it came from, which spec owned it, when it was resolved,
and how confident the match is. The suggestion appears as a field on the entry row in
`maverick review --list --json`, and the maverick-review skill presents it as the
default option in its question sweep — clearly labeled as sourced from a prior
decision. The human confirms with one selection instead of re-deriving an answer they
already gave. The land gate is unchanged: a suggestion never answers an entry by
itself.

**Why this priority**: This is the feature's visible payoff — the human stops
re-answering questions they have already answered. It depends on User Story 1's corpus
but is independently testable the moment records exist.

**Independent Test**: Seed the knowledge store with a decision record, record a new
assumption whose question closely matches it, and verify the new entry's row in
`review --list --json` carries the suggested resolution with provenance; verify a
non-matching entry carries no suggestion; verify the entry still counts as open for
the land gate until the human resolves it.

**Acceptance Scenarios**:

1. **Given** a decision record answering "Should retries use exponential backoff?" and
   a new assumption entry asking a closely matching question, **When** the entry is
   recorded, **Then** the entry carries a suggested resolution containing the prior
   answer, the source entry's identity, the owning spec, the resolution date, and a
   confidence score.
2. **Given** a new entry whose question matches no prior decision above the
   presentation threshold, **When** the entry is listed, **Then** it carries no
   suggestion — a weak match is silence, not a guess.
3. **Given** an entry with a suggestion, **When** the human runs the maverick-review
   sweep, **Then** the suggested resolution is presented as the default option,
   visibly attributed to the prior decision, alongside the entry's own alternatives
   and free-form input.
4. **Given** an entry with a suggestion, **When** `maverick land` evaluates the
   frontier before the human resolves the entry, **Then** the entry still blocks
   landing exactly as an entry with no suggestion would.
5. **Given** several prior decisions match a new entry above threshold, **When** the
   suggestion is computed, **Then** exactly one suggestion — the highest-confidence
   match, ties broken deterministically — is attached.

---

### User Story 3 - Rejected suggestions stop being suggested (Priority: P3)

When the human resolves an entry differently from its suggestion — a different answer,
or a waive where an answer was suggested — that outcome is recorded as a rejection of
the pairing between that question shape (its normalized question text) and that prior
decision. The pairing's future
confidence is lowered so the same wrong default is not presented again. A wrong
suggestion presented as a default is worse than no suggestion, so the system must
learn from its misses, not just its hits.

**Why this priority**: This is the quality control that makes User Story 2 safe to
trust. Without it, one bad match becomes a recurring default the human must fight
every sweep.

**Independent Test**: Present a suggestion, resolve the entry with a different answer,
then record a new assumption with the same question shape; verify the previously
rejected pairing either no longer surfaces as a suggestion or surfaces with a lowered
confidence below the presentation threshold.

**Acceptance Scenarios**:

1. **Given** an entry whose suggestion came from decision record R, **When** the human
   answers with different text, **Then** a rejection is recorded for the pairing of
   that question shape and R, and the pairing's future match confidence is lowered.
2. **Given** a pairing rejected once, **When** a new entry with the same question
   shape is recorded, **Then** that pairing does not surface as the default suggestion
   unless subsequent confirming signal has restored its confidence above threshold.
3. **Given** an entry whose suggestion the human accepts as-is, **When** the entry is
   resolved, **Then** the acceptance is recorded on the pairing so match quality is
   auditable over time.

---

### User Story 4 - Opt-in auto-resolution for high-confidence low-severity entries (Priority: P4)

A project may explicitly enable a policy that auto-resolves low-severity entries whose
match confidence exceeds a configured threshold. Auto-resolved entries are marked as
such on the ledger, carry the source decision's provenance, and are visibly distinct
from human-answered entries everywhere entries render — the review list, the land
report, and the land banner. A land that relied on any auto-resolved entry is at most
conditionally-verified, never verified. The policy is off by default and never applies
to medium or high severity regardless of confidence.

**Why this priority**: This is the "fleet stops asking" end state, but it is only safe
once the corpus, matching, and rejection feedback (P1–P3) have proven themselves. It
must remain a deliberate, revocable choice.

**Independent Test**: Enable the policy with a threshold, record a low-severity
assumption matching a prior decision above that threshold, and verify the entry is
resolved without human action, marked auto-resolved with provenance, and that a
subsequent land classifies as conditionally-verified; verify a medium-severity entry
with the same confidence is not auto-resolved.

**Acceptance Scenarios**:

1. **Given** the auto-resolution policy is not configured, **When** a low-severity
   entry matches a prior decision with very high confidence, **Then** the entry
   receives a suggestion only and remains open until a human resolves it.
2. **Given** the policy is enabled with a confidence threshold, **When** a
   low-severity entry's best match meets or exceeds that threshold, **Then** the entry
   is waived automatically with a rationale citing the matched prior decision, stamped
   as auto-resolved with the source decision's provenance, and no longer blocks the
   land gate.
3. **Given** a land whose frontier was cleared partly by auto-resolution, **When**
   `maverick land` classifies the outcome, **Then** the classification is at most
   conditionally-verified, and the land report shows auto-resolved entries distinctly
   from human-answered ones.
4. **Given** an auto-resolved entry, **When** the human re-answers it with different
   text via `maverick review`, **Then** the human's answer supersedes the
   auto-resolution and the override is recorded as a rejection of the pairing that
   auto-resolved it.
5. **Given** the policy is enabled, **When** a medium- or high-severity entry matches
   above the threshold, **Then** it is never auto-resolved.

---

### Edge Cases

- **Knowledge store unavailable or corrupt at match time**: recording a new assumption
  and listing entries must proceed with no suggestions and a warning — suggestion
  machinery degrading must never block capture, review, or landing.
- **Decision-record write fails at resolution time**: the answer or waive itself still
  succeeds on the ledger; the missed record is a warning, not a review failure.
- **Self-match**: an entry must never receive a suggestion sourced from its own
  resolution history.
- **Duplicate or near-duplicate decision records** (the same question resolved on
  several specs): matching selects one best candidate deterministically; the corpus
  growing must not produce duplicate suggestions on one entry.
- **Conflicting prior decisions** (the same question shape answered differently on two
  specs): the suggestion mechanism must resolve to a single candidate by its
  documented scoring and tie-break rules — most recent resolution preferred — rather
  than presenting both or averaging them.
- **Legacy entries with no structured severity**: treated as medium for policy
  purposes (consistent with existing land-gate and scheduler behavior), so they are
  never auto-resolved.
- **Entries recorded before any matching corpus existed**: an open entry recorded
  before a relevant decision record may gain a suggestion when suggestions are next
  evaluated; absence of a suggestion at recording time is not permanent.
- **Waive-sourced suggestions**: a prior waive can suggest waiving a closely matching
  new entry, with the waive reason as the suggested rationale — presented and
  attributed the same way an answer-sourced suggestion is.
- **Threshold misconfiguration**: an auto-resolution threshold configured below the
  presentation threshold, or outside valid bounds, fails validation with a clear
  message rather than silently auto-resolving on weak matches.

## Requirements *(mandatory)*

### Functional Requirements

**Decision records**

- **FR-001**: Every terminal assumption-ledger outcome — answered, waived, and
  re-answered-after-a-prior-answer — MUST persist a structured decision record in the
  project's knowledge store, carrying at minimum: the question, the agent's adopted
  answer, the human's resolution (answer text or waive reason), the resolution type,
  the entry's severity, the owning spec, the source entry's identity, and the
  resolution timestamp.
- **FR-002**: Decision records MUST survive across specs, runs, and sessions; their
  lifecycle is independent of any run directory or workflow invocation.
- **FR-003**: When an entry is re-answered, its decision record MUST treat the latest
  human resolution as authoritative for future matching while preserving the earlier
  resolution as visible history.
- **FR-004**: Failure to persist a decision record MUST NOT fail or block the
  resolution action that triggered it; the miss is surfaced as a structured warning
  and the ledger write proceeds.
- **FR-005**: Only human-initiated resolutions grow the corpus: individual answers and
  waives, and human-invoked bulk waives (one record per covered entry). Machine-initiated
  resolutions — the notification scheduler's auto-waives and this feature's own
  auto-resolutions (FR-016) — MUST NOT feed decision records.

**Matching and suggestions**

- **FR-006**: When a new assumption entry is recorded, it MUST be evaluated against
  existing decision records, and when the best match's confidence meets or exceeds the
  presentation threshold, a suggested resolution MUST be attached to the entry and
  persisted with it. Listing entries back-fills a suggestion for entries that have no
  stored one; an existing stored suggestion is never silently replaced.
- **FR-007**: A suggestion MUST carry provenance: the source decision's entry
  identity, owning spec, resolution date, resolution type, and the match confidence.
- **FR-008**: The definition of "closely matching" and the confidence score MUST be
  deterministic and documented: the same entry evaluated against the same corpus and
  feedback state always yields the same suggestion and score. Suggestion evaluation
  makes zero model calls.
- **FR-009**: When no candidate meets the presentation threshold, the entry MUST carry
  no suggestion — the system prefers silence over a weak guess. The presentation
  threshold is a built-in fixed default, not user-configurable.
- **FR-010**: When multiple candidates exceed the threshold, exactly one suggestion —
  the highest-confidence candidate, ties broken deterministically in favor of the most
  recent resolution — MUST be attached.
- **FR-011**: The suggestion MUST appear as a field on the entry row everywhere entry
  rows render, including `maverick review --list --json` and the land report, using
  the single shared entry-row projection so surfaces cannot drift; entries without a
  suggestion carry an explicit absent value.
- **FR-012**: The maverick-review skill MUST present an entry's suggestion as the
  default option in its sweep, visibly attributed to the prior decision, alongside the
  entry's own adopted answer, alternatives, free-form input, and waive/skip.
- **FR-013**: A suggestion MUST NOT resolve an entry by itself outside the explicit
  auto-resolution policy (FR-016); the land gate's semantics are unchanged, and an
  entry with a suggestion blocks landing exactly as one without.

**Rejection feedback**

- **FR-014**: When the human resolves an entry differently from its suggestion, the
  system MUST record a rejection for the pairing and lower the pairing's future match
  confidence; when the human accepts a suggestion, the acceptance MUST likewise be
  recorded. A pairing is identified as (normalized question text of the new entry,
  source decision record identity), where normalization is deterministic — case-fold,
  collapse whitespace, strip punctuation.
- **FR-015**: A rejected pairing MUST NOT be presented as a default suggestion again
  unless subsequent confirming feedback restores its confidence above the presentation
  threshold; suppression state persists across runs alongside the decision corpus.

**Auto-resolution policy**

- **FR-016**: An explicitly configured, default-off policy MAY auto-resolve
  low-severity entries whose best-match confidence meets or exceeds a configured
  auto-resolution threshold; the threshold MUST be at least as strict as the built-in
  presentation threshold, and configuration violating this MUST fail validation.
  Auto-resolution always resolves via the waive path with a recorded rationale citing
  the matched prior decision — it never writes an answer, so a machine decision can
  never enter reconcile's answered-entry detection or drive history rewriting.
- **FR-017**: Auto-resolution MUST never apply to medium- or high-severity entries
  (including legacy entries with no structured severity, which are treated as medium),
  regardless of confidence.
- **FR-018**: An auto-resolved entry MUST be marked as auto-resolved on the ledger —
  a waive stamped with the source decision's provenance and rationale, attributable to
  the resolving machinery rather than a human — and MUST be visually and structurally
  distinguishable from human-resolved entries in the review list, the land report, and
  any JSON projection.
- **FR-019**: A land whose frontier evaluation relied on one or more auto-resolved
  entries MUST classify as at most conditionally-verified.
- **FR-020**: A human re-answering an auto-resolved entry MUST supersede the
  auto-resolution; the override counts as a rejection of the pairing that produced it
  and re-enters the entry into normal downstream lifecycle (including reconcile
  detection where applicable).

**Degradation and safety**

- **FR-021**: Unavailability or corruption of the knowledge store MUST degrade to
  no-suggestion behavior with a structured warning; it MUST NOT block assumption
  capture, review listing, entry resolution, or landing.
- **FR-022**: All new behavior MUST be scoped to the current repository's knowledge
  store; no decision record, suggestion, or feedback signal crosses repositories.

### Key Entities

- **Decision record**: the durable trace of one human resolution of one
  assumption-ledger entry — question, adopted answer, human resolution, resolution
  type (answered / waived / re-answered), severity, owning spec, source entry
  identity, timestamp, and resolution history. Lives in the project knowledge store,
  outliving specs and runs.
- **Suggestion**: a proposal attached to an open ledger entry, derived from the single
  best-matching decision record — suggested resolution text, resolution type,
  provenance (source entry, spec, date), and confidence score. Advisory only.
- **Match feedback**: the accumulated accept/reject history for a pairing, keyed by
  (normalized question text, source decision record identity) — normalization is
  deterministic: case-fold, collapse whitespace, strip punctuation. Used to raise or
  lower that pairing's future confidence. Persists alongside the decision corpus.
- **Auto-resolution policy**: project configuration declaring whether auto-resolution
  is enabled, its confidence threshold, and (implicitly) its severity ceiling of low.
  Absent configuration means the capability is inert.
- **Auto-resolution stamp**: the ledger-side marking on an entry resolved by policy —
  distinguishable resolution kind, source decision provenance, and rationale — feeding
  the land report's distinct rendering and the at-most-conditionally-verified
  classification.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of terminal ledger outcomes performed through the review surfaces
  produce a retrievable decision record with complete provenance, verified across at
  least two consecutive specs' lifecycles in one repository.
- **SC-002**: When a newly recorded assumption's question closely matches a prior
  decision, the prior resolution is available as the entry's default at the very next
  review interaction — the human confirms it with a single selection instead of
  composing an answer.
- **SC-003**: After a suggestion is rejected once, the same question shape does not
  surface that pairing as a default again in subsequent sweeps (absent new confirming
  feedback), verified over repeated recording of matching entries.
- **SC-004**: Zero entries carry a suggestion whose confidence is below the
  presentation threshold, and zero entries are auto-resolved below the auto-resolution
  threshold or above low severity — across the full test matrix.
- **SC-005**: Every land that relied on any auto-resolved entry is classified at most
  conditionally-verified, and its report distinguishes auto-resolved from
  human-answered entries in 100% of cases.
- **SC-006**: With a corpus of at least 500 decision records, suggestion evaluation
  adds no human-perceptible delay to recording or listing entries (under one second of
  added latency).
- **SC-007**: A simulated knowledge-store outage during capture, review, and land
  produces zero blocked operations and zero lost ledger writes — only absent
  suggestions and warnings.

## Assumptions

- **Matching is deterministic, not model-driven.** Consistent with the project's
  determinism-over-inference principle, "closely matching" is defined by a
  deterministic, documented similarity mechanism over question text and structure;
  the concrete algorithm and score formula are plan-phase decisions, but zero model
  calls is a requirement (FR-008), not a preference.
- **The knowledge store is the existing per-repository runway store.** Decision
  records and match feedback live in the same durable knowledge layer the project
  already maintains under the repository's Maverick state, not a new external system.
- **Suggestions are computed and persisted at recording time**; listing back-fills a
  suggestion only for entries that have no stored one, so entries that predate a
  relevant decision can still gain suggestions. An existing stored suggestion is never
  silently replaced, so a suggestion is stable within and across sweeps.
- **Rejection is defined behaviorally**: resolving an entry with anything other than
  the suggested resolution (different answer text, or waive where an answer was
  suggested) counts as rejecting the pairing; accepting the presented default counts
  as confirmation.
- **The existing severity semantics are unchanged**: severity continues to come from
  the capturing agent; legacy entries without structured severity are treated as
  medium, matching current land-gate and scheduler behavior.
- **Auto-resolution reuses the existing waive lifecycle** rather than a new terminal
  state, so downstream consumers (land gate, reports, reconcile) see a coherent
  lifecycle; the distinguishing mark is carried as provenance on the entry. Waiving —
  never answering — is what keeps machine decisions out of reconcile's history
  rewriting.
- **Cross-repository sharing is out of scope**, as is any change to how agents capture
  assumptions; the capture payloads and recording flow are untouched.
