"""Extracted step functions for FlyBeadsWorkflow bead loop.

Each function receives the workflow instance (for emit_* and _step_executor)
and a BeadContext that threads mutable state through the pipeline.

Invariant-based orchestration: the agent owns implementation + validation
internally, the workflow enforces gates.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.library.actions.beads import (
    create_beads_from_findings,
    defer_bead,
    mark_bead_complete,
)
from maverick.library.actions.jj import (
    jj_commit_bead,
    jj_describe,
    jj_restore_operation,
    jj_snapshot_operation,
)
from maverick.library.actions.review import (
    gather_local_review_context,
    run_review_fix_loop,
)
from maverick.library.actions.runway import (
    record_bead_outcome,
    record_review_findings,
    retrieve_runway_context,
)
from maverick.library.actions.validation import run_independent_gate
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    DEFAULT_BASE_BRANCH,
    DEFAULT_VALIDATION_STAGES,
    GATE_CHECK,
    GATE_REMEDIATION,
    GATE_REMEDIATION_TIMEOUT,
    IMPLEMENT_AND_VALIDATE,
    IMPLEMENT_AND_VALIDATE_TIMEOUT,
    MAX_ESCALATION_DEPTH,
    REVIEW,
)
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.config import ValidationConfig
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


def _build_validation_commands(
    vc: ValidationConfig,
) -> dict[str, tuple[str, ...]]:
    """Convert ValidationConfig to the dict for run_independent_gate."""
    commands: dict[str, tuple[str, ...]] = {}
    if vc.format_cmd:
        commands["format"] = tuple(vc.format_cmd)
    if vc.lint_cmd:
        commands["lint"] = tuple(vc.lint_cmd)
    if vc.typecheck_cmd:
        commands["typecheck"] = tuple(vc.typecheck_cmd)
    if vc.test_cmd:
        commands["test"] = tuple(vc.test_cmd)
    return commands


def _parse_work_unit_sections(
    description: str,
) -> dict[str, str]:
    """Parse a work-unit markdown description into named sections.

    Splits on ``## `` headings and returns a dict keyed by
    lower-cased heading (e.g. ``"task"``, ``"acceptance criteria"``,
    ``"file scope"``, ``"instructions"``, ``"verification"``).
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in description.split("\n"):
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def _parse_file_scope(
    file_scope_text: str,
) -> tuple[list[str], list[str], list[str]]:
    """Parse ``## File Scope`` into create, modify, protect lists."""
    create: list[str] = []
    modify: list[str] = []
    protect: list[str] = []

    current = None
    for line in file_scope_text.split("\n"):
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("### create"):
            current = create
        elif low.startswith("### modify"):
            current = modify
        elif low.startswith("### protect"):
            current = protect
        elif stripped.startswith("- ") and current is not None:
            current.append(stripped[2:].strip())

    return create, modify, protect


def _parse_verification_commands(
    verification_text: str,
) -> list[str]:
    """Extract shell commands from ``## Verification``."""
    commands: list[str] = []
    for line in verification_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        # Skip empty lines and prose (commands start with a tool name)
        if not stripped or stripped[0].isupper():
            continue
        commands.append(stripped)
    return commands


async def run_acceptance_check(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
) -> tuple[bool, list[str]]:
    """Deterministic acceptance-criteria check after gate passes.

    Parses the bead's work-unit markdown to extract File Scope and
    Verification sections, then runs structural checks:

    1. Files listed under Create must exist in the workspace.
    2. Files under Protect must NOT appear in the uncommitted diff.
    3. The diff must overlap with at least one Create/Modify file.
    4. Verification commands (grep/rg) from the decomposer are run.

    Returns ``(passed, reasons)`` where *reasons* lists failures.
    """
    from maverick.workflows.fly_beads.constants import ACCEPTANCE_CHECK

    await wf.emit_step_started(ACCEPTANCE_CHECK)
    reasons: list[str] = []

    sections = _parse_work_unit_sections(ctx.description)
    file_scope_text = sections.get("file scope", "")
    verification_text = sections.get("verification", "")

    # Skip if the bead has no structured sections (follow-up beads)
    if not file_scope_text and not verification_text:
        await wf.emit_step_completed(ACCEPTANCE_CHECK)
        return True, []

    create, modify, protect = _parse_file_scope(file_scope_text)

    # Get files the agent actually changed
    changed = set(await _get_uncommitted_files(ctx.cwd))

    # Check 1: Files under Create must exist
    if create:
        for f in create:
            fpath = ctx.cwd / f if ctx.cwd else Path(f)
            if not fpath.exists():
                reasons.append(
                    f"File scope requires creating '{f}' but "
                    f"it does not exist"
                )

    # Check 2: Protected files must not be in the diff
    if protect and changed:
        for f in protect:
            if f in changed:
                reasons.append(
                    f"File '{f}' is marked as protected but was "
                    f"modified by the implementation"
                )

    # Check 3: Diff must overlap with Create+Modify scope
    expected = set(create + modify)
    if expected and changed:
        overlap = expected & changed
        if not overlap:
            reasons.append(
                "Implementation did not modify any files from "
                "the bead's file scope. Changed: "
                + ", ".join(sorted(changed)[:5])
                + f". Expected: {', '.join(sorted(expected)[:5])}"
            )
    elif expected and not changed:
        reasons.append(
            "Implementation produced no file changes but "
            "the bead's file scope lists files to create/modify"
        )

    # Check 4: Run verification commands
    if verification_text and ctx.cwd:
        from maverick.runners.command import CommandRunner

        runner = CommandRunner(cwd=ctx.cwd)
        for cmd_str in _parse_verification_commands(verification_text):
            # Only run safe read-only commands
            first_word = cmd_str.split()[0] if cmd_str.split() else ""
            if first_word not in ("rg", "grep", "cargo", "make"):
                continue
            try:
                # Run through shell to support pipes, redirects
                result = await runner.run(["sh", "-c", cmd_str])
                if result.returncode != 0:
                    reasons.append(
                        f"Verification command failed: `{cmd_str}`"
                    )
            except Exception as exc:
                reasons.append(
                    f"Verification command error: `{cmd_str}`: {exc}"
                )

    passed = len(reasons) == 0
    if passed:
        await wf.emit_step_completed(ACCEPTANCE_CHECK)
    else:
        await wf.emit_step_failed(
            ACCEPTANCE_CHECK,
            "; ".join(reasons),
        )

    return passed, reasons


