"""Pure, deterministic text-matching for learned assumption resolution.

Implements the normative matching formula from
``specs/055-learned-assumption-resolution/contracts/decision-records.md``:
normalized-text similarity via stdlib ``difflib.SequenceMatcher`` blended
with token-set Jaccard similarity, a rejection-feedback penalty fold, and a
deterministic best-candidate selector.

This module is pure and synchronous: no I/O, no model calls, no third-party
dependencies beyond the standard library (``difflib``, ``re``, ``string``).
Callers own corpus preparation (collapsing records, self-match exclusion)
and persistence; this module only scores and selects.

``PRESENTATION_THRESHOLD`` and ``REJECTION_PENALTY`` are contract constants,
not tuning knobs — see the contract doc for the derivation. Changing either
value, or the 50/50 blend weights in :func:`base_score`, is a contract
change, not a tuning adjustment.
"""

from __future__ import annotations

import string
from difflib import SequenceMatcher
from typing import Final, NamedTuple, TypeVar

__all__ = [
    "PRESENTATION_THRESHOLD",
    "REJECTION_PENALTY",
    "ScoredCandidate",
    "base_score",
    "effective_confidence",
    "normalize_question",
    "select_best",
]

#: Minimum effective confidence required to present a suggestion (FR-015).
#: Built-in and fixed — not configurable. See contract doc for derivation.
PRESENTATION_THRESHOLD: Final[float] = 0.75

#: Per-net-rejection deduction applied to a pairing's base score. Sized so
#: that a single net rejection suppresses even an exact match: the maximum
#: possible base score is 1.0, and 1.0 - 0.30 = 0.70 < PRESENTATION_THRESHOLD.
REJECTION_PENALTY: Final[float] = 0.30

#: Translation table dropping every ASCII punctuation character.
_PUNCTUATION_TABLE: Final[dict[int, int | None]] = str.maketrans("", "", string.punctuation)

#: Minimum token length retained by :func:`_tokenize` (mirrors the runway
#: store's ``_tokenize`` convention of dropping single-character tokens).
_MIN_TOKEN_LENGTH: Final[int] = 2

T = TypeVar("T")


class ScoredCandidate(NamedTuple):
    """One candidate in a best-match selection pool.

    Attributes:
        confidence: Effective confidence score for this pairing, already
            penalty-adjusted (see :func:`effective_confidence`).
        resolved_at: ISO timestamp string of when the candidate's underlying
            decision was resolved. Used as a tie-break (descending).
        source_entry_id: Stable identity of the candidate's originating
            ledger entry. Used as the final tie-break (ascending).
        payload: Arbitrary caller-owned value carried through selection
            unchanged (e.g. the full suggestion record).
    """

    confidence: float
    resolved_at: str
    source_entry_id: str
    payload: object


def normalize_question(text: str) -> str:
    """Normalize question text for matching.

    Applies casefold, strips ASCII punctuation, and collapses whitespace
    (including leading/trailing) to single spaces. This is the exact
    normalization referenced throughout the matching contract.

    Args:
        text: Raw question text.

    Returns:
        Normalized text: casefolded, punctuation-free, whitespace-collapsed.
    """
    folded = text.casefold()
    stripped = folded.translate(_PUNCTUATION_TABLE)
    return " ".join(stripped.split())


def _tokenize(normalized_text: str) -> set[str]:
    """Split already-normalized text into a token set, dropping short tokens.

    Args:
        normalized_text: Text already passed through :func:`normalize_question`.

    Returns:
        Set of whitespace-delimited tokens with length > 1.
    """
    return {t for t in normalized_text.split() if len(t) >= _MIN_TOKEN_LENGTH}


