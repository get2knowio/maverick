# Contract: Supported Spec Kit artifact grammar

**Feature**: 048-speckit-refuel-ingestion
**Supported template versions**: `>=0.14,<0.15` (constant `SUPPORTED_SPECKIT_RANGE` in `speckit/detect.py`)
**Version source**: `.specify/init-options.json` → `speckit_version`. Absent file/field → status `unknown`: warn and parse structurally (D5).

## Feature directory shape

```
specs/NNN-name/
├── spec.md      REQUIRED
├── tasks.md     REQUIRED
└── plan.md      optional (noted if absent; never parsed for structure)
```

`NNN` = 3+ digits. Shape check failure → E02.

## tasks.md grammar (line-oriented)

```ebnf
tasks_file      = { ignored_line | phase_section } ;
phase_section   = phase_heading , { task_line | ignored_line } ;
phase_heading   = "## Phase " , integer , [ ":" , title_text ] ;
task_line       = "- [" , (" " | "x" | "X") , "] " , task_id ,
                  [ " [P]" ] , [ " [US" , integer , "]" ] , " " , description ;
task_id         = "T" , 3*digit ;
```

- **Phase headings**: `## Phase <n>: <title>`. Numbers must be strictly increasing in file order (violation → E05). Content before the first phase heading is ignored.
- **Task lines**: only recognized *inside* a phase section. Marker order is fixed: checkbox, ID, `[P]`, `[USn]`, description. A line matching `- [ ]`/`- [x]` inside a phase that does **not** match the full task grammar is a **hard error** (E05: file, line, expected pattern, suggestion) — never silently skipped (SC-002).
- **Ignored lines**: prose, `**Checkpoint**` lines, `###` subheadings, blank lines, HTML comments, fenced code blocks (fence-aware skipping), and any `## ` heading that is not `## Phase …` (terminates the current phase section).
- **Explicit dependencies** (parsed from description text, case-insensitive): `(depends on T012[, T013…])` or `depends on: T012[, T013…]`. Referenced IDs must exist in the file (E06).
- **File paths**: whitespace-delimited tokens in the description containing `/` and a file extension, or ending in `/`. Extraction is best-effort (empty is valid).
- **Duplicate task IDs** anywhere in the file → E06 with both line numbers.
- **Dependencies section** (optional): a `## Dependencies` (or `## Dependencies & Execution Order`) section; lines matching `US<n>: Depends on US<m>[, US<k>…]` add story-level dependency pairs. All other content in that section is ignored (the phase barrier already encodes phase ordering).

## spec.md extraction (best-effort except where noted)

| Element | Pattern | On absence |
| --- | --- | --- |
| Feature title | `# Feature Specification: <title>` (fallback: first `# ` heading) | fallback: feature dir name |
| Success criteria | bullets matching `- **SC-\d+**: …` under `## Success Criteria` | warning; epic description omits section |
| Story scenarios | `### User Story <n> …` sections → items under `**Acceptance Scenarios**` | tasks labeled with a missing story get task text only + warning |

spec.md that exists but yields no title and no success criteria and no stories → E05 (likely not a Spec Kit spec).

## Guarantees

1. **Deterministic**: identical inputs → identical `SpeckitFeature` (pure functions, no I/O in `parser.py`).
2. **Total accounting**: every task-shaped line inside a phase is either a parsed task or a hard error — no third outcome.
3. **Error quality**: every E05/E06 carries file path, 1-based line number, expected structure, and a suggested fix.
4. **Version gate**: `unsupported` version fails (E04) before any file is parsed; `unknown` warns and proceeds.
