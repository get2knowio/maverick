"""xoscar SpecCheckActor — deterministic spec-compliance verification.

Runs grep-based convention checks against files changed since last
commit. No LLM, no cost. Rust-specific by default; other project
types return a no-op pass.
"""

from __future__ import annotations

import subprocess
import sys

import xoscar as xo

from maverick.actors.xoscar.messages import SpecRequest, SpecResult

# Rust-specific anti-pattern checks.
# (grep_pattern, description, severity)
RUST_CHECKS: list[tuple[str, str, str]] = [
    (
        r"\.unwrap()",
        "unwrap() in runtime code — use Result propagation with .context() instead",
        "critical",
    ),
    (
        r"\.expect(",
        "unchecked expect() in runtime code — use fallible error handling instead",
        "critical",
    ),
    (
        r"std::process::Command",
        "blocking std::process::Command in async code — use tokio::process::Command",
        "critical",
    ),
]


class SpecCheckActor(xo.Actor):
    """Deterministic spec compliance check against changed files."""

    def __init__(self, *, project_type: str = "rust") -> None:
        super().__init__()
        self._project_type = project_type

    async def spec_check(self, request: SpecRequest) -> SpecResult:
        cwd = request.cwd
        if not cwd:
            return SpecResult(passed=True, details="no cwd — skipped")

        changed_files = self._get_changed_files(cwd)
        if not changed_files:
            return SpecResult(passed=True, details="no changed files")

        checks = RUST_CHECKS if self._project_type == "rust" else []
        if not checks:
            return SpecResult(
                passed=True,
                details=f"no checks for project type '{self._project_type}'",
            )

        source_files = self._filter_source_files(changed_files)
        if not source_files:
            return SpecResult(passed=True, details="only test files changed")

        findings: list[dict[str, str]] = []
        for pattern, description, severity in checks:
            hits = self._grep_files(cwd, pattern, source_files)
            for file_path, line_num, line_text in hits:
                findings.append(
                    {
                        "file": file_path,
                        "line": line_num,
                        "pattern": pattern,
                        "description": description,
                        "severity": severity,
                        "text": line_text.strip()[:200],
                    }
                )

        critical = [f for f in findings if f["severity"] == "critical"]
        passed = not critical

        if findings:
            print(
                f"SPEC_CHECK: {len(findings)} findings "
                f"({len(critical)} critical) in {len(source_files)} files",
                file=sys.stderr,
                flush=True,
            )
            for f in findings[:5]:
                print(
                    f"  {f['severity']}: {f['file']}:{f['line']} — {f['description']}",
                    file=sys.stderr,
                    flush=True,
                )

        details = (
            f"{len(critical)} critical, {len(findings) - len(critical)} warnings"
            if findings
            else "all checks passed"
        )
        formatted = tuple(
            f"{f['file']}:{f['line']}: {f['description']} — `{f['text']}`" for f in findings
        )
        return SpecResult(passed=passed, details=details, findings=formatted)

    def _get_changed_files(self, cwd: str) -> list[str]:
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
        except Exception:  # noqa: BLE001
            pass
        return []

    def _filter_source_files(self, files: list[str]) -> list[str]:
        source_files: list[str] = []
        for f in files:
            if "/tests/" in f or f.startswith("tests/"):
                continue
            if f.endswith("_test.rs") or f.endswith("_tests.rs"):
                continue
            if (
                self._project_type == "rust"
                and f.endswith(".rs")
                or self._project_type == "python"
                and f.endswith(".py")
            ):
                source_files.append(f)
        return source_files

    def _grep_files(self, cwd: str, pattern: str, files: list[str]) -> list[tuple[str, str, str]]:
        hits: list[tuple[str, str, str]] = []
        try:
            cmd = ["grep", "-n", "-F", pattern, *files]
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
                        if self._is_test_context(line_text):
                            continue
                        hits.append((file_path, line_num, line_text))
        except Exception:  # noqa: BLE001
            pass
        return hits

    def _is_test_context(self, line_text: str) -> bool:
        text = line_text.strip()
        if text.startswith("//"):
            return True
        if "#[test]" in text or "#[cfg(test)]" in text:
            return True
        return bool("assert!" in text or "assert_eq!" in text)