def base_score(a: str, b: str) -> float:
    """Compute the corpus-independent base similarity score for two questions.

    Both inputs are normalized internally via :func:`normalize_question`, so
    callers may pass raw, un-normalized text.

    The score is a 50/50 blend of ``difflib.SequenceMatcher`` phrasing
    similarity and token-set Jaccard vocabulary overlap:

        base(a, b) = 0.5 * SequenceMatcher(None, na, nb).ratio()
                   + 0.5 * |tokens(na) & tokens(nb)| / |tokens(na) | tokens(nb)|

    The Jaccard term is defined as 0 when both token sets are empty (guards
    the divide-by-zero that would otherwise occur).

    Args:
        a: First question text (raw or normalized).
        b: Second question text (raw or normalized).

    Returns:
        Blended similarity score in [0, 1]. Deterministic for identical
        inputs; symmetric in ``a``/``b``.
    """
    na = normalize_question(a)
    nb = normalize_question(b)

    sequence_ratio = SequenceMatcher(None, na, nb).ratio()

    tokens_a = _tokenize(na)
    tokens_b = _tokenize(nb)
    union = tokens_a | tokens_b
    jaccard = len(tokens_a & tokens_b) / len(union) if union else 0.0

    return 0.5 * sequence_ratio + 0.5 * jaccard


def effective_confidence(base: float, *, rejections: int, acceptances: int) -> float:
    """Fold rejection feedback into a base score to get effective confidence.

    Implements ``effective = base - REJECTION_PENALTY * max(0, rejections - acceptances)``:
    each net rejection (rejections in excess of acceptances) deducts
    ``REJECTION_PENALTY`` from the base score; net-zero or net-positive
    acceptance history leaves the base score unchanged (no bonus above base).

    Args:
        base: Base similarity score for the pairing, typically from
            :func:`base_score`.
        rejections: Count of prior "rejected" feedback outcomes for this
            pairing.
        acceptances: Count of prior "accepted" feedback outcomes for this
            pairing.

    Returns:
        Effective confidence score. Not clamped to [0, 1] — callers compare
        against :data:`PRESENTATION_THRESHOLD`, where negative values simply
        fail the threshold.
    """
    net_rejections = max(0, rejections - acceptances)
    return base - REJECTION_PENALTY * net_rejections


def select_best(
    candidates: list[tuple[float, str, str, T]],
) -> tuple[float, str, str, T] | None:
    """Deterministically select the best candidate from a scored pool.

    Filters candidates to those with ``confidence >= PRESENTATION_THRESHOLD``,
    then picks the maximum by (``confidence`` descending, ``resolved_at``
    descending, ``source_entry_id`` ascending).

    Args:
        candidates: Iterable of ``(confidence, resolved_at, source_entry_id,
            payload)`` tuples. ``resolved_at`` is expected to be an
            ISO-8601 timestamp string (lexical ordering matches chronological
            ordering for that format); ``source_entry_id`` is any
            lexically-ordered identifier.

    Returns:
        The winning tuple unchanged, or ``None`` if no candidate meets
        :data:`PRESENTATION_THRESHOLD` (including an empty input).
    """
    eligible = [c for c in candidates if c[0] >= PRESENTATION_THRESHOLD]
    if not eligible:
        return None

    # Two fields (confidence, resolved_at) sort descending, one
    # (source_entry_id) sorts ascending — a single sort key can't mix
    # directions, so select via explicit pairwise reduction instead.
    best = eligible[0]
    for candidate in eligible[1:]:
        if _is_better(candidate, best):
            best = candidate
    return best


def _is_better(
    candidate: tuple[float, str, str, T], current_best: tuple[float, str, str, T]
) -> bool:
    """Return True if ``candidate`` outranks ``current_best`` under the tie-break order."""
    c_confidence, c_resolved_at, c_source_id, _ = candidate
    b_confidence, b_resolved_at, b_source_id, _ = current_best

    if c_confidence != b_confidence:
        return c_confidence > b_confidence
    if c_resolved_at != b_resolved_at:
        return c_resolved_at > b_resolved_at
    return c_source_id < b_source_id
