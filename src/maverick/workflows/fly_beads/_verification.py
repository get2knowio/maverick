"""Deterministic acceptance + spec-compliance checks for fly-beads."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.logging import get_logger
from maverick.workflows.fly_beads._plan_parsing import (
    _parse_file_scope,
    _parse_verification_commands,
    _parse_work_unit_sections,
)
from maverick.workflows.fly_beads._vcs_queries import _get_uncommitted_files
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)

_TEST_ATTR_RE = re.compile(r"#\[test\]")


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

    if not file_scope_text and not verification_text:
        await wf.emit_step_completed(ACCEPTANCE_CHECK)
        return True, []

    create, modify, protect = _parse_file_scope(file_scope_text)

    changed = set(await _get_uncommitted_files(ctx.cwd))

    if create:
        for f in create:
            fpath = ctx.cwd / f if ctx.cwd else Path(f)
            if not fpath.exists():
                reasons.append(f"File scope requires creating '{f}' but it does not exist")

    if protect and changed:
        for f in protect:
            if f in changed:
                reasons.append(
                    f"File '{f}' is marked as protected but was modified by the implementation"
                )

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

    if verification_text and ctx.cwd:
        from maverick.runners.command import CommandRunner

        runner = CommandRunner(cwd=ctx.cwd)
        for cmd_str in _parse_verification_commands(verification_text):
            first_word = cmd_str.split()[0] if cmd_str.split() else ""
            if first_word not in ("rg", "grep", "cargo", "make"):
                continue
            try:
                result = await runner.run(["sh", "-c", cmd_str])
                if result.returncode != 0:
                    reasons.append(f"Verification command failed: `{cmd_str}`")
            except Exception as exc:
                reasons.append(f"Verification command error: `{cmd_str}`: {exc}")

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

    code = verification_properties
    if "```" in code:
        parts = code.split("```")
        if len(parts) >= 3:
            block = parts[1]
            if "\n" in block:
                block = block.split("\n", 1)[1]
            code = block.strip()

    if "verify_" not in code:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
        return True, []

    # Append VP tests to the main source file's test module, run
    # them, then remove the appended code. This avoids the Rust
    # visibility issue where integration tests can't access
    # private functions in binary crates.
    test_fns: list[str] = []
    in_fn = False
    fn_lines: list[str] = []
    brace_depth = 0
    for line in code.split("\n"):
        stripped = line.strip()
        if _TEST_ATTR_RE.match(stripped):
            in_fn = True
            fn_lines = [stripped]
            brace_depth = 0
        elif in_fn:
            fn_lines.append(stripped)
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0 and "}" in stripped:
                test_fns.append("\n    ".join(fn_lines))
                in_fn = False
                fn_lines = []

    if not test_fns:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
        return True, []

    src_candidates = list((ctx.cwd / "src").rglob("main.rs"))
    if not src_candidates:
        src_candidates = list((ctx.cwd / "src").rglob("lib.rs"))
    if not src_candidates:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
        return True, []

    src_path = src_candidates[0]
    original_content = src_path.read_text(encoding="utf-8")

    marker = "// --- SPEC_COMPLIANCE_MARKER ---"
    vp_block = f"\n{marker}\n" + "\n".join(f"    {fn}" for fn in test_fns) + f"\n{marker}\n"

    if "#[cfg(test)]" in original_content:
        last_brace = original_content.rfind("}")
        if last_brace > 0:
            modified = original_content[:last_brace] + vp_block + original_content[last_brace:]
        else:
            modified = original_content + vp_block
    else:
        modified = (
            original_content
            + "\n#[cfg(test)]\nmod spec_verify {\n"
            + "    use super::*;\n"
            + vp_block
            + "}\n"
        )

    try:
        from maverick.runners.command import CommandRunner

        runner = CommandRunner(cwd=ctx.cwd)

        src_path.write_text(modified, encoding="utf-8")

        result = await runner.run(["sh", "-c", "cargo test verify_ 2>&1"])

        output = (result.stdout or "") + (result.stderr or "")

        if "test result: ok" in output:
            pass
        elif "test result: FAILED" in output:
            for line in output.split("\n"):
                stripped = line.strip()
                if (
                    "FAILED" in stripped
                    and "verify_" in stripped
                    or "panicked at" in stripped
                    or "left:" in stripped
                    or "right:" in stripped
                ):  # noqa: E501
                    reasons.append(stripped[:200])
            if not reasons:
                reasons.append("Spec compliance tests FAILED. Check output.")
        elif "error" in output.lower() and result.returncode != 0:
            for line in output.split("\n"):
                if "error" in line.lower():
                    reasons.append("Spec test compile error: " + line.strip()[:200])
                    break
            if not reasons:
                reasons.append("Spec compliance tests failed to compile")

    except Exception as exc:
        reasons.append(f"Spec compliance check error: {exc}")
    finally:
        src_path.write_text(original_content, encoding="utf-8")

    passed = len(reasons) == 0
    if passed:
        await wf.emit_step_completed(SPEC_COMPLIANCE)
    else:
        await wf.emit_step_failed(SPEC_COMPLIANCE, "; ".join(reasons))

    return passed, reasons
