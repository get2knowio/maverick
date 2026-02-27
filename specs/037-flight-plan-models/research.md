# Research: Flight Plan and Work Unit Data Models

**Feature**: 037-flight-plan-models
**Date**: 2026-02-27

## R1: Pydantic Frozen Model Pattern

**Decision**: Use `model_config = ConfigDict(frozen=True)` for all domain models. Use `@dataclass(frozen=True, slots=True)` only for simple value objects with no validation.

**Rationale**: The codebase uses both patterns — frozen dataclasses in `jj/models.py` (result types with no validation) and Pydantic models in `models/issue_fix.py` (complex models with validators). Flight Plan models need field validators (e.g., kebab-case ID regex, positive integer sequence), so Pydantic is the better fit. Frozen Pydantic models support `model_copy(update={...})` for programmatic modifications.

**Alternatives considered**:
- Plain frozen dataclasses: No built-in validation; would need manual `__post_init__` validators.
- Mutable Pydantic models: Risk of accidental mutation; spec clarification explicitly chose frozen.

## R2: YAML Frontmatter Parsing Strategy

**Decision**: Manual `---` delimiter splitting + `yaml.safe_load()`. Implement a shared `parse_frontmatter(content: str) -> tuple[dict[str, Any], str]` function in `parser.py`.

**Rationale**: The project already depends on PyYAML. The `python-frontmatter` library adds an unnecessary dependency for a simple operation: find the first `---`, find the second `---`, extract the YAML between them, and treat everything after as the Markdown body.

**Algorithm**:
1. Strip leading whitespace. Content must start with `---`.
2. Find the closing `---` (second occurrence).
3. `yaml.safe_load()` the content between delimiters.
4. Return `(metadata_dict, markdown_body)`.
5. Raise `FlightPlanParseError` if delimiters missing or YAML invalid.

**Alternatives considered**:
- `python-frontmatter` library: Works well but adds a dependency for ~20 lines of code.
- Regex-based parsing: Fragile with edge cases (YAML containing `---`).

## R3: Markdown Section Extraction

**Decision**: Parse Markdown body into sections by splitting on `## ` heading markers. Each section is identified by its heading text and contains everything until the next heading of the same or higher level.

**Rationale**: Flight Plan and Work Unit documents use `## Section Name` for top-level sections and `### Subsection` for nested content (e.g., Scope has In/Out/Boundaries). A line-by-line parser that tracks heading levels is simple, predictable, and handles nested subsections.

**Algorithm**:
1. Split body into lines.
2. Identify heading lines (`## `, `### `, etc.) and their levels.
3. Build a dict mapping heading text to content between headings.
4. For sections with subsections (Scope, File Scope), recursively parse.

**Alternatives considered**:
- `markdown` or `mistune` library: Full AST parsing is overkill for this structured format.
- Regex-based splitting: Works but less readable than line-by-line.

## R4: Topological Sort for Dependency Resolution

**Decision**: Adapt the existing DFS-based topological sort from `PrerequisiteRegistry.get_all_dependencies()` in `src/maverick/dsl/prerequisites/registry.py:197-237`. Add parallel-group awareness.

**Rationale**: The codebase already has a proven topological sort with cycle detection. The algorithm uses `visited` and `in_stack` sets for O(V+E) cycle detection. For Work Units, the adaptation needs:
- Input: list of `WorkUnit` objects (not string names).
- `depends_on` field maps to edges.
- `parallel_group` groups units for concurrent execution batching.
- Missing dependency detection (ID not found in the loaded set).

**Algorithm**:
1. Build adjacency map from Work Unit `depends_on` lists.
2. Validate all referenced IDs exist; raise `WorkUnitDependencyError` if not.
3. DFS with `in_stack` for cycle detection.
4. Return `list[list[WorkUnit]]` — each inner list is a batch of parallelizable units.

**Alternatives considered**:
- Kahn's algorithm (BFS-based): Equally valid but DFS is the established pattern.
- `graphlib.TopologicalSorter` (stdlib): Available in Python 3.9+ but lacks parallel group awareness and custom error messages.

## R5: Success Criteria Checkbox Parsing

**Decision**: Parse `- [x]` and `- [ ]` Markdown checkbox syntax into `SuccessCriterion` objects with `checked: bool` and `text: str` fields.

**Rationale**: This is standard GitHub-flavored Markdown checkbox syntax. A simple regex `r'^\s*-\s*\[([ xX])\]\s*(.+)$'` per line handles all cases.

**Algorithm**:
1. Extract the Success Criteria section content.
2. For each line matching the checkbox pattern, create a `SuccessCriterion`.
3. `[x]` or `[X]` → `checked=True`; `[ ]` → `checked=False`.
4. Compute `completion_percentage = checked_count / total * 100` (handle 0/0 as `None`).

## R6: Acceptance Criteria Trace References

**Decision**: Parse Work Unit acceptance criteria as lines with an optional `[SC-###]` trace reference suffix linking to Flight Plan Success Criteria.

**Rationale**: The spec requires traceability links between Work Unit acceptance criteria and Flight Plan success criteria. Using a `[SC-###]` suffix pattern (e.g., `- Criterion text [SC-001]`) is human-readable and parseable. The trace reference is optional — not all acceptance criteria need to map to a specific success criterion.

**Pattern**: `r'\[SC-(\d+)\]\s*$'` at end of line.

## R7: File Scope Sublist Parsing

**Decision**: Parse File Scope section with `### Create`, `### Modify`, `### Protect` subsections, each containing a bullet list of file paths.

**Rationale**: Each sublist serves a distinct purpose (new files, changed files, protected files). The subsection pattern matches the Scope section's In/Out/Boundaries structure, providing consistency.

## R8: Async File Loading

**Decision**: Use `asyncio.to_thread()` for async file I/O, following the pattern in `src/maverick/dsl/checkpoint/store.py`.

**Rationale**: File I/O is blocking. The codebase uses `asyncio.to_thread()` to offload blocking operations. Both `FlightPlanFile` and `WorkUnitFile` provide `load()` (sync) and `aload()` (async) class methods.

**Pattern**:
```python
@classmethod
async def aload(cls, path: Path) -> FlightPlan:
    content = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return cls._parse(content, path)
```
