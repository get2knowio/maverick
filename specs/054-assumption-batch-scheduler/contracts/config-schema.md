# Contract: configuration schema (`maverick.yaml`)

Two blocks cooperate: the **new** `assumptions.schedule` block (delivery
policy) and the **existing** `notifications` block (ntfy endpoint — reused
unchanged, first consumer).

## Full example

```yaml
notifications:
  enabled: true
  server: https://ntfy.sh        # default
  topic: my-maverick-topic       # required for delivery

assumptions:
  schedule:
    windows: ["09:00", "17:00"]  # required, >=1, HH:MM local time, unique
    quiet_hours:                 # optional; absent => no quiet hours
      start: "22:00"
      end: "07:00"               # may be earlier than start (spans midnight)
    high_overrides_quiet: true   # default true (FR-004)
    min_batch_size: 1            # default 1, >=1 (FR-005)
    max_entry_age_hours: 24      # default 24, >=1 (FR-006)
    renotify_backoff_hours: [4, 8, 16, 24]  # default; non-decreasing, >0;
                                            # last value repeats (FR-007)
    auto_waive_low:              # optional; absent => never auto-waive (FR-015)
      enabled: true              # default false — double opt-in with presence
      after_hours: 168           # default 168 (7 days), >=1
      rationale: "accepted-risk: low-severity assumptions expire after a week"
```

## Model placement

- `MaverickConfig.assumptions: AssumptionsConfig` (new, `default_factory`).
- `AssumptionsConfig.schedule: AssumptionScheduleConfig | None = None`.
- Loading, env overrides (`MAVERICK_ASSUMPTIONS__SCHEDULE__...`), and
  precedence follow the existing `load_config` / `YamlConfigSource` stack
  untouched.

## Validation semantics

| Condition | Behavior | Where |
|---|---|---|
| `assumptions.schedule` absent | Command inert: exit 0, "not configured" (FR-021) | notify command |
| `windows` empty / bad `HH:MM` / duplicates | `ConfigError`/`ValidationError` at load | Pydantic validators |
| `quiet_hours.start == end` | rejected (ambiguous: zero- or full-day quiet) | Pydantic validator |
| `renotify_backoff_hours` empty, non-positive, or decreasing | rejected | Pydantic validator |
| `auto_waive_low.enabled: true` without `rationale` | rejected | Pydantic validator |
| schedule present, `notifications.enabled: false` or `topic` unset | `validation` error naming the exact key to fix (FR-009) | notify command (the existing `NotificationConfig` validator only warns; other consumers keep that behavior) |

## Interpretation rules

- All times are **machine-local wall-clock** (`datetime.now().astimezone()`);
  no per-config timezone override (spec Assumptions).
- Each window time yields at most one occurrence per local calendar date;
  occurrences are deadlines-to-deliver-after, not instants (FR-020, research
  R6 covers DST fold/gap handling).
- A window occurrence inside quiet hours shifts its due time to quiet-hours
  end — same occurrence identity, so no double delivery (research R8).
- `high_overrides_quiet` gates high-severity interrupts **and** high-severity
  escalation re-notifications identically.
- Defaults were fixed at plan time (clarify deferred them): `min_batch_size=1`,
  `max_entry_age_hours=24`, backoff `4→8→16→24h` then repeating `24h`,
  `auto_waive_low.after_hours=168`.
