"""Requirement-block grammar for ``spec.md``: parse + render with a
byte-identical round-trip.

See ``specs/059-spec-delta-layer/contracts/requirement-block-grammar.md``
for the normative grammar this module implements, and ``research.md`` R1
for the corpus measurements behind every rule below.

The round-trip invariant (SC-010) is ``render(parse(text)) == text`` for
every ``specs/*/spec.md`` in the repository. That is why every field here
stores lines **verbatim** rather than normalized, and why
:class:`RequirementSection` carries the raw ``prefix``/``suffix`` text
surrounding the section (beyond what ``data-model.md``'s field table
lists) — reconstructing the *whole file* byte-for-byte needs that text
somewhere, and storing it verbatim rather than re-deriving it is what
makes the round-trip mechanical instead of aspirational.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from maverick.speckit.errors import SpeckitParseError

#: Anchors the section start. The bare form (``### Functional
#: Requirements``) covers 53/54 specs; one legacy spec (004, predating
#: the single-heading convention) splits the section into
#: ``### Functional Requirements - <suffix>`` sub-headings instead. Both
#: forms match here, and a later occurrence of this same pattern is
#: never treated as the section *terminator* (see the scan in
#: :func:`parse_requirements`) — it is a same-section sub-heading, not a
#: new top-level section, and round-tripping it correctly is what
#: SC-010's live-corpus test exists to catch.
_SECTION_HEADING_RE = re.compile(r"^### Functional Requirements(?:\s|$)")

#: Section terminator: the next ``## `` or ``### `` heading that is not
#: itself a Functional Requirements (sub-)heading. A bare ``#### ``
#: (4+ hashes) does NOT match either prefix, so in-block grouping
#: headings never terminate the section.
_SECTION_TERMINATOR_RE = re.compile(r"^(?:## |### )")

#: A requirement block's header line. All 1,139 requirement lines in the
#: corpus match this with zero exceptions.
_BLOCK_START_RE = re.compile(r"^- \*\*(FR-\d{3}[a-z]?)\*\*: ")

_REQ_ID_RE = re.compile(r"^FR-\d{3}[a-z]?$")

#: A body line belongs to the current block iff it is blank or indented
#: by at least two spaces. Corpus indent depth is only ever 0 or 2.
_BODY_LINE_RE = re.compile(r"^(?: {2,})|^\s*$")

#: Sub-bullet vs. continuation classification, within a block's body.
_SUB_BULLET_RE = re.compile(r"^\s*- ")


def _bare(line: str) -> str:
    """*line* with its trailing newline stripped, for regex matching."""
    return line[:-1] if line.endswith("\n") else line


class RequirementBlock(BaseModel):
    """One requirement as it appears in ``spec.md``.

    ``body_lines`` is the single source of truth for everything after the
    header: continuation prose, sub-bullets, and any blank lines that
    separate them or trail the block, all verbatim and in file order.
    ``continuation``/``sub_bullets``/``trailing_blanks`` are computed
    views over it rather than separately-stored fields — storing them
    separately would require reassembling file order from two buckets,
    which is exactly the kind of derived state that breaks round-trips
    the moment a corpus file interleaves them.
    """

    model_config = ConfigDict(frozen=True)

    req_id: str = Field(description="Validated FR-\\d{3}[a-z]?")
    header_line: str = Field(description="The '- **FR-NNN**: ...' line, verbatim")
    body_lines: tuple[str, ...] = Field(
        default=(), description="Continuation/sub-bullet/blank lines, verbatim, file order"
    )
    line_number: int = Field(ge=1, description="1-based, for error messages")

    @field_validator("req_id")
    @classmethod
    def _req_id_must_match_pattern(cls, v: str) -> str:
        if not _REQ_ID_RE.match(v):
            raise ValueError(f"req_id must match FR-\\d{{3}}[a-z]?, got: {v!r}")
        return v

    @property
    def continuation(self) -> tuple[str, ...]:
        """Non-blank, indent-2 lines that are not sub-bullets."""
        return tuple(
            line for line in self.body_lines if line.strip() and not _SUB_BULLET_RE.match(line)
        )

    @property
    def sub_bullets(self) -> tuple[str, ...]:
        """Non-blank, indent-2 lines starting with ``- ``."""
        return tuple(
            line for line in self.body_lines if line.strip() and _SUB_BULLET_RE.match(line)
        )

    @property
    def trailing_blanks(self) -> int:
        """Blank lines at the end of ``body_lines`` (before the next element)."""
        count = 0
        for line in reversed(self.body_lines):
            if line.strip():
                break
            count += 1
        return count

    @property
    def all_lines(self) -> tuple[str, ...]:
        """``header_line`` followed by every ``body_lines`` entry."""
        return (self.header_line, *self.body_lines)

    @property
    def normalized_length(self) -> int:
        """Whitespace-collapsed character count of the whole block.

        Used only by the content-loss guard (``speckit/delta/validate.py``);
        derived, never stored.
        """
        parts = [self.header_line.strip()]
        parts.extend(line.strip() for line in self.body_lines if line.strip())
        return len(" ".join(" ".join(parts).split()))

    def render(self) -> str:
        """Verbatim text for this block alone (no trailing section context)."""
        return "".join(self.all_lines)


class PassthroughLines(BaseModel):
    """Anything inside the section that is not a requirement block.

    Carries the ``####`` grouping headings, bold pseudo-headings, and
    blank runs between blocks — verbatim, re-emitted untouched.
    """

    model_config = ConfigDict(frozen=True)

    lines: tuple[str, ...] = Field(description="Verbatim lines, file order")
    start_line: int = Field(ge=1, description="1-based line of the first entry")


class RequirementSection(BaseModel):
    """The ``### Functional Requirements`` section of one ``spec.md``,
    plus enough surrounding context to round-trip the whole file.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str = Field(description="Verbatim text before heading_line")
    heading_line: str = Field(description="The '### Functional Requirements' line, verbatim")
    elements: tuple[RequirementBlock | PassthroughLines, ...] = Field(
        default=(), description="In file order"
    )
    suffix: str = Field(description="Verbatim text from the terminator (or EOF) onward")
    start_line: int = Field(ge=1, description="1-based line of heading_line")
    end_line: int = Field(ge=1, description="1-based line of the section's last line")

    def blocks(self) -> tuple[RequirementBlock, ...]:
        """Every :class:`RequirementBlock` in the section, file order."""
        return tuple(el for el in self.elements if isinstance(el, RequirementBlock))

    def block_by_id(self, req_id: str) -> RequirementBlock | None:
        for block in self.blocks():
            if block.req_id == req_id:
                return block
        return None


