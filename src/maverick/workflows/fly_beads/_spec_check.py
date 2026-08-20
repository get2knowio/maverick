"""Pure-Python spec-compliance grep checks for the fly workflow.

Ports the rule engine from the pre-migration ``SpecCheckActor`` into a
substrate-independent helper that the Burr ``spec_check`` action can
call directly. No agent, no LLM — just :mod:`subprocess` calls
to ``git diff`` and ``grep``.

Rust is the only project type with rules today (matches the legacy
behaviour). Other project types return ``passed=True`` with no findings.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# (grep_pattern, description, severity) — Rust-specific anti-patterns.
# Patterns are passed to ``grep -F`` (fixed string) so no regex escapes
# are needed; ``.`` is literal, ``(`` is literal. The pre-migration
# ``SpecCheckActor`` shipped escapes (``r"\.unwrap()"``) but combined
# them with ``grep -F``, which never matched — fixed here.
RUST_CHECKS: list[tuple[str, str, str]] = [
    (
        ".unwrap()",
        "unwrap() in runtime code — use Result propagation with .context() instead",
        "critical",
    ),
    (
        ".expect(",
        "unchecked expect() in runtime code — use fallible error handling instead",
        "critical",
    ),
    (
        "std::process::Command",
        "blocking std::process::Command in async code — use tokio::process::Command",
        "critical",
    ),
]


@dataclass(frozen=True, slots=True)
class SpecCheckResult:
    """One pass through the spec-compliance rules.

    Attributes:
        passed: ``True`` when no critical findings landed.
        details: Short human-readable summary.
        findings: Per-finding strings formatted as
            ``"file:line: <description> — `<code>`"``.
    """

    passed: bool
    details: str
    findings: tuple[str, ...] = ()


def run_spec_check(*, cwd: str, project_type: str = "rust") -> SpecCheckResult:
    """Run the spec-compliance grep checks against changed files.

    Args:
        cwd: Workspace directory; ``git diff HEAD`` is run here.
        project_type: ``"rust"`` enables :data:`RUST_CHECKS`; anything
            else returns a no-op pass.
    """
    if not cwd:
        return SpecCheckResult(passed=True, details="no cwd — skipped")

    changed = _get_changed_files(cwd)
    if not changed:
        return SpecCheckResult(passed=True, details="no changed files")

    checks = RUST_CHECKS if project_type == "rust" else []
    if not checks:
        return SpecCheckResult(passed=True, details=f"no checks for project type {project_type!r}")

    source_files = _filter_source_files(changed, project_type=project_type)
    if not source_files:
        return SpecCheckResult(passed=True, details="only test files changed")

    findings_raw: list[dict[str, str]] = []
    for pattern, description, severity in checks:
        for file_path, line_num, line_text in _grep_files(cwd, pattern, source_files):
            findings_raw.append(
                {
                    "file": file_path,
                    "line": line_num,
                    "description": description,
                    "severity": severity,
                    "text": line_text.strip()[:200],
                }
            )

    critical = [f for f in findings_raw if f["severity"] == "critical"]
    passed = not critical
    details = (
        f"{len(critical)} critical, {len(findings_raw) - len(critical)} warnings"
        if findings_raw
        else "all checks passed"
    )
    formatted = tuple(
        f"{f['file']}:{f['line']}: {f['description']} — `{f['text']}`" for f in findings_raw
    )
    return SpecCheckResult(passed=passed, details=details, findings=formatted)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _get_changed_files(cwd: str) -> list[str]:
    """Return paths the working copy has changed since its parent.

    Uses ``git diff`` when *cwd* is a git working tree (the historical,
    well-tested path — unchanged). A `fly --isolated` bead's workspace
    (``jj workspace add``) has no ``.git`` of its own — confirmed against
    real jj 0.44, only ``.jj`` exists there — so ``git diff`` used to fail
    there with a non-zero exit that this function silently swallowed,
    making every isolated bead's spec check permanently report "no
    changed files" regardless of what the bead actually changed. Falls
    back to ``jj diff --name-only`` (the jj-native equivalent) whenever
    *cwd* isn't a git checkout.
    """
    if (Path(cwd) / ".git").exists():
        return _git_changed_files(cwd)
    return _jj_changed_files(cwd)


def _git_changed_files(cwd: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
            start_new_session=True,
            check=False,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:  # noqa: BLE001 — git can fail many ways; treat as "no diff"
        pass
    return []


def _jj_changed_files(cwd: str) -> list[str]:
    """``jj diff --name-only`` against the working copy's parent — the
    jj-native equivalent of ``_git_changed_files`` for a workspace with no
    ``.git``. jj has no ``--diff-filter`` flag, so a deleted path (which
    git's ``ACMR`` filter excludes) is dropped here by checking it still
    exists on disk — deleted files have nothing left to grep anyway.
    """
    try:
        result = subprocess.run(
            ["jj", "diff", "--name-only"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
            start_new_session=True,
            check=False,
        )
        if result.returncode == 0:
            base = Path(cwd)
            return [
                f.strip()
                for f in result.stdout.strip().split("\n")
                if f.strip() and (base / f.strip()).is_file()
            ]
    except Exception:  # noqa: BLE001 — jj can fail many ways; treat as "no diff"
        pass
    return []


def _filter_source_files(files: list[str], *, project_type: str) -> list[str]:
    """Keep only source files for ``project_type``; drop tests."""
    out: list[str] = []
    for f in files:
        if "/tests/" in f or f.startswith("tests/"):
            continue
        if f.endswith("_test.rs") or f.endswith("_tests.rs"):
            continue
        if (project_type == "rust" and f.endswith(".rs")) or (
            project_type == "python" and f.endswith(".py")
        ):
            out.append(f)
    return out


def _grep_files(cwd: str, pattern: str, files: list[str]) -> list[tuple[str, str, str]]:
    """Run ``grep -nF pattern <files>`` under ``cwd``.

    Returns ``(file_path, line_num, line_text)`` triples, with lines
    that look like test scaffolding filtered out.
    """
    hits: list[tuple[str, str, str]] = []
    try:
        # ``-H`` forces ``grep`` to prefix the filename even when only
        # one file is passed — otherwise the parser below sees
        # ``"line:content"`` and skips it because there's no
        # ``file:line:content`` split.
        cmd = ["grep", "-H", "-n", "-F", pattern, *files]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
            start_new_session=True,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path, line_num, line_text = parts[0], parts[1], parts[2]
                    if _is_test_context(line_text):
                        continue
                    hits.append((file_path, line_num, line_text))
    except Exception:  # noqa: BLE001 — grep can fail many ways
        pass
    return hits


def _is_test_context(line_text: str) -> bool:
    """Heuristic: skip lines that obviously live in test scaffolding."""
    text = line_text.strip()
    if text.startswith("//"):
        return True
    if "#[test]" in text or "#[cfg(test)]" in text:
        return True
    return "assert!" in text or "assert_eq!" in text
