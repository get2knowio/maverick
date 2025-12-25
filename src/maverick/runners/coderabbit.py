"""CodeRabbit runner for AI-powered code review."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.runners.preflight import ValidationResult

from maverick.logging import get_logger
from maverick.runners.command import CommandRunner
from maverick.runners.models import CodeRabbitFinding, CodeRabbitResult

__all__ = ["CodeRabbitRunner"]

logger = get_logger(__name__)


class CodeRabbitRunner:
    """Execute CodeRabbit code reviews with graceful degradation."""

    def __init__(self) -> None:
        """Initialize the CodeRabbitRunner."""
        self._command_runner = CommandRunner()

    async def is_available(self) -> bool:
        """Check if CodeRabbit CLI is installed and available."""
        return shutil.which("coderabbit") is not None

    async def validate(self) -> ValidationResult:
        """Validate that CodeRabbit is available.

        CodeRabbit is optional, so missing CLI is a warning, not an error.
        This method always returns success=True.

        Returns:
            ValidationResult with warnings if CLI not installed.
        """
        from maverick.runners.preflight import ValidationResult

        start = time.monotonic()

        warnings: tuple[str, ...] = ()
        if not await self.is_available():
            warnings = ("CodeRabbit CLI not installed (optional)",)

        duration_ms = int((time.monotonic() - start) * 1000)

        return ValidationResult(
            success=True,  # Always success - CodeRabbit is optional
            component="CodeRabbitRunner",
            errors=(),
            warnings=warnings,
            duration_ms=duration_ms,
        )

    def _parse_findings(self, output: str) -> list[CodeRabbitFinding]:
        """Parse CodeRabbit output into structured findings."""
        findings: list[CodeRabbitFinding] = []

        try:
            # Try to parse as JSON first
            data = json.loads(output)
            if isinstance(data, dict) and "findings" in data:
                for item in data["findings"]:
                    findings.append(
                        CodeRabbitFinding(
                            file=item.get("file", ""),
                            line=item.get("line", 1),
                            severity=item.get("severity", "info"),
                            message=item.get("message", ""),
                            suggestion=item.get("suggestion"),
                            category=item.get("category"),
                        )
                    )
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        findings.append(
                            CodeRabbitFinding(
                                file=item.get("file", ""),
                                line=item.get("line", 1),
                                severity=item.get("severity", "info"),
                                message=item.get("message", ""),
                                suggestion=item.get("suggestion"),
                                category=item.get("category"),
                            )
                        )
        except json.JSONDecodeError as e:
            # If not JSON, gracefully degrade with warning
            logger.warning("Failed to parse CodeRabbit output as JSON: %s", e)
            return []
        except Exception as e:
            # Catch any other unexpected parsing errors
            logger.warning("Unexpected error parsing CodeRabbit findings: %s", e)
            return []

        return findings

    async def run_review(
        self,
        files: list[Path] | None = None,
    ) -> CodeRabbitResult:
        """Run CodeRabbit review on specified files.

        Args:
            files: List of files to review. If None, reviews all changed files.

        Returns:
            CodeRabbitResult with findings or warnings if not available.
        """
        # Check availability first - graceful degradation
        if not await self.is_available():
            return CodeRabbitResult(
                findings=(),
                summary="",
                raw_output="",
                warnings=(
                    "CodeRabbit CLI not installed. Install from: https://coderabbit.ai/",
                ),
            )

        # Build command
        args = ["coderabbit", "review"]
        if files:
            args.extend(str(f) for f in files)

        # Run review
        result = await self._command_runner.run(args, timeout=300.0)

        # Handle malformed output gracefully
        if not result.success and result.returncode == 127:
            return CodeRabbitResult(
                findings=(),
                summary="",
                raw_output=result.output,
                warnings=("CodeRabbit command not found",),
            )

        # Parse findings
        findings = self._parse_findings(result.stdout)

        # Generate summary
        error_count = sum(1 for f in findings if f.severity == "error")
        warning_count = sum(1 for f in findings if f.severity == "warning")
        summary = (
            f"Found {len(findings)} issues: "
            f"{error_count} errors, {warning_count} warnings"
        )

        return CodeRabbitResult(
            findings=tuple(findings),
            summary=summary if findings else "No issues found",
            raw_output=result.stdout,
            warnings=(),
        )
