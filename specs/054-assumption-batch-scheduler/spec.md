# Feature Specification: Assumption Batch Scheduler

**Feature Branch**: `054-assumption-batch-scheduler`

**Created**: 2026-08-05

**Status**: Draft

**Input**: User description: "Add schedule-respecting, severity-tiered delivery of assumption-ledger entries to the human, so that questions raised by agents reach the human in batches that match the human's schedule instead of requiring them to poll `maverick brief`."

## Clarifications

### Session 2026-08-05

- Q: What should the scheduler command do when no assumptions schedule block is configured? → A: It is inert — exit success with a clear "not configured" report, deliver nothing; there is no built-in default schedule, delivery is strictly opt-in.
- Q: Which severities does maximum-entry-age escalation actually deliver? → A: Medium and high escalate to delivery; only high re-notifies on a backoff schedule afterwards; low is never delivered proactively — its only aging path is the opt-in auto-waive policy.
- Q: Should the evaluation command offer a machine-readable output mode? → A: Yes — a `--json` mode emitting the shared JSON verb envelope, carrying the full evaluation outcome (what was delivered, what was skipped, and the rule that decided each).
- Q: How long must persisted delivery records be retained? → A: While any covered entry remains open, plus 90 days after all covered entries reach a terminal state; only then may they be pruned.
- Q: Do batch notification counts-by-severity include low-severity entries? → A: Yes, as informational context — but low entries never trigger or block a delivery.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Batched morning summons (Priority: P1)

A human running autonomous overnight work has configured review windows at 09:00 and 17:00 with quiet hours from 22:00 to 07:00. Agents record several medium- and low-severity assumption-ledger entries overnight. At 09:00 the human receives exactly one push notification summarizing everything that accumulated: counts by severity, the owning specs, the age of the oldest entry, and the exact `maverick review` invocation to start the sweep. The human opens their terminal, runs the printed command, and works the queue.

**Why this priority**: This is the core value of the feature — the human stops polling `maverick brief` and instead gets summoned on their own schedule. Without it, nothing else in this feature matters.

**Independent Test**: Seed a ledger with medium-severity entries recorded at various times overnight, run the scheduler evaluation at a simulated 09:00 with the configuration above, and verify exactly one notification is delivered carrying the correct counts, owning specs, oldest-entry age, and review invocation — and that entry contents (question/answer text) are absent.

**Acceptance Scenarios**:

1. **Given** quiet hours 22:00–07:00 and windows at 09:00 and 17:00, with three medium-severity entries recorded overnight, **When** the scheduler evaluates at 09:00, **Then** exactly one batch notification is delivered summarizing all three entries.
2. **Given** the same configuration, **When** the scheduler evaluates at 03:00 (inside quiet hours) with medium-severity entries pending, **Then** nothing is delivered and the entries remain accumulated for the 09:00 window.
3. **Given** a batch notification, **When** its content is inspected, **Then** it carries count by severity, the owning specs, the oldest entry's age, and the exact `maverick review` invocation — and never the entry's question or answer text.
4. **Given** a window whose pending batch is smaller than the configured minimum batch size, **When** the scheduler evaluates at that window, **Then** the window is skipped and the entries roll to the next window.
5. **Given** low-severity entries only, **When** any window arrives, **Then** no notification is delivered — low-severity entries accumulate silently and surface only during a review sweep or bulk waive.

---

### User Story 2 - High-severity interrupt (Priority: P2)

An agent records a high-severity assumption that is blocking downstream work. The human is notified at the next scheduler evaluation regardless of review windows, because high severity means "interrupt", not "batch". If the entry is recorded during quiet hours, the default policy still delivers it (high overrides quiet hours), but a human who has explicitly configured quiet hours as absolute is not disturbed until quiet hours end.

**Why this priority**: High-severity entries gate downstream work via blocks edges; hours of latency on them stalls the fleet. But the interrupt path is meaningless without the delivery machinery from Story 1.

**Independent Test**: Record a high-severity entry, run the scheduler evaluation outside any window, and verify an interrupt notification is delivered immediately; repeat inside quiet hours under both override policies and verify delivery matches the configured policy.

**Acceptance Scenarios**:

1. **Given** a high-severity entry recorded at 14:23 with windows at 09:00 and 17:00, **When** the scheduler next evaluates, **Then** an interrupt notification for that entry is delivered without waiting for the 17:00 window.
2. **Given** a high-severity entry recorded at 23:30 and the default quiet-hours policy, **When** the scheduler evaluates during quiet hours, **Then** the interrupt is delivered (high overrides quiet hours by default).
3. **Given** the same entry and an explicit configuration that quiet hours are absolute, **When** the scheduler evaluates during quiet hours, **Then** nothing is delivered, and the interrupt is delivered at the first evaluation after quiet hours end.
4. **Given** a delivered high-severity interrupt that remains unanswered past the configured maximum entry age, **When** subsequent evaluations run, **Then** the entry re-notifies on a backoff schedule rather than on every evaluation.