async def run_spec_compliance_check(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    verification_properties: str,
) -> tuple[bool, list[str]]:
    """Run deterministic spec compliance using verification properties.

    Writes the verification property tests to a temp file in the
    workspace, runs them, and checks that all pass. The properties
    were derived at plan time from acceptance criteria and are
    immutable — they define "correct."

    Returns ``(passed, reasons)`` where *reasons* lists assertion
    failures.
    """
    from maverick.workflows.fly_beads.constants import SPEC_COMPLIANCE

    await wf.emit_step_started(SPEC_COMPLIANCE)
    reasons: list[str] = []

    if not verification_properties or not ctx.cwd:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
        return True, []

    # Extract expected assertions from verification properties.
    # Supports two formats:
    #   Simple: "verify_NAME: assert_eq!(expr, "expected")"
    #   Rust:   "fn verify_NAME() { assert_eq!(...); }"
    import re as _re

    expected_tests: dict[str, str] = {}
    lines = verification_properties.split("\n")

    for line in lines:
        stripped = line.strip()
        # Simple format: verify_NAME: assert_eq!(...)
        if stripped.startswith("verify_") and ":" in stripped:
            parts = stripped.split(":", 1)
            test_name = parts[0].strip()
            assertion = parts[1].strip()
            expected_tests[test_name] = assertion

    # Rust format: fn verify_NAME() { ... }
    if not expected_tests:
        current_fn: str | None = None
        current_body: list[str] = []
        for line in lines:
            stripped = line.strip()
            fn_match = _re.match(r"fn\s+(verify_\w+)\s*\(", stripped)
            if fn_match:
                current_fn = fn_match.group(1)
                current_body = []
            elif current_fn and "assert" in stripped:
                current_body.append(stripped)
            elif current_fn and stripped == "}":
                if current_body:
                    expected_tests[current_fn] = " ".join(
                        current_body
                    )
                current_fn = None
                current_body = []

    if not expected_tests:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
        return True, []

    try:
        from maverick.runners.command import CommandRunner

        runner = CommandRunner(cwd=ctx.cwd)

        # Step 1: Run tests matching verify_ prefix
        result = await runner.run(
            ["sh", "-c", "cargo test verify_ 2>&1 || true"]
        )

        output = (result.stdout or "") + (result.stderr or "")

        # Step 2: Check each expected test exists and passes
        for test_name, expected_assertion in expected_tests.items():
            if f"{test_name} ..." not in output:
                reasons.append(
                    f"Required test '{test_name}' not found. "
                    f"You MUST add this test to src/main.rs: "
                    f"{expected_assertion[:200]}"
                )
            elif f"{test_name} ... FAILED" in output:
                reasons.append(
                    f"Test {test_name} FAILED. It MUST assert: "
                    + expected_assertion[:200]
                )

        # Step 3: Verify assertion VALUES match the spec.
        # Grep the source for each verify_ test and check the
        # expected string matches what the flight plan specifies.
        if not reasons:
            for test_name, expected_assertion in (
                expected_tests.items()
            ):
                # Extract expected string from assertion
                # e.g.: assert_eq!(greet("Alice", ...), "Good day")
                # We look for the quoted expected value
                import re

                expected_strings = re.findall(
                    r'"([^"]*)"', expected_assertion
                )
                if len(expected_strings) < 2:
                    continue  # Can't extract expected value

                # The last quoted string is the expected output
                expected_value = expected_strings[-1]

                # Find the test in source and check assertion
                test_source = await runner.run(
                    [
                        "sh",
                        "-c",
                        f"grep -A5 'fn {test_name}' src/ -r"
                        " 2>/dev/null || true",
                    ]
                )
                test_code = test_source.stdout or ""

                if expected_value not in test_code:
                    reasons.append(
                        f"Test {test_name} does not assert the"
                        f" exact expected value from the spec."
                        f" Expected: \"{expected_value}\"."
                        f" The test MUST use the exact string"
                        f" from the Verification Properties."
                    )

        # If no expected tests defined, just check overall pass
        if not expected_tests and "test result: FAILED" in output:
            reasons.append(
                "Verification property tests failed"
            )

    except Exception as exc:
        reasons.append(f"Spec compliance check error: {exc}")

    passed = len(reasons) == 0
    if passed:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
    else:
        await wf.emit_step_failed(
            SPEC_COMPLIANCE, "; ".join(reasons)
        )

    return passed, reasons


def load_work_unit_files(
    flight_plan_name: str | None,
) -> dict[str, str]:
    """Load all work unit markdown files from the plan directory.

    Returns a dict mapping work-unit ID (from YAML frontmatter) to
    the full markdown body (after frontmatter). Used to enrich bead
    descriptions with structured sections (File Scope, Acceptance
    Criteria, etc.) that the bead database truncates.
    """
    result: dict[str, str] = {}
    if not flight_plan_name:
        return result
    plan_dir = Path.cwd() / ".maverick" / "plans" / flight_plan_name
    if not plan_dir.is_dir():
        return result

    skip = {"flight-plan.md", "briefing.md", "refuel-briefing.md"}
    for md_file in sorted(plan_dir.glob("*.md")):
        if md_file.name in skip:
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            # Extract work-unit ID from YAML frontmatter
            wu_id = ""
            for line in content.split("\n"):
                if line.startswith("work-unit:"):
                    wu_id = line.split(":", 1)[1].strip()
                    break
            if wu_id:
                # Strip frontmatter, keep body
                parts = content.split("---", 2)
                body = parts[2].strip() if len(parts) >= 3 else content
                result[wu_id] = body
        except Exception:
            continue

    return result