def _parse_elements(
    lines: list[str], *, base_line_number: int
) -> tuple[RequirementBlock | PassthroughLines, ...]:
    """Parse *lines* (the section body, after the heading) into elements.

    Args:
        lines: Raw lines (with line endings), the section body.
        base_line_number: 1-based absolute line number of ``lines[0]``.
    """
    elements: list[RequirementBlock | PassthroughLines] = []
    j = 0
    n = len(lines)
    while j < n:
        line = lines[j]
        bare = _bare(line)
        start_m = _BLOCK_START_RE.match(bare)
        if start_m:
            req_id = start_m.group(1)
            header_line = line
            header_line_no = base_line_number + j
            j += 1
            body: list[str] = []
            while j < n:
                nxt_bare = _bare(lines[j])
                if _BODY_LINE_RE.match(nxt_bare):
                    body.append(lines[j])
                    j += 1
                    continue
                break
            elements.append(
                RequirementBlock(
                    req_id=req_id,
                    header_line=header_line,
                    body_lines=tuple(body),
                    line_number=header_line_no,
                )
            )
            continue

        # Passthrough run: consume consecutive lines that are not a block start.
        start = j
        passthrough: list[str] = []
        while j < n:
            cur_bare = _bare(lines[j])
            if _BLOCK_START_RE.match(cur_bare):
                break
            passthrough.append(lines[j])
            j += 1
        elements.append(
            PassthroughLines(lines=tuple(passthrough), start_line=base_line_number + start)
        )

    return tuple(elements)