---

### User Story 3 - Idempotent evaluation from cron (Priority: P3)

The human wires the scheduler command into cron (or a systemd timer) to run every few minutes. Each run evaluates the ledger against the schedule and delivers anything due. Re-running within the same window never re-delivers the same batch; every delivery is recorded in persisted state so the human can prove, after the fact, why each notification fired — or why one did not.

**Why this priority**: Without idempotence and persisted delivery state, a cron-driven scheduler would spam duplicates and the feature's behavior would be unauditable. This story makes Stories 1 and 2 safe to automate.

**Independent Test**: Run the scheduler command twice in succession within the same window against the same ledger state and verify the second run delivers nothing; inspect persisted delivery state and verify it records what was delivered, when, and which entries each delivery covered.

**Acceptance Scenarios**:

1. **Given** a batch delivered at the 09:00 window, **When** the scheduler runs again at 09:05 with no new entries, **Then** nothing is re-delivered.
2. **Given** a batch delivered at the 09:00 window, **When** a new medium-severity entry is recorded at 09:10, **Then** that entry waits for the 17:00 window rather than triggering an immediate second batch.
3. **Given** any sequence of evaluations, **When** the persisted delivery state is inspected, **Then** it records each delivery (what, when, which entries) such that the outcome of every evaluation is reproducible from the ledger state, the configuration, and the delivery state.
4. **Given** a delivery attempt that fails (notification service unreachable), **When** the scheduler next evaluates, **Then** the batch is re-attempted — a failed delivery is never recorded as delivered.
5. **Given** two scheduler processes started concurrently (overlapping cron fires), **When** both evaluate the same due batch, **Then** the batch is delivered exactly once.

---

### User Story 4 - Age-based escalation and explicit expiry (Priority: P4)

Entries do not linger forever. An undelivered or unanswered medium- or high-severity entry past the configured maximum age escalates regardless of batching rules: it is delivered (or re-delivered) even if its window's minimum batch size was never met. Separately, a human who has explicitly opted in may configure aged low-severity entries to be auto-waived, with the rationale recorded on the ledger entry. Nothing ever expires silently.

**Why this priority**: This is the safety net around the batching rules — it prevents the minimum-batch-size and low-severity-silence rules from starving entries indefinitely. It refines Stories 1–3 rather than standing alone.

**Independent Test**: Configure a maximum entry age, seed entries that would otherwise never meet the minimum batch size, advance past the age threshold, and verify they are delivered anyway; enable the auto-waive policy for low severity and verify aged low entries are waived with a recorded rationale and appear in ledger reporting as waived.

**Acceptance Scenarios**:

1. **Given** a single medium-severity entry below the minimum batch size that keeps rolling forward, **When** its age exceeds the configured maximum entry age, **Then** it is delivered at the next permissible evaluation despite the minimum-batch-size rule.
2. **Given** the auto-waive policy is not configured, **When** low-severity entries age past any threshold, **Then** they are never waived automatically — they remain open and continue to block `maverick land` per existing enforcement semantics.
3. **Given** the auto-waive policy is explicitly enabled for low severity, **When** a low-severity entry ages past the configured threshold, **Then** it is waived with a recorded rationale on the ledger entry, and the waiver is visible through existing review/land reporting surfaces.
4. **Given** any entry that reaches a terminal state via this feature (auto-waived), **When** the ledger is inspected, **Then** the entry shows who/what resolved it and why — nothing expires without a persisted record.

---

### Edge Cases

