"""Tests for the pure matching primitives (protection/matching.py).

See specs/056-context-file-protection/research.md R5 for the authoritative
matching semantics and data-model.md's "ProtectionPolicy" section for the
decision algorithm these primitives feed into (implemented separately in
protection/policy.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import pathspec

from maverick.protection.matching import (
    compile_globs,
    is_default_protected,
    matches_glob,
    normalize_relpath,
)


class TestNormalizeRelpathBasenames:
    def test_relative_candidate_at_root(self, tmp_path: Path) -> None:
        assert normalize_relpath("CLAUDE.md", root=tmp_path, resolve=True) == "CLAUDE.md"

    def test_relative_candidate_nested(self, tmp_path: Path) -> None:
        result = normalize_relpath("sub/dir/AGENTS.md", root=tmp_path, resolve=True)
        assert result == "sub/dir/AGENTS.md"

    def test_absolute_candidate_under_root(self, tmp_path: Path) -> None:
        target = tmp_path / "AGENTS.md"
        assert normalize_relpath(target, root=tmp_path, resolve=True) == "AGENTS.md"

    def test_pathlib_candidate_accepted(self, tmp_path: Path) -> None:
        result = normalize_relpath(Path("sub") / "CLAUDE.md", root=tmp_path, resolve=True)
        assert result == "sub/CLAUDE.md"

    def test_root_itself_returns_empty_string(self, tmp_path: Path) -> None:
        assert normalize_relpath(tmp_path, root=tmp_path, resolve=True) == "."


class TestNormalizeRelpathOutsideRoot:
    def test_dotdot_escape_relative(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        result = normalize_relpath("../../etc/passwd", root=root, resolve=False)
        assert result is None

    def test_absolute_path_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "elsewhere" / "AGENTS.md"
        assert normalize_relpath(outside, root=root, resolve=True) is None
        assert normalize_relpath(outside, root=root, resolve=False) is None

    def test_symlink_resolving_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside_target = tmp_path / "outside.md"
        outside_target.write_text("outside content")
        link = root / "escape.md"
        os.symlink(outside_target, link)

        # Resolved side: the symlink dereferences outside root -> None.
        assert normalize_relpath(link, root=root, resolve=True) is None
        # Literal side: the link itself lives inside root -> still normalized.
        assert normalize_relpath(link, root=root, resolve=False) == "escape.md"


class TestNormalizeRelpathSymlinkPlant:
    """FR-014: catch a symlink planted at a protected path before dereferencing."""

    def test_literal_side_sees_the_link_not_the_target(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "sub").mkdir(parents=True)
        real_claude = root / "CLAUDE.md"
        real_claude.write_text("real content")
        link = root / "sub" / "link.md"
        os.symlink(real_claude, link)

        literal = normalize_relpath(link, root=root, resolve=False)
        assert literal == "sub/link.md"

    def test_resolved_side_sees_the_real_target(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "sub").mkdir(parents=True)
        real_claude = root / "CLAUDE.md"
        real_claude.write_text("real content")
        link = root / "sub" / "link.md"
        os.symlink(real_claude, link)

        resolved = normalize_relpath(link, root=root, resolve=True)
        assert resolved == "CLAUDE.md"

    def test_both_sides_are_independently_checkable_against_defaults(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "sub").mkdir(parents=True)
        real_claude = root / "CLAUDE.md"
        real_claude.write_text("real content")
        link = root / "sub" / "link.md"
        os.symlink(real_claude, link)

        literal = normalize_relpath(link, root=root, resolve=False)
        resolved = normalize_relpath(link, root=root, resolve=True)

        assert literal is not None
        assert resolved is not None
        # The resolved side catches it because CLAUDE.md is a default name.
        assert is_default_protected(resolved) is True
        # The literal side (sub/link.md) is not itself a default name, but is
        # still independently checkable — this is what a policy's allowlist/
        # extra-glob pass against the literal side would use.
        assert is_default_protected(literal) is False


class TestNormalizeRelpathRootResolution:
    def test_root_with_trailing_symlink_component_resolved(self, tmp_path: Path) -> None:
        real_root = tmp_path / "real_root"
        real_root.mkdir()
        (real_root / "CLAUDE.md").write_text("x")
        linked_root = tmp_path / "linked_root"
        os.symlink(real_root, linked_root)

        # Candidate expressed via the symlinked root, resolve=True normalizes
        # both root and candidate onto the same (real) footing.
        result = normalize_relpath(linked_root / "CLAUDE.md", root=linked_root, resolve=True)
        assert result == "CLAUDE.md"


class TestIsDefaultProtectedBasenames:
    def test_agents_md_exact(self) -> None:
        assert is_default_protected("AGENTS.md") is True

    def test_claude_md_lowercase(self) -> None:
        assert is_default_protected("claude.md") is True

    def test_agents_md_mixed_case_nested(self) -> None:
        assert is_default_protected("sub/dir/Agents.MD") is True

    def test_claude_md_uppercase(self) -> None:
        assert is_default_protected("CLAUDE.MD") is True

    def test_nested_depth(self) -> None:
        assert is_default_protected("a/b/c/d/CLAUDE.md") is True

    def test_unrelated_file(self) -> None:
        assert is_default_protected("README.md") is False

    def test_similar_name_not_exact(self) -> None:
        assert is_default_protected("docs/AGENTS.md.bak") is False


class TestIsDefaultProtectedSpecifyMemory:
    def test_direct_child(self) -> None:
        assert is_default_protected(".specify/memory/x.md") is True

    def test_nested_child(self) -> None:
        assert is_default_protected(".specify/memory/nested/y.md") is True

    def test_case_insensitive_segments(self) -> None:
        assert is_default_protected(".SPECIFY/Memory/x.md") is True

    def test_missing_leading_dot(self) -> None:
        assert is_default_protected("specify/memory/x.md") is False

    def test_wrong_second_segment(self) -> None:
        assert is_default_protected(".specify/other/x.md") is False

    def test_empty_relpath(self) -> None:
        assert is_default_protected("") is False


class TestCompileGlobsValid:
    def test_double_star_matches_nested(self) -> None:
        spec, dropped = compile_globs(["**/*.md"])
        assert dropped == []
        assert matches_glob("docs/nested/file.md", spec) is True

    def test_exact_filename_matches(self) -> None:
        spec, dropped = compile_globs(["GEMINI.md"])
        assert dropped == []
        assert matches_glob("GEMINI.md", spec) is True
        assert matches_glob("sub/GEMINI.md", spec) is True

    def test_non_matching_pattern(self) -> None:
        spec, dropped = compile_globs(["*.txt"])
        assert dropped == []
        assert matches_glob("file.md", spec) is False

    def test_empty_pattern_list_matches_nothing(self) -> None:
        spec, dropped = compile_globs([])
        assert dropped == []
        assert isinstance(spec, pathspec.PathSpec)
        assert matches_glob("anything.md", spec) is False
        assert matches_glob("", spec) is False


class TestCompileGlobsInvalid:
    def test_invalid_pattern_dropped_reported(self) -> None:
        # A trailing unescaped backslash is rejected by pathspec's
        # gitwildmatch parser (GitWildMatchPatternError, a ValueError
        # subclass) — verified against the installed pathspec version.
        spec, dropped = compile_globs(["a\\"])
        assert dropped == ["a\\"]
        assert matches_glob("a", spec) is False

    def test_invalid_pattern_does_not_break_the_rest(self) -> None:
        spec, dropped = compile_globs(["**/*.md", "a\\", "GEMINI.md"])
        assert dropped == ["a\\"]
        assert matches_glob("docs/x.md", spec) is True
        assert matches_glob("GEMINI.md", spec) is True

    def test_multiple_invalid_patterns_all_reported(self) -> None:
        spec, dropped = compile_globs(["a\\", "**/*.md", "docs/\\"])
        assert dropped == ["a\\", "docs/\\"]
        assert matches_glob("x.md", spec) is True


class TestMatchesGlob:
    def test_double_star_crosses_directories(self) -> None:
        spec, _ = compile_globs(["docs/**/secret.md"])
        assert matches_glob("docs/a/b/c/secret.md", spec) is True
        assert matches_glob("docs/secret.md", spec) is True

    def test_single_star_does_not_cross_directories(self) -> None:
        spec, _ = compile_globs(["docs/*.md"])
        assert matches_glob("docs/file.md", spec) is True
        assert matches_glob("docs/sub/file.md", spec) is False

    def test_no_match_returns_false(self) -> None:
        spec, _ = compile_globs(["*.md"])
        assert matches_glob("file.py", spec) is False