def parse_requirements(text: str, *, file: str = "spec.md") -> RequirementSection:
    """Parse the ``### Functional Requirements`` section out of *text*.

    Pure function — no I/O. Stores every line verbatim; the round-trip
    invariant (``render_requirements(parse_requirements(text)) == text``)
    depends on nothing here ever normalizing whitespace or reordering
    content.

    Args:
        text: Raw ``spec.md`` content.
        file: File path used in error messages.

    Returns:
        A :class:`RequirementSection`.

    Raises:
        SpeckitParseError: No ``### Functional Requirements`` heading found.
    """
    lines = text.splitlines(keepends=True)

    heading_idx: int | None = None
    for idx, line in enumerate(lines):
        if _SECTION_HEADING_RE.match(_bare(line)):
            heading_idx = idx
            break

    if heading_idx is None:
        raise SpeckitParseError(
            f"{file}: no '### Functional Requirements' heading found",
            file=file,
            line=1,
            expected="### Functional Requirements",
            suggestion="verify this file was generated by Spec Kit's specify template",
        )

    prefix = "".join(lines[:heading_idx])
    heading_line = lines[heading_idx]

    end_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        bare = _bare(lines[idx])
        if _SECTION_HEADING_RE.match(bare):
            # A same-section sub-heading (the 004-style split), not a
            # terminator — keep scanning.
            continue
        if _SECTION_TERMINATOR_RE.match(bare):
            end_idx = idx
            break

    body_lines = lines[heading_idx + 1 : end_idx]
    suffix = "".join(lines[end_idx:])

    elements = _parse_elements(body_lines, base_line_number=heading_idx + 2)

    return RequirementSection(
        prefix=prefix,
        heading_line=heading_line,
        elements=elements,
        suffix=suffix,
        start_line=heading_idx + 1,
        end_line=max(end_idx, heading_idx + 1),
    )


def render_requirements(section: RequirementSection) -> str:
    """Reproduce the complete original text of a parsed ``spec.md``.

    Args:
        section: A :class:`RequirementSection` from :func:`parse_requirements`.

    Returns:
        The verbatim original text — ``render_requirements(parse_requirements(text)) == text``.
    """
    parts: list[str] = [section.prefix, section.heading_line]
    for element in section.elements:
        if isinstance(element, RequirementBlock):
            parts.extend(element.all_lines)
        else:
            parts.extend(element.lines)
    parts.append(section.suffix)
    return "".join(parts)


def parse_single_block(
    text: str, *, line_number: int = 1, file: str = "<block>"
) -> RequirementBlock:
    """Parse a standalone requirement block (no surrounding section).

    Used by the delta layer to turn a ``### Before``/``### After`` body —
    a complete verbatim requirement block, per
    ``contracts/delta-document-format.md`` — into a structured
    :class:`RequirementBlock`, reusing the exact same grammar
    :func:`parse_requirements` applies inside a full ``spec.md``.

    Args:
        text: The block's raw text (header line plus any body lines),
            each line ending in ``\\n``.
        line_number: 1-based line number to report on the resulting
            block (typically the delta document's own line number for
            this entry, not a spec.md line).
        file: File path used in error messages.

    Returns:
        The single :class:`RequirementBlock` found in *text*.

    Raises:
        SpeckitParseError: *text* does not start with a requirement
            header line, or contains more than one.
    """
    lines = text.splitlines(keepends=True)
    elements = _parse_elements(lines, base_line_number=line_number)
    blocks = [el for el in elements if isinstance(el, RequirementBlock)]
    non_blank_passthrough = [
        el
        for el in elements
        if isinstance(el, PassthroughLines) and any(line.strip() for line in el.lines)
    ]
    if len(blocks) != 1 or non_blank_passthrough:
        raise SpeckitParseError(
            f"{file}: expected exactly one requirement block, found {len(blocks)}",
            file=file,
            line=line_number,
            expected="a single '- **FR-NNN**: ...' header plus its body, nothing else",
            suggestion="verify the block starts at column zero with '- **FR-NNN**: '",
        )
    block = blocks[0]
    return block.model_copy(update={"line_number": line_number})


__all__ = [
    "PassthroughLines",
    "RequirementBlock",
    "RequirementSection",
    "parse_requirements",
    "parse_single_block",
    "render_requirements",
]