- Quiet hours spanning midnight (22:00–07:00) must suppress deliveries correctly on both sides of the day boundary.
- A review window that falls inside quiet hours: quiet hours win — the window's batch rolls to the first evaluation after quiet hours end (except high-severity interrupts under the default override policy).
- An entry answered or waived between accumulation and the delivery window must not be counted in the delivered batch; a batch whose entries have all been resolved before the window delivers nothing.
- Daylight-saving transitions: local-time windows fire once per local day; a skipped or repeated wall-clock hour must not cause a double delivery or a silently missed window.
- The scheduler run may be arbitrarily delayed relative to a window (cron granularity, machine asleep): a window whose time has passed but whose batch was never delivered is still due at the next evaluation — windows are deadlines to deliver after, not instants to hit exactly.
- Notification service misconfigured or unreachable: the evaluation still runs, the failure is reported clearly, and no delivery is recorded; the batch remains due.
- Ledger unreadable at evaluation time: the run fails with a clear diagnostic; it must not record deliveries or mutate state based on a partial read.
- Entries in the legacy severity bucket (no structured severity) must map to a defined delivery tier rather than being dropped from delivery evaluation.
- Machine timezone differs from the human's expectation: windows and quiet hours are interpreted in the machine's local timezone, and delivery state records enough timing context to make that auditable.
- No assumptions schedule block configured: the command is inert and says so — it must not error, must not invent a default schedule, and must deliver nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an idempotent evaluation command that reads the assumption ledger, evaluates it against the configured schedule, delivers anything due, and exits — with no resident process required. The command MUST be safe to run at any frequency from cron or a systemd timer.
- **FR-002**: The system MUST implement a severity-tiered delivery policy: high-severity entries are delivered as interrupts at the next evaluation after recording; medium-severity entries accumulate and are delivered as a batch at the next configured review window; low-severity entries accumulate silently and are never delivered proactively.
- **FR-003**: Delivery scheduling MUST be configurable in the project configuration file under an assumptions schedule block, covering: review windows as local times of day, quiet hours, the quiet-hours override policy for high severity, a minimum batch size, and a maximum entry age.
- **FR-004**: During quiet hours, the system MUST deliver nothing except high-severity interrupts when the override policy permits them. The override policy MUST default to allowing high-severity interrupts through quiet hours, and MUST be explicitly configurable to make quiet hours absolute.
- **FR-005**: A review window whose pending batch is smaller than the configured minimum batch size MUST be skipped, with the pending entries rolling to the next window.
- **FR-006**: An undelivered or unanswered medium- or high-severity entry older than the configured maximum entry age MUST escalate: it becomes due for delivery (or re-delivery) regardless of minimum-batch-size and window rules, subject only to the quiet-hours policy. Low-severity entries never escalate to delivery; their only aging path is the opt-in auto-waive policy (FR-015).
- **FR-007**: An unanswered high-severity entry past its maximum age MUST re-notify on a backoff schedule — successive re-notifications spaced increasingly far apart — rather than on every evaluation. An escalated medium-severity entry is delivered once per escalation and does not re-notify.
- **FR-008**: Batch notifications MUST carry: entry count by severity (including low, as informational context — low entries never trigger or block a delivery), the owning specs, the oldest entry's age, and the exact `maverick review` invocation to start the sweep. Notifications MUST NOT carry entry contents (question, adopted answer, alternatives) — the notification is a summons, not the console.
- **FR-009**: Delivery MUST use the ntfy push-notification service. Absent or invalid ntfy configuration MUST produce a clear, actionable error from the evaluation command, not a silent no-op.
- **FR-010**: Re-running the evaluation within the same window against unchanged ledger state MUST NOT re-deliver a batch already delivered. Idempotence MUST hold across process restarts (state is persisted, not in-memory).
- **FR-011**: The system MUST persist delivery state — what was delivered, when, to which window or trigger, and covering which entries — such that the outcome of any evaluation is deterministic and auditable from the ledger state, the configuration, and the persisted delivery state.
- **FR-012**: A failed delivery attempt MUST NOT be recorded as delivered; the batch or interrupt remains due at the next evaluation. Delivery failures MUST be reported clearly to the invoker.
- **FR-013**: Concurrent evaluation runs (e.g. overlapping cron fires) MUST NOT double-deliver: at most one of the concurrent runs delivers any given due batch or interrupt.
- **FR-014**: Entries resolved (answered or waived) between accumulation and delivery MUST be excluded from the delivered batch. A batch left empty by resolution delivers nothing.
- **FR-015**: The system MAY auto-waive aged low-severity entries only under an explicitly configured opt-in policy. Auto-waived entries MUST carry a recorded rationale on the ledger entry and MUST be distinguishable from human-waived entries in ledger reporting. Absent the opt-in, no entry is ever auto-resolved.
- **FR-016**: No entry may ever leave delivery evaluation silently: an entry leaves the scheduler's tracking only via a persisted terminal outcome — resolved by a human, or auto-waived with rationale. Deliveries themselves never end tracking; they are recorded as audit records under FR-011 while the entry remains tracked until resolved.
- **FR-017**: The evaluation logic MUST be invocable without assuming a resident process, and MUST be structured so a future host daemon can invoke the same evaluation in-process. Nothing in the feature may depend on residency, background threads, or long-lived scheduling state in memory.
- **FR-018**: This feature MUST NOT change enforcement semantics: the land gate, ready-queue deferral, and blocks-edge behavior for assumption entries are untouched. Delivery is a notification layer only.
- **FR-019**: Entries carrying only legacy severity metadata MUST be assigned a defined delivery tier (treated as medium) so they participate in batching rather than being invisible to delivery.
- **FR-020**: Windows and quiet hours MUST be interpreted in the machine's local timezone, and behavior across daylight-saving transitions MUST avoid both double delivery and silently missed windows. A window whose time has passed without delivery remains due at the next permissible evaluation.
- **FR-021**: When no assumptions schedule block is configured, the evaluation command MUST be inert: it exits successfully, reports clearly that delivery is not configured, and delivers nothing. There is no built-in default schedule — delivery is strictly opt-in.
- **FR-022**: The evaluation command MUST offer a machine-readable output mode (`--json`) emitting the shared JSON verb envelope used by the other assumption-lifecycle verbs, carrying the full evaluation outcome: what was delivered, what was skipped, and the rule that decided each.
- **FR-023**: Delivery records MUST be retained for as long as any entry they cover remains open, and for at least 90 days after every covered entry reaches a terminal state; only then may they be pruned. Pruning MUST never remove a record needed to prove why an open entry's notification fired or was skipped.

