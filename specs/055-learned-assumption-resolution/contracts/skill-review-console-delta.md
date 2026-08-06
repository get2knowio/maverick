# Contract: maverick-review Skill Delta (Suggestion as Default)

Changes to `src/maverick/skills/review_console/SKILL.md` (installed as
`.claude/skills/maverick-review/SKILL.md`). Everything not listed here is
unchanged from the 053 contract — one `AskUserQuestion` per entry, immediate
application through JSON verbs, overflow chaining, single batched reconcile,
frontier report, land only on explicit confirmation, and the prohibition on
touching jj/git/bd/files directly.

## Option ordering when the entry row carries `suggestion`

1. **The suggested resolution — first option, recommended.**
   - Answer-sourced (`resolution_type: "answered"`): label the option with the
     suggested answer text plus
     `"(Recommended — prior decision from <source_spec>, <resolved_at date>)"`.
   - Waive-sourced (`resolution_type: "waived"`): first option is
     `"Waive this entry (Recommended — prior decision from <source_spec>, <resolved_at date>)"`
     and, when chosen, the suggested reason is used as the waive reason without a
     second prompt (the human saw it on the option).
2. The entry's own `adopted_answer` — second, **without** any "(Recommended)"
   suffix (the suffix moves to the suggestion; exactly one option is ever marked
   recommended).
3. `alternatives[]`, then waive/skip and overflow chaining exactly as today.

When `suggestion` is `null`, the sweep renders exactly as the 053 contract
specifies (adopted answer first with "(Recommended)").

## Decision mapping additions

- Choosing the suggested answer → `maverick review <id> --answer "<suggested text>" --json`.
- Choosing the suggested waive → `maverick review <id> --waive "<suggested reason>" --json`.
- All other choices map exactly as today. The skill never marks
  acceptance/rejection itself — feedback derivation happens inside the CLI verbs
  by comparing the applied resolution against the stored suggestion.

## Auto-resolved entries in the sweep

Entries with `auto_resolved: true` are waived, hence outside the default open-only
sweep. When the human asks to revisit them (e.g. lists waived entries), the skill
presents them with their provenance and offers re-answer — the CLI permits
re-answering auto-resolved entries (FR-020).

## Display obligations

- Always show the suggestion's provenance (source spec + date) in the option
  label or question context — never present a suggested default without saying
  where it came from.
- Show `confidence` in the question context when present; do not editorialize
  beyond the number.