def match_bead_to_work_unit(
    bead_title: str,
    work_units: dict[str, str],
) -> str | None:
    """Match a bead title to a work unit markdown body.

    The bead title from the database often starts with the work unit's
    task description. We match by checking if the work-unit ID
    (kebab-case) appears in the bead title (with hyphens or spaces).
    """
    title_lower = bead_title.lower()
    for wu_id, body in work_units.items():
        # Try exact ID match in title
        if wu_id in title_lower:
            return body
        # Try with hyphens → spaces
        if wu_id.replace("-", " ") in title_lower:
            return body
        # Try matching first few words of the task section
        sections = _parse_work_unit_sections(body)
        task = sections.get("task", "")
        if task:
            # Match first 40 chars of task in title
            task_prefix = task[:40].lower().strip()
            if task_prefix and task_prefix in title_lower:
                return body
    return None


def load_briefing_context(flight_plan_name: str | None) -> str | None:
    """Read briefing markdown from plan directory.

    Returns:
        Briefing text or None if not found.
    """
    if not flight_plan_name:
        return None
    plan_dir = Path.cwd() / ".maverick" / "plans" / flight_plan_name
    for candidate in ("refuel-briefing.md", "briefing.md"):
        briefing_path = plan_dir / candidate
        if briefing_path.is_file():
            with contextlib.suppress(Exception):
                return briefing_path.read_text(encoding="utf-8")
    return None