### Key Entities

- **Schedule configuration**: The human's delivery policy — review windows (local times of day), quiet hours (a local-time range, possibly spanning midnight), quiet-hours override policy for high severity, minimum batch size, maximum entry age, re-notification backoff parameters, and the optional low-severity auto-waive policy. Lives in the project configuration file.
- **Assumption-ledger entry** (existing): The unit being delivered. Relevant attributes: severity (high/medium/low or legacy), status (open/answered/waived), recording time, owning spec. This feature reads entries and — only under the opt-in auto-waive policy — resolves them; it does not otherwise mutate them.
- **Delivery record**: The persisted, append-style account of one delivery: what kind (window batch, high-severity interrupt, escalation re-notification), when it was delivered, which window or trigger caused it, and which entries it covered. The source of truth for idempotence and audit. Retained while any covered entry is open, plus 90 days after all covered entries reach a terminal state; prunable only after that.
- **Batch**: The evaluated set of due, still-open entries grouped for one notification, summarized as counts by severity, owning specs, and oldest-entry age.
- **Notification**: The outbound message delivered via the push service — a summons carrying the batch summary and the exact review invocation, never entry contents.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A human with quiet hours 22:00–07:00 and windows at 09:00 and 17:00 receives exactly one notification at the 09:00 window summarizing everything that accumulated overnight — verified across a simulated multi-day run with entries recorded at arbitrary hours.
- **SC-002**: High-severity entries reach the human at the first evaluation after recording (subject only to the configured quiet-hours policy), while medium-severity entries never generate a notification outside a review window and low-severity entries never generate a notification at all.
- **SC-003**: Running the evaluation command any number of times within one window produces at most one delivery of a given batch — zero duplicate notifications across a test matrix of repeated and concurrent invocations.
- **SC-004**: For every notification delivered (and every window skipped), the human can reconstruct from persisted state alone why it fired or was skipped — which entries, which rule (window, interrupt, escalation, minimum-batch-size skip), and when.
- **SC-005**: No entry is ever dropped from tracking without a persisted outcome: across a simulated run including resolutions, escalations, and (opted-in) auto-waivers, 100% of recorded entries are accounted for as delivered, human-resolved, or auto-waived-with-rationale.
- **SC-006**: The human polls nothing: in a workflow driven entirely by scheduler notifications, the human runs `maverick brief` zero times and still learns of every open entry within one review window of its recording (or immediately, for high severity).

## Assumptions

- "Immediate" delivery for high-severity interrupts means at the next scheduler evaluation, since there is no resident process; the effective interrupt latency is bounded by the cron/timer frequency the human chooses. This is inherent to the daemonless design and acceptable.
- The scheduler evaluates one repository's ledger per invocation, consistent with Maverick's single-repo workflow model; multi-repository aggregation is out of scope.
- ntfy connection details (server URL, topic) are part of the new configuration surface; the feature assumes the human has a working ntfy subscription on their devices. Validating ntfy reachability is done per delivery attempt, not ahead of time.
- Delivery state is persisted under the repository's existing Maverick state area alongside runs and plans, and is not intended to be committed or shared between machines. Two machines running schedulers against clones of the same repository are out of scope.
- Local times in configuration are interpreted in the machine's local timezone; no per-config timezone override is provided in this feature.
- The default for the low-severity auto-waive policy is off; the default quiet-hours override policy is that high severity interrupts through quiet hours — both as stated in the feature description.
- Legacy-severity entries (open escalation beads without structured severity) are treated as medium for delivery, mirroring how the land gate already treats them.
- Answered-but-unreconciled entries are not the scheduler's concern: delivery targets open entries awaiting a human decision. Reconciliation prompting remains with existing `maverick land`/`maverick reconcile` surfaces.
- The exact CLI command name and its placement in the existing command tree are deferred to planning; the feature requires only that it be a single idempotent command suitable for cron.
- Out of scope, per the feature description: Slack/email/other channels, learned auto-resolution from prior answers, and any change to enforcement semantics.
