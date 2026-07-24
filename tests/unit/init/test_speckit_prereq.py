"""Unit tests for `maverick.init.prereqs.check_speckit_installed` (R7, US5)."""

from __future__ import annotations

from pathlib import Path

from maverick.init.models import PreflightStatus
from maverick.init.prereqs import check_speckit_installed


class TestCheckSpeckitInstalled:
    def test_missing_specify_dir_fails(self, tmp_path: Path) -> None:
        result = check_speckit_installed(tmp_path)
        assert result.status == PreflightStatus.FAIL
        assert result.name == "speckit_installed"
        assert result.remediation is not None
        assert "specify init" in result.remediation

    def test_specify_dir_present_no_init_options_json_passes_as_unknown_version(
        self, tmp_path: Path
    ) -> None:
        """`.specify/` present but no version metadata — treated as
        "installed, proceed structurally" (matches refuel's tolerance for
        "unknown" template versions), not a hard failure."""
        (tmp_path / ".specify").mkdir()
        result = check_speckit_installed(tmp_path)
        assert result.status == PreflightStatus.PASS

    def test_supported_version_passes(self, tmp_path: Path) -> None:
        specify_dir = tmp_path / ".specify"
        specify_dir.mkdir()
        (specify_dir / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )
        result = check_speckit_installed(tmp_path)
        assert result.status == PreflightStatus.PASS
        assert "0.14.0" in result.message

    def test_unsupported_version_fails(self, tmp_path: Path) -> None:
        specify_dir = tmp_path / ".specify"
        specify_dir.mkdir()
        (specify_dir / "init-options.json").write_text(
            '{"speckit_version": "0.9.0"}', encoding="utf-8"
        )
        result = check_speckit_installed(tmp_path)
        assert result.status == PreflightStatus.FAIL
        assert "0.9.0" in result.message
        assert result.remediation is not None

    def test_unparseable_init_options_json_treated_as_unknown_version(
        self, tmp_path: Path
    ) -> None:
        specify_dir = tmp_path / ".specify"
        specify_dir.mkdir()
        (specify_dir / "init-options.json").write_text("not valid json{{{", encoding="utf-8")
        result = check_speckit_installed(tmp_path)
        assert result.status == PreflightStatus.PASS

    def test_never_raises_only_returns_prerequisite_check(self, tmp_path: Path) -> None:
        """Advisory contract: this check must never hard-fail (raise) —
        callers (init's offer flow, `maverick spec`'s own preflight) rely
        on inspecting the returned PrerequisiteCheck, not exception
        handling."""
        result = check_speckit_installed(tmp_path / "does" / "not" / "exist")
        assert result.status == PreflightStatus.FAIL
