# Contract: ntfy notification payload

**Single canonical wrapper** (Guardrail 5):
`src/maverick/assumptions/schedule/deliver.py` is the only module that may
construct ntfy requests.

## Request

```
POST {notifications.server}/{notifications.topic}
Title:    <title per kind, below>
Priority: <priority per kind, below>
Tags:     maverick,assumptions
Body:     <plain-text summons, below>
```

- Client: `httpx.AsyncClient`, explicit 10-second timeout.
- Retries: `tenacity.AsyncRetrying`, 3 attempts, exponential backoff, retrying
  on `httpx.TransportError` and HTTP 5xx; 4xx fails immediately (config
  problem, retrying cannot help).
- Exhausted retries → `delivery-failed` error path; the decision is not
  recorded as delivered (FR-012).

## Content by kind

| Kind | Title | Priority |
|---|---|---|
| `window-batch` | `Assumption review: N open entries` | `default` |
| `interrupt` | `High-severity assumption recorded` | `urgent` |
| `escalation` | `Assumption entries aging past limit` | `urgent` |
| `renotify` | `High-severity assumption still unanswered` | `urgent` |

Body template (all kinds; counts include low as informational context —
clarification Q5):

```
{high} high, {medium} medium, {low} low open across {spec list}.
Oldest: {oldest_age_hours}h.
Run: {review_invocation}
```

`review_invocation` is the exact command to start the sweep
(`maverick review --list --status open`, spec-scoped variant when all entries
share one owning spec: `maverick review --list --spec {spec} --status open`).

## Prohibitions (FR-008)

The payload MUST NOT contain: entry question text, adopted answers,
alternatives, waive reasons, bead descriptions, or any other entry content.
The notification is a summons, not the console. (Bead **ids** are likewise
omitted from the push body — they appear only in local persisted state — so
nothing entry-specific transits ntfy beyond counts, spec names, and age.)

Enforced structurally: `BatchSummary` (the only input `deliver.py` accepts)
carries no content fields, so a leak would require a type-level change, not a
formatting slip.

## Test hooks

Unit tests exercise the deliverer with `httpx.MockTransport` — asserting URL,
headers, body template, retry-on-5xx, no-retry-on-4xx, and that failure
surfaces as the typed delivery error consumed by the command layer.