async def fetch_runway_context(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Fetch runway context for the current bead (best-effort).

    Queries the runway store for historical outcomes and semantically
    relevant passages. Sets ctx.runway_context if data is found.
    Never raises — logs a warning on failure.
    """
    try:
        runway_cfg = getattr(wf._config, "runway", None)
        if runway_cfg is None or not getattr(runway_cfg, "enabled", True):
            return

        retrieval_cfg = getattr(runway_cfg, "retrieval", None)
        max_passages = (
            getattr(retrieval_cfg, "max_passages", 10) if retrieval_cfg else 10
        )
        bm25_top_k = getattr(retrieval_cfg, "bm25_top_k", 20) if retrieval_cfg else 20
        max_context_chars = (
            getattr(retrieval_cfg, "max_context_chars", 4000) if retrieval_cfg else 4000
        )

        result = await retrieve_runway_context(
            title=ctx.title,
            description=ctx.description,
            epic_id=ctx.epic_id,
            max_passages=max_passages,
            bm25_top_k=bm25_top_k,
            max_context_chars=max_context_chars,
            cwd=ctx.cwd,
        )
        if result.context_text:
            ctx.runway_context = result.context_text
            logger.info(
                "runway_context_fetched",
                bead_id=ctx.bead_id,
                outcomes=result.outcomes_used,
                passages=result.passages_used,
            )
    except Exception as exc:
        logger.warning(
            "fetch_runway_context_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def walk_discovered_from_chain(bead_id: str) -> list[str]:
    """Walk the discovered-from dependency chain back to the root.

    Returns a list of bead IDs from root to the bead that links to
    ``bead_id``.  An empty list means the bead has no discovered-from
    ancestry (it is an original bead, not a follow-up).

    Capped at 10 hops to prevent infinite loops on circular deps.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    chain: list[str] = []
    current = bead_id
    seen: set[str] = set()

    for _ in range(10):
        try:
            result = await runner.run(
                ["bd", "dep", "list", current, "--json"],
            )
        except Exception:
            break

        if not result.stdout:
            break

        origin_id = ""
        with contextlib.suppress(Exception):
            deps = _json.loads(result.stdout)
            if isinstance(deps, list):
                for dep in deps:
                    if (
                        isinstance(dep, dict)
                        and dep.get("dependency_type") == "discovered-from"
                    ):
                        origin_id = dep.get("id", "")
                        break

        if not origin_id or origin_id in seen:
            break

        chain.append(origin_id)
        seen.add(origin_id)
        current = origin_id

    chain.reverse()  # root first
    return chain


async def resolve_provenance(ctx: BeadContext) -> None:
    """Enrich bead context with provenance from discovered-from links.

    Populates ``ctx.discovered_from_chain`` and appends a provenance
    section to ``ctx.description`` so the implementer agent can understand
    what was tried before and what the reviewer objected to.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    chain = await walk_discovered_from_chain(ctx.bead_id)
    ctx.discovered_from_chain = chain
    ctx.escalation_depth = len(chain)

    if not chain:
        return

    # Fetch the immediate parent bead's details for the description
    origin_id = chain[-1]  # most recent ancestor
    runner = CommandRunner(cwd=Path.cwd())

    try:
        origin_result = await runner.run(
            ["bd", "show", origin_id, "--json"],
        )
    except Exception:
        return

    if not origin_result.stdout:
        return

    with contextlib.suppress(Exception):
        origin = _json.loads(origin_result.stdout)
        origin_title = origin.get("title", "")
        origin_desc = origin.get("description", "")

        provenance_section = (
            f"\n\n## Provenance\n\n"
            f"This bead was created to address unresolved review"
            f" findings from bead `{origin_id}`"
            f" ({origin_title}).\n"
        )
        if len(chain) > 1:
            provenance_section += (
                f"\nFull chain: {' → '.join(f'`{b}`' for b in chain)}"
                f" → `{ctx.bead_id}` (current)\n"
            )
        if origin_desc:
            desc_preview = origin_desc[:500]
            if len(origin_desc) > 500:
                desc_preview += "..."
            provenance_section += (
                f"\n### Original Bead Description\n\n"
                f"{desc_preview}\n"
            )

        ctx.description = ctx.description + provenance_section


async def snapshot_and_describe(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Snapshot jj operation and set WIP description."""
    snapshot_result = await jj_snapshot_operation(cwd=ctx.cwd)
    ctx.operation_id = snapshot_result.get("operation_id")
    await jj_describe(
        message=f"WIP bead({ctx.bead_id}): {ctx.title}",
        cwd=ctx.cwd,
    )


def _is_verification_only(ctx: BeadContext) -> bool:
    """Detect verification-only beads that should not modify files.

    Checks the bead title and description for keywords that indicate a
    read-only verification task.
    """
    text = f"{ctx.title} {ctx.description}".lower()
    verification_signals = (
        "verification-only",
        "verification only",
        "no code changes expected",
        "no code changes needed",
        "no implementation work",
        "confirm only",
    )
    return any(signal in text for signal in verification_signals)


def _is_research_only(ctx: BeadContext) -> bool:
    """Detect research-only beads that extract patterns to context files.

    Research beads can read the codebase and write findings to
    ``.maverick/context/{bead-id}.md`` for dependent beads to consume.
    """
    text = f"{ctx.title} {ctx.description}".lower()
    return "research-only" in text


async def run_implement_and_validate(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Execute the implement-and-validate agent step.

    The agent implements the bead AND runs validation internally, iterating
    until validation passes or it determines the issue is unfixable.

    Verification-only beads (detected by keywords in the description) are
    constrained to read-only tools to prevent accidental modifications.

    On failure: emits step_failed (not step_completed), logs warning.
    Does NOT propagate — bead continues to gate check.
    """
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(IMPLEMENT_AND_VALIDATE, step_type=StepType.AGENT)

    if wf._step_executor is not None:
        # Parse work-unit markdown into structured sections so the
        # implementer sees explicit acceptance criteria, file scope,
        # and verification commands rather than one raw blob.
        parsed = _parse_work_unit_sections(ctx.description)
        implement_prompt: dict[str, Any] = {
            "task_description": parsed.get("task", ctx.description),
            "cwd": cwd_str,
        }
        if parsed.get("acceptance criteria"):
            implement_prompt["acceptance_criteria"] = (
                "You MUST satisfy ALL of these acceptance criteria:\n\n"
                + parsed["acceptance criteria"]
            )
        if parsed.get("file scope"):
            implement_prompt["file_scope"] = (
                "File scope for this bead (Create/Modify/Protect):\n\n"
                + parsed["file scope"]
            )
        procedure_text = parsed.get("procedure") or parsed.get(
            "instructions"
        )
        if procedure_text:
            implement_prompt["procedure"] = (
                "Follow this procedure STEP BY STEP. Complete each"
                " step before moving to the next. MUST steps are"
                " mandatory — do not skip them. Use the Read tool to"
                " examine files at the specified line ranges before"
                " making changes. Verify after each step.\n\n"
                + procedure_text
            )
        if parsed.get("verification"):
            implement_prompt["verification_commands"] = (
                "After implementation, run these commands to verify "
                "your work:\n\n" + parsed["verification"]
            )
        if parsed.get("test specification"):
            implement_prompt["test_to_pass"] = (
                "PRIORITY: Make this test pass FIRST, then implement "
                "remaining acceptance criteria. This test defines the "
                "minimum viable implementation target:\n\n"
                + parsed["test specification"]
            )
        if ctx.runway_context:
            implement_prompt["runway_context"] = ctx.runway_context
        if ctx.briefing_context:
            implement_prompt["briefing_context"] = ctx.briefing_context
        if ctx.prior_failures:
            implement_prompt["previous_failures"] = (
                "This bead failed in previous attempt(s). "
                "Address these issues:\n"
                + "\n".join(
                    f"- Attempt {i + 1}: {reason}"
                    for i, reason in enumerate(ctx.prior_failures)
                )
            )
            # Inject detailed review findings so implementer knows WHAT to fix
            if ctx.review_result:
                review_report = ctx.review_result.get("review_report", "")
                if review_report:
                    implement_prompt["review_findings_to_address"] = (
                        "The reviewer identified these specific issues that "
                        "MUST be addressed in this attempt:\n\n" + review_report
                    )

        # Inject prior attempt context so the implementer can iterate
        # on what it produced last time rather than starting from scratch.
        if ctx.prior_attempt_context:
            implement_prompt["prior_attempt"] = (
                "Your PREVIOUS attempt produced the code below. "
                "Do NOT start from scratch — iterate on this code "
                "and fix the specific issues identified above.\n\n"
                + ctx.prior_attempt_context
            )

        # Constrain verification-only beads to read-only tools
        verification_mode = _is_verification_only(ctx)
        research_mode = _is_research_only(ctx)
        extra_kwargs: dict[str, Any] = {}
        if verification_mode:
            extra_kwargs["allowed_tools"] = ["Read", "Glob", "Grep"]
            implement_prompt["task_description"] = (
                "IMPORTANT: This is a VERIFICATION-ONLY bead. "
                "Do NOT modify any files. Only read, search, and report "
                "your findings.\n\n" + implement_prompt["task_description"]
            )
        elif research_mode:
            # Research beads can read and write to .maverick/context/
            extra_kwargs["allowed_tools"] = ["Read", "Glob", "Grep", "Write"]
            if ctx.cwd:
                context_dir = ctx.cwd / ".maverick" / "context"
                context_dir.mkdir(parents=True, exist_ok=True)
            implement_prompt["task_description"] = (
                "IMPORTANT: This is a RESEARCH-ONLY bead. "
                "Read the codebase to extract patterns and write your "
                f"findings to `.maverick/context/{ctx.bead_id}.md`. "
                "Do NOT modify any source code files.\n\n"
                + implement_prompt["task_description"]
            )

        try:
            # Resolve step config from maverick.yaml's steps.implement section
            # (provider, model_id, timeout, etc.) via the 5-layer precedence chain.
            resolved = wf.resolve_step_config(
                step_name="implement",
                step_type=StepType.PYTHON,
                agent_name="implementer",
            )
            effective_timeout = resolved.timeout or IMPLEMENT_AND_VALIDATE_TIMEOUT
            resolved = resolved.model_copy(update={"timeout": effective_timeout})

            # Build agent kwargs so ImplementerAgent receives validation
            # commands and project type in its system prompt.
            vc = wf._config.validation
            impl_agent_kwargs: dict[str, Any] = {
                "validation_commands": {
                    "sync_cmd": vc.sync_cmd,
                    "format_cmd": vc.format_cmd,
                    "lint_cmd": vc.lint_cmd,
                    "typecheck_cmd": vc.typecheck_cmd,
                    "test_cmd": vc.test_cmd,
                },
                "project_type": wf._config.project_type,
            }

            await wf._step_executor.execute(
                step_name=IMPLEMENT_AND_VALIDATE,
                agent_name="implementer",
                prompt=implement_prompt,
                cwd=ctx.cwd,
                config=resolved,
                agent_kwargs=impl_agent_kwargs,
                **extra_kwargs,
            )
        except Exception as exc:
            logger.warning(
                "implement_and_validate_step_failed",
                bead_id=ctx.bead_id,
                error=str(exc),
            )
            await wf.emit_step_failed(IMPLEMENT_AND_VALIDATE, str(exc))
            await wf.emit_output(
                IMPLEMENT_AND_VALIDATE,
                f"Implement-and-validate step failed: {exc}",
                level="warning",
            )
            return
    else:
        await wf.emit_output(
            IMPLEMENT_AND_VALIDATE,
            "No step executor configured — skipping agent implement step",
            level="warning",
        )

    await wf.emit_step_completed(IMPLEMENT_AND_VALIDATE)


async def run_gate_check(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run independent validation gate check.

    The orchestrator runs validation as subprocess — trust-but-verify.
    Stores result in ctx.gate_result and ctx.validation_result.
    Never raises — gate pass/fail handled by workflow loop.
    """
    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(GATE_CHECK)

    try:
        validation_commands = _build_validation_commands(wf._config.validation)
        gate_result = await run_independent_gate(
            stages=list(DEFAULT_VALIDATION_STAGES),
            cwd=cwd_str,
            validation_commands=validation_commands or None,
            timeout_seconds=float(wf._config.validation.timeout_seconds),
        )
        ctx.gate_result = gate_result
        # Also update validation_result for runway recording compatibility
        ctx.validation_result = gate_result
    except Exception as exc:
        logger.warning(
            "gate_check_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
        ctx.gate_result = {
            "passed": False,
            "stage_results": {},
            "summary": f"Gate check error: {exc}",
        }
        ctx.validation_result = ctx.gate_result
        await wf.emit_step_failed(GATE_CHECK, str(exc))
        return

    await wf.emit_step_completed(GATE_CHECK, gate_result)


async def run_gate_remediation(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Run gate remediation agent to fix gate failures.

    Only called when gate_check failed. Invokes FixerAgent (registered as
    "gate_remediator") with gate failure output. Sets ctx.remediation_attempted = True.

    Non-fatal on executor failure.
    """
    await wf.emit_step_started(GATE_REMEDIATION, step_type=StepType.AGENT)
    ctx.remediation_attempted = True

    if wf._step_executor is None:
        await wf.emit_output(
            GATE_REMEDIATION,
            "No step executor configured — skipping gate remediation",
            level="warning",
        )
        await wf.emit_step_completed(GATE_REMEDIATION)
        return

    # Build prompt from gate failure details
    gate_summary = ""
    if ctx.gate_result:
        gate_summary = ctx.gate_result.get("summary", "")
        stage_results = ctx.gate_result.get("stage_results", {})
        failure_details = []
        for stage_name, sr in stage_results.items():
            if stage_name.startswith("_"):
                continue
            if not sr.get("passed", True):
                output = sr.get("output", "")
                errors = sr.get("errors", [])
                if errors:
                    error_msgs = [
                        e.get("message", str(e)) if isinstance(e, dict) else str(e)
                        for e in errors
                    ]
                    failure_details.append(f"- {stage_name}: {'; '.join(error_msgs)}")
                elif output:
                    failure_details.append(f"- {stage_name}: {output[:500]}")
                else:
                    failure_details.append(f"- {stage_name}: failed (no details)")

        if failure_details:
            gate_summary += "\n\nFailure details:\n" + "\n".join(failure_details)

    remediation_prompt: dict[str, Any] = {
        "prompt": (
            "The orchestrator independently ran validation and found these failures. "
            "Fix the issues and re-run validation to verify your fixes.\n\n"
            f"{gate_summary}"
        ),
        "cwd": str(ctx.cwd) if ctx.cwd else None,
    }

    try:
        resolved = wf.resolve_step_config(
            step_name="gate_remediation",
            step_type=StepType.PYTHON,
            agent_name="gate_remediator",
        )
        effective_timeout = resolved.timeout or GATE_REMEDIATION_TIMEOUT
        resolved = resolved.model_copy(update={"timeout": effective_timeout})

        await wf._step_executor.execute(
            step_name=GATE_REMEDIATION,
            agent_name="gate_remediator",
            prompt=remediation_prompt,
            cwd=ctx.cwd,
            config=resolved,
        )
    except Exception as exc:
        logger.warning(
            "gate_remediation_step_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
        await wf.emit_step_failed(GATE_REMEDIATION, str(exc))
        await wf.emit_output(
            GATE_REMEDIATION,
            f"Gate remediation failed: {exc}",
            level="warning",
        )
        return

    await wf.emit_step_completed(GATE_REMEDIATION)


async def run_review_and_remediate(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    *,
    skip_review: bool,
) -> None:
    """Run review and fix findings in a single pass.

    If skip_review: return immediately.
    Runs dual review (CompletenessReviewer + CorrectnessReviewer in parallel).
    If critical/major findings: invokes ReviewFixerAgent (with Bash access).
    Creates beads from remaining unresolved findings.
    Records runway review data. Single pass — no retry loop.
    """
    if skip_review:
        return

    cwd_str = str(ctx.cwd) if ctx.cwd else None
    await wf.emit_step_started(REVIEW, step_type=StepType.AGENT)

    # Scope the review to files this bead actually changed (not the
    # full workspace diff which includes prior beads' commits).
    # At review time the bead is not yet committed, so we use the
    # uncommitted diff (jj working copy changes).
    bead_files = await _get_uncommitted_files(ctx.cwd)

    try:
        review_context_result = await gather_local_review_context(
            base_branch=DEFAULT_BASE_BRANCH,
            include_spec_files=True,
            include_files=tuple(bead_files) if bead_files else None,
            cwd=cwd_str,
        )
        review_input_dict = review_context_result.to_dict()
        # Inject bead description so completeness reviewer can compare
        # the diff against acceptance criteria and SC trace references.
        review_input_dict["bead_description"] = ctx.description
        # Thread run_dir and bead_id for per-bead review output
        if ctx.run_dir:
            review_input_dict["run_dir"] = str(ctx.run_dir)
            review_input_dict["bead_id"] = ctx.bead_id
        # Inject bead file scope so reviewers can distinguish in-scope
        # vs out-of-scope findings (files this bead is responsible for)
        if bead_files:
            review_input_dict["bead_file_scope"] = list(bead_files)
        # Resolve review step configs so provider/model from maverick.yaml
        # is honoured (e.g. completeness_review → copilot, correctness → claude)
        _review_configs: dict[str, Any] = {}
        if wf._step_executor is not None:
            for _rname in ("completeness_review", "correctness_review"):
                _review_configs[_rname] = wf.resolve_step_config(
                    step_name=_rname,
                    step_type=StepType.PYTHON,
                    agent_name=_rname.replace("_review", "_reviewer"),
                )

        review_loop_result = await run_review_fix_loop(
            review_input=review_input_dict,
            base_branch=DEFAULT_BASE_BRANCH,
            max_attempts=1,  # Single pass — no retry loop
            generate_report=True,
            cwd=cwd_str,
            briefing_context=ctx.briefing_context,
            executor=wf._step_executor,
            review_step_configs=_review_configs or None,
        )
        ctx.review_result = review_loop_result.to_dict()
        await record_runway_review(wf, ctx)
    except Exception as exc:
        logger.warning(
            "review_step_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
        await wf.emit_output(
            REVIEW,
            f"Review step failed: {exc}",
            level="warning",
        )
        ctx.review_result = None

    await wf.emit_step_completed(REVIEW, ctx.review_result)

    # Create beads from unresolved findings
    if ctx.review_result is not None:
        try:
            await create_beads_from_findings(
                epic_id=ctx.epic_id,
                review_result=ctx.review_result,
            )
        except Exception as exc:
            logger.warning(
                "create_review_beads_failed",
                bead_id=ctx.bead_id,
                error=str(exc),
            )


async def commit_bead(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Commit the bead and mark it complete."""
    await wf.emit_step_started(COMMIT)
    commit_result = await jj_commit_bead(
        message=f"bead({ctx.bead_id}): {ctx.title}",
        cwd=ctx.cwd,
    )
    await wf.emit_step_completed(COMMIT, commit_result)

    # Capture files changed by this bead (jj colocated → git diff works)
    files_changed = await _get_files_changed(ctx.cwd)

    await mark_bead_complete(bead_id=ctx.bead_id)
    await record_runway_outcome(wf, ctx, files_changed=files_changed)
    await wf.emit_output(
        COMMIT,
        f"Bead {ctx.bead_id} completed: {ctx.title}",
        level="success",
    )


async def _get_uncommitted_files(cwd: Path | None) -> list[str]:
    """Get files changed in the working copy (uncommitted changes).

    In jj colocated mode, ``git diff --name-only HEAD`` shows the
    working copy changes that haven't been committed yet — i.e., what
    the current bead's agent wrote.
    """
    from maverick.runners.command import CommandRunner

    try:
        runner = CommandRunner(cwd=cwd or Path.cwd())
        result = await runner.run(
            ["git", "diff", "--name-only", "HEAD"],
        )
        if result.stdout:
            return [
                f.strip() for f in result.stdout.strip().splitlines() if f.strip()
            ]
    except Exception as exc:
        logger.debug("uncommitted_files_capture_failed", error=str(exc))
    return []


async def snapshot_prior_attempt(
    run_dir: Path,
    ctx: BeadContext,
    attempt: int,
) -> Path | None:
    """Snapshot changed files before rollback so the next attempt can see them.

    Writes to ``.maverick/runs/{run_id}/beads/{bead_id}/attempt-{n}/``
    alongside a summary markdown with the review findings.

    Returns the snapshot directory path, or None on failure.
    """
    import shutil

    snapshot_dir = (
        run_dir / "beads" / ctx.bead_id / f"attempt-{attempt}"
    )
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Copy changed files into snapshot
        changed = await _get_uncommitted_files(ctx.cwd)
        if changed and ctx.cwd:
            for relpath in changed:
                src = ctx.cwd / relpath
                if src.exists() and src.is_file():
                    dest = snapshot_dir / relpath
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dest))

        # Write summary with review findings
        summary_lines = [
            f"# Attempt {attempt} — {ctx.bead_id}",
            "",
            f"**Files changed:** {', '.join(changed) if changed else 'none'}",
            "",
        ]
        if ctx.review_result:
            report = ctx.review_result.get("review_report", "")
            if report:
                summary_lines.append("## Review Findings")
                summary_lines.append("")
                summary_lines.append(report)
        if ctx.gate_result and not ctx.gate_result.get("passed"):
            summary_lines.append("## Gate Failures")
            summary_lines.append("")
            summary_lines.append(
                ctx.gate_result.get("summary", "unknown")
            )

        (snapshot_dir / "summary.md").write_text(
            "\n".join(summary_lines), encoding="utf-8"
        )

        logger.info(
            "prior_attempt_snapshot",
            bead_id=ctx.bead_id,
            attempt=attempt,
            files=len(changed),
            path=str(snapshot_dir),
        )
        return snapshot_dir

    except Exception as exc:
        logger.warning(
            "prior_attempt_snapshot_failed",
            bead_id=ctx.bead_id,
            attempt=attempt,
            error=str(exc),
        )
        return None


def load_prior_attempt_context(
    run_dir: Path,
    bead_id: str,
    attempt: int,
) -> str | None:
    """Load the prior attempt's code and review findings as context.

    Returns a formatted string with the prior attempt's changed files
    and review summary, or None if no snapshot exists.
    """
    snapshot_dir = (
        run_dir / "beads" / bead_id / f"attempt-{attempt}"
    )
    if not snapshot_dir.exists():
        return None

    parts: list[str] = []

    # Load summary
    summary_path = snapshot_dir / "summary.md"
    if summary_path.exists():
        parts.append(summary_path.read_text(encoding="utf-8"))

    # Load changed source files (skip summary.md)
    source_files = sorted(
        f
        for f in snapshot_dir.rglob("*")
        if f.is_file() and f.name != "summary.md"
    )
    if source_files:
        parts.append("\n## Prior Attempt Code\n")
        for src_file in source_files[:10]:  # Cap at 10 files
            relpath = src_file.relative_to(snapshot_dir)
            content = src_file.read_text(encoding="utf-8", errors="replace")
            # Truncate large files
            if len(content) > 4000:
                content = content[:4000] + "\n... (truncated)"
            parts.append(f"### {relpath}\n```\n{content}\n```\n")

    return "\n".join(parts) if parts else None


async def _get_files_changed(cwd: Path | None) -> list[str]:
    """Get the list of files changed by the most recent commit.

    Uses ``git diff --name-only HEAD~1`` which works in jj colocated
    mode (shared ``.git`` directory).
    """
    from maverick.runners.command import CommandRunner

    try:
        runner = CommandRunner(cwd=cwd or Path.cwd())
        result = await runner.run(
            ["git", "diff", "--name-only", "HEAD~1"],
        )
        if result.stdout:
            return [
                f.strip() for f in result.stdout.strip().splitlines() if f.strip()
            ]
    except Exception as exc:
        logger.debug("files_changed_capture_failed", error=str(exc))
    return []


async def record_runway_outcome(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    files_changed: list[str] | None = None,
) -> None:
    """Record bead outcome to runway store (best-effort)."""
    try:
        await record_bead_outcome(
            bead_id=ctx.bead_id,
            epic_id=ctx.epic_id,
            title=ctx.title,
            flight_plan=ctx.flight_plan_name,
            validation_result=ctx.validation_result,
            review_result=ctx.review_result,
            files_changed=files_changed,
            cwd=ctx.cwd,
        )
    except Exception as exc:
        logger.warning(
            "runway_outcome_recording_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def record_runway_review(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Record review findings to runway store (best-effort)."""
    if ctx.review_result is None:
        return
    try:
        await record_review_findings(
            bead_id=ctx.bead_id,
            review_result=ctx.review_result,
            cwd=ctx.cwd,
        )
    except Exception as exc:
        logger.warning(
            "runway_review_recording_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def rollback_bead(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Rollback jj state and emit error output."""
    if ctx.operation_id:
        await jj_restore_operation(
            operation_id=ctx.operation_id,
            cwd=ctx.cwd,
        )
    reasons = "; ".join(ctx.verify_result.reasons) if ctx.verify_result else "unknown"
    await wf.emit_output(
        COMMIT,
        f"Bead {ctx.bead_id} failed verification: {reasons}",
        level="error",
    )


async def commit_bead_with_followup(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    prior_failures: list[str],
) -> None:
    """Commit a bead that passed validation but exhausted review retries.

    Two-tier escalation:
    - **Tier 1** (no discovered-from chain): Create a follow-up task bead
      under the same epic with the review findings.
    - **Tier 2** (has discovered-from chain — this IS a follow-up): The
      same issue has persisted across multiple beads. Escalate by running
      the decomposer to re-plan the stuck work, superseding the stuck chain.

    Args:
        wf: Workflow instance for emitting events.
        ctx: Bead context with review results and discovered_from_chain.
        prior_failures: List of failure reason strings from prior attempts.
    """
    # Commit the implementation work (it passed validation)
    await commit_bead(wf, ctx)

    # Circuit breaker: stop escalating when chain is too deep
    if ctx.escalation_depth >= MAX_ESCALATION_DEPTH:
        ctx.human_review_tag = "needs-human-review"
        await wf.emit_output(
            COMMIT,
            f"Bead {ctx.bead_id} committed with needs-human-review tag: "
            f"escalation depth {ctx.escalation_depth} exceeds max "
            f"{MAX_ESCALATION_DEPTH}. No further follow-up beads will be "
            f"created for this chain.",
            level="warning",
        )
        return

    if ctx.discovered_from_chain:
        # Tier 2: This is already a follow-up — escalate to re-planning
        await _escalate_to_replan(wf, ctx, prior_failures)
    else:
        # Tier 1: First-time failure — create a follow-up task bead
        await _create_followup_bead(wf, ctx, prior_failures)


async def _create_followup_bead(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    prior_failures: list[str],
) -> None:
    """Tier 1: Create a follow-up task bead for unresolved review findings."""
    import json as _json

    from maverick.runners.command import CommandRunner

    followup_description = _build_followup_description(ctx, prior_failures)

    try:
        runner = CommandRunner(cwd=Path.cwd())
        title = f"Address review findings from {ctx.bead_id}: {ctx.title[:80]}"
        result = await runner.run(
            [
                "bd", "create", title,
                "--parent", ctx.epic_id,
                "--type", "task",
                "--description", followup_description,
                "--json",
            ]
        )

        followup_id = ""
        if result.stdout:
            with contextlib.suppress(Exception):
                data = _json.loads(result.stdout)
                followup_id = data.get("id", "")

        if followup_id:
            await runner.run(
                [
                    "bd", "dep", "add", followup_id, ctx.bead_id,
                    "--type", "discovered-from",
                ]
            )

        label = f" ({followup_id})" if followup_id else ""
        await wf.emit_output(
            COMMIT,
            f"Created follow-up bead{label} for unresolved review"
            f" issues from {ctx.bead_id}",
            level="warning",
        )
    except Exception as exc:
        logger.warning(
            "followup_bead_creation_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def _escalate_to_replan(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    prior_failures: list[str],
) -> None:
    """Tier 2: Re-plan the stuck work via the decomposer agent.

    The same reviewer issue has persisted across multiple beads in the
    discovered-from chain.  Instead of creating another follow-up task,
    re-run the decomposer with failure context so the work can be
    re-decomposed into different boundaries.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    chain = ctx.discovered_from_chain  # [root, ..., parent]
    full_chain = chain + [ctx.bead_id]

    # --- Gather failure context ---
    chain_titles: dict[str, str] = {}
    for bid in full_chain:
        with contextlib.suppress(Exception):
            r = await runner.run(["bd", "show", bid, "--json"])
            if r.stdout:
                data = _json.loads(r.stdout)
                chain_titles[bid] = data.get("title", bid)

    review_report = ""
    if ctx.review_result:
        review_report = ctx.review_result.get("review_report", "")

    # --- Build enriched prompt for the decomposer ---
    replan_description = _build_escalation_description(
        full_chain, chain_titles, review_report, prior_failures
    )

    # --- Supersede the stuck chain (close old beads cleanly) ---
    for bid in full_chain:
        with contextlib.suppress(Exception):
            await runner.run(["bd", "close", bid, "--reason",
                              f"Superseded by re-planning from {ctx.bead_id}"])

    # --- Create re-planning bead ---
    try:
        title = (
            f"Re-plan: reviewer issue persisted across"
            f" {len(full_chain)} beads ({full_chain[0]}..{ctx.bead_id})"
        )
        result = await runner.run(
            [
                "bd", "create", title,
                "--parent", ctx.epic_id,
                "--type", "task",
                "--label", "needs-replan",
                "--description", replan_description,
                "--json",
            ]
        )

        replan_id = ""
        if result.stdout:
            with contextlib.suppress(Exception):
                data = _json.loads(result.stdout)
                replan_id = data.get("id", "")

        # Wire discovered-from to ALL beads in the chain
        if replan_id:
            for bid in full_chain:
                with contextlib.suppress(Exception):
                    await runner.run(
                        ["bd", "dep", "add", replan_id, bid,
                         "--type", "discovered-from"]
                    )

        label = f" ({replan_id})" if replan_id else ""
        await wf.emit_output(
            COMMIT,
            f"Escalated to re-planning bead{label}:"
            f" reviewer issue persisted across {len(full_chain)} beads"
            f" in chain {' → '.join(full_chain)}",
            level="warning",
        )
    except Exception as exc:
        logger.warning(
            "replan_bead_creation_failed",
            bead_id=ctx.bead_id,
            chain=full_chain,
            error=str(exc),
        )

    # --- Defer beads that depend on the stuck chain ---
    await _defer_dependent_beads(full_chain, ctx.epic_id)


async def _defer_dependent_beads(
    chain: list[str],
    epic_id: str,
) -> None:
    """Defer beads that are blocked by any bead in the stuck chain."""
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    deferred: set[str] = set()

    for bid in chain:
        with contextlib.suppress(Exception):
            r = await runner.run(["bd", "dep", "list", bid, "--json"])
            if not r.stdout:
                continue
            deps = _json.loads(r.stdout)
            if not isinstance(deps, list):
                continue
            for dep in deps:
                if not isinstance(dep, dict):
                    continue
                # Find beads that this bead blocks
                if dep.get("type") == "blocks":
                    blocked_id = dep.get("issue_id", "")
                    if blocked_id and blocked_id not in deferred:
                        with contextlib.suppress(Exception):
                            await defer_bead(
                                bead_id=blocked_id,
                                reason=f"Blocked by stuck chain: {' → '.join(chain)}",
                            )
                            deferred.add(blocked_id)


def _build_followup_description(
    ctx: BeadContext,
    prior_failures: list[str],
) -> str:
    """Build a description for the Tier 1 follow-up bead from review results."""
    parts = [
        f"Address unresolved review findings from bead `{ctx.bead_id}`.",
        "",
        f"The original bead ({ctx.title}) was committed after passing"
        f" validation but the reviewer repeatedly requested changes"
        f" ({len(prior_failures)} attempts).",
        "",
    ]

    # Extract verbatim review findings from review_report markdown
    if ctx.review_result:
        review_report = ctx.review_result.get("review_report", "")
        if review_report:
            parts.append("## Reviewer Findings")
            parts.append("")
            parts.append(review_report)
            parts.append("")

    # Include failure history for context
    parts.append("## Failure History")
    parts.append("")
    for i, reason in enumerate(prior_failures, 1):
        parts.append(f"- Attempt {i}: {reason}")

    return "\n".join(parts)


def _build_escalation_description(
    chain: list[str],
    chain_titles: dict[str, str],
    review_report: str,
    prior_failures: list[str],
) -> str:
    """Build a description for the Tier 2 re-planning bead.

    Contains the full provenance chain, the verbatim reviewer objection,
    and instructions for the decomposer to re-plan the stuck work.
    """
    parts = [
        "# Re-Planning Required",
        "",
        "A reviewer issue persisted across multiple implementation attempts.",
        "The work boundaries need to be re-decomposed.",
        "",
        "## Bead Chain",
        "",
    ]
    for bid in chain:
        title = chain_titles.get(bid, bid)
        parts.append(f"- `{bid}`: {title}")
    parts.append("")

    if review_report:
        parts.append("## Persistent Reviewer Finding")
        parts.append("")
        parts.append(review_report)
        parts.append("")

    if prior_failures:
        parts.append("## Most Recent Failure History")
        parts.append("")
        for i, reason in enumerate(prior_failures, 1):
            parts.append(f"- Attempt {i}: {reason}")
        parts.append("")

    parts.extend([
        "## Instructions",
        "",
        "Re-decompose ONLY the work that failed. Do not re-plan"
        " already-completed beads. The codebase has been updated with"
        " the committed (but reviewer-rejected) changes — build on that"
        " work rather than starting over.",
        "",
        "Consider whether the original decomposition drew the boundary"
        " wrong (e.g., two beads that should have been one), or whether"
        " the reviewer is flagging an architectural concern that requires"
        " a different approach entirely.",
    ])

    return "\n".join(parts)
