# Contract: `assumptions.resolution` Configuration Block

New optional block in `maverick.yaml`, sibling to 054's `assumptions.schedule`:

```yaml
assumptions:
  resolution:
    auto_resolve_low:
      enabled: true                # default: false — double opt-in with the block itself
      confidence_threshold: 0.92   # default 0.9; must be >= 0.75 and <= 1.0
```

## Semantics

| State | Behavior |
|---|---|
| `assumptions.resolution` absent (default) | Suggestions fully functional (they require no config); auto-resolution inert |
| Block present, `auto_resolve_low` absent or `enabled: false` | Same as absent — suggestions only |
| `enabled: true` | Low-severity entries with effective confidence ≥ `confidence_threshold` are auto-waived at recording time by `"maverick-resolver"` |

## Validation (fails config load, FR-016)

- `confidence_threshold` bounds: `ge=0.75`, `le=1.0`. The lower bound equals the
  built-in `PRESENTATION_THRESHOLD` — "auto must be at least as strict as
  presentation" (clarify Q3) — and a unit test pins the config bound to the
  constant so they cannot drift.
- Types per Pydantic; unknown keys ignored per `MaverickConfig` (`extra="ignore"`).

## Model classes (`src/maverick/config.py`)

```python
class AutoResolvePolicyConfig(BaseModel):
    enabled: bool = False
    confidence_threshold: float = Field(default=0.9, ge=0.75, le=1.0)

class AssumptionResolutionConfig(BaseModel):
    auto_resolve_low: AutoResolvePolicyConfig | None = None

class AssumptionsConfig(BaseModel):
    schedule: AssumptionScheduleConfig | None = None      # existing (054)
    resolution: AssumptionResolutionConfig | None = None  # new (055)
```

The presentation threshold itself is **not** configurable (clarify Q3); there is no
key for it, and requests to tune it route to the contract in
[decision-records.md](decision-records.md).
