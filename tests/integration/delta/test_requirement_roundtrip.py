"""SC-010: byte-identical round-trip over the LIVE ``specs/`` tree.

This is the design's own falsification mechanism (research R1): every rule
in ``contracts/requirement-block-grammar.md`` is a measured claim about the
54 real ``specs/*/spec.md`` files in this repository. A wrong rule must
fail here — against the live tree, not a frozen fixture — rather than
corrupt a spec in use. A fixture would freeze the corpus at capture time,
and the next spec written in an unanticipated style would pass the suite
and fail in production.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.speckit.requirements import parse_requirements, render_requirements

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECS_DIR = _REPO_ROOT / "specs"


def _all_spec_md_files() -> list[Path]:
    if not _SPECS_DIR.is_dir():
        return []
    return sorted(_SPECS_DIR.glob("*/spec.md"))


_SPEC_FILES = _all_spec_md_files()


@pytest.mark.skipif(not _SPEC_FILES, reason="no specs/*/spec.md found in this checkout")
@pytest.mark.parametrize(
    "spec_path", _SPEC_FILES, ids=lambda p: p.relative_to(_SPECS_DIR).parts[0]
)
def test_round_trip_is_byte_identical(spec_path: Path) -> None:
    original = spec_path.read_text(encoding="utf-8")

    section = parse_requirements(original, file=str(spec_path))
    rendered = render_requirements(section)

    if rendered == original:
        return

    # Name the file and the first differing line on failure (contract
    # requirement) — an assert on the whole string just prints a diff
    # nobody can read for a 30KB spec.
    original_lines = original.splitlines(keepends=True)
    rendered_lines = rendered.splitlines(keepends=True)
    pairs = enumerate(zip(original_lines, rendered_lines, strict=False), start=1)
    first_diff = next(
        (i for i, (a, b) in pairs if a != b),
        min(len(original_lines), len(rendered_lines)) + 1,
    )

    def _line_at(lines: list[str], index: int) -> str:
        return repr(lines[index - 1]) if index - 1 < len(lines) else "<EOF>"

    pytest.fail(
        f"{spec_path}: round-trip mismatch at line {first_diff}\n"
        f"  original: {_line_at(original_lines, first_diff)}\n"
        f"  rendered: {_line_at(rendered_lines, first_diff)}"
    )
