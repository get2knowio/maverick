"""SpecCheckActor — Thespian actor for spec compliance verification.

Runs deterministic grep-based checks against changed files to catch
coding convention violations. No LLM, no cost, fast.

Checks are project-type aware: Rust projects get unwrap/blocking-call
detection; other project types get basic checks.
"""

import subprocess
import sys

from thespian.actors import Actor

# Rust-specific anti-pattern checks.
# Each tuple: (grep_pattern, description, severity)
# severity: "critical" blocks the bead, "warning" is informational
RUST_CHECKS = [
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


class SpecCheckActor(Actor):
    """Deterministic spec compliance check against changed files."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._cwd = message.get("cwd")
            self._project_type = message.get("project_type", "rust")
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "spec_check":
            cwd = message.get("cwd") or self._cwd
            result = self._run_checks(cwd)
            self.send(sender, result)

    def _run_checks(self, cwd):
        """Run convention checks against files changed since last commit."""
        if not cwd:
            return {
                "type": "spec_result",
                "passed": True,
                "details": "no cwd — skipped",
                "findings": [],
            }

        # Get changed files (staged + unstaged vs HEAD)
        changed_files = self._get_changed_files(cwd)
        if not changed_files:
            return {
                "type": "spec_result",
                "passed": True,
                "details": "no changed files",
                "findings": [],
            }

        # Select checks based on project type
        checks = RUST_CHECKS if self._project_type == "rust" else []
        if not checks:
            return {
                "type": "spec_result",
                "passed": True,
                "details": f"no checks for project type '{self._project_type}'",
                "findings": [],
            }

        # Filter to source files (exclude tests)
        source_files = self._filter_source_files(changed_files)
        if not source_files:
            return {
                "type": "spec_result",
                "passed": True,
                "details": "only test files changed",
                "findings": [],
            }

        # Run each check
        findings = []
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
        passed = len(critical) == 0

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

        return {
            "type": "spec_result",
            "passed": passed,
            "details": (
                f"{len(critical)} critical, {len(findings) - len(critical)} warnings"
                if findings
                else "all checks passed"
            ),
            "findings": [
                f"{f['file']}:{f['line']}: {f['description']} — `{f['text']}`" for f in findings
            ],
        }

    def _get_changed_files(self, cwd):
        """Get list of files changed vs HEAD."""
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMR"],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=10,
                start_new_session=True,
            )
            if result.returncode == 0:
                return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception:
            pass
        return []

    def _filter_source_files(self, files):
        """Filter to non-test source files based on project type."""
        source_files = []
        for f in files:
            # Skip test files
            if "/tests/" in f or f.startswith("tests/"):
                continue
            if f.endswith("_test.rs") or f.endswith("_tests.rs"):
                continue
            # Include source files
            if (
                self._project_type == "rust"
                and f.endswith(".rs")
                or self._project_type == "python"
                and f.endswith(".py")
            ):
                source_files.append(f)
        return source_files

    def _grep_files(self, cwd, pattern, files):
        """Grep for a pattern in specific files, returning (file, line, text) tuples."""
        hits = []
        try:
            # Use grep with fixed string matching for safety
            cmd = ["grep", "-n", "-F", pattern] + files
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=10,
                start_new_session=True,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    # Parse grep output: file:line:text
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        file_path = parts[0]
                        line_num = parts[1]
                        line_text = parts[2]

                        # Skip if the match is inside a test module
                        if self._is_test_context(line_text):
                            continue

                        hits.append((file_path, line_num, line_text))
        except Exception:
            pass
        return hits

    def _is_test_context(self, line_text):
        """Heuristic: skip lines that are clearly inside test code."""
        text = line_text.strip()
        # Common test markers in Rust
        if text.startswith("//"):
            return True  # Comments
        if "#[test]" in text or "#[cfg(test)]" in text:
            return True
        return bool("assert!" in text or "assert_eq!" in text)
