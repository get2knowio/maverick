"""RunwayStore: core read/write class for the runway knowledge store.

Handles JSONL append/read for episodic records, semantic file I/O,
index management, and BM25-based retrieval across all runway content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiofiles

from maverick.exceptions.runway import RunwayCorruptedError, RunwayNotInitializedError
from maverick.logging import get_logger
from maverick.runway.models import (
    BeadOutcome,
    FixAttemptRecord,
    RunwayIndex,
    RunwayPassage,
    RunwayQueryResult,
    RunwayReviewFinding,
    RunwayStatus,
)
from maverick.utils.atomic import atomic_write_json, atomic_write_text

__all__ = ["RunwayStore"]

logger = get_logger(__name__)

# Directory names within the runway root
_EPISODIC_DIR = "episodic"
_SEMANTIC_DIR = "semantic"
_INDEX_FILE = "index.json"

# JSONL file names
_BEAD_OUTCOMES_FILE = "bead-outcomes.jsonl"
_REVIEW_FINDINGS_FILE = "review-findings.jsonl"
_FIX_ATTEMPTS_FILE = "fix-attempts.jsonl"


class RunwayStore:
    """Read/write interface for the runway knowledge store.

    All methods are async (uses ``aiofiles`` for I/O). Constructor receives
    ``runway_path`` — no singleton, no global state.

    Args:
        runway_path: Root directory of the runway store (e.g.
            ``.maverick/runway/``).
    """

    def __init__(self, runway_path: Path) -> None:
        self._path = runway_path

    @property
    def path(self) -> Path:
        """Root path of the runway store."""
        return self._path

    @property
    def is_initialized(self) -> bool:
        """Check whether the runway directory structure exists."""
        return (
            self._path.is_dir()
            and (self._path / _EPISODIC_DIR).is_dir()
            and (self._path / _SEMANTIC_DIR).is_dir()
            and (self._path / _INDEX_FILE).is_file()
        )

    # -----------------------------------------------------------------
    # Initialization
    # -----------------------------------------------------------------

    async def initialize(self) -> None:
        """Create the runway directory structure and scaffold files.

        Safe to call multiple times — existing files are not overwritten.
        """
        episodic = self._path / _EPISODIC_DIR
        semantic = self._path / _SEMANTIC_DIR

        episodic.mkdir(parents=True, exist_ok=True)
        semantic.mkdir(parents=True, exist_ok=True)

        index_path = self._path / _INDEX_FILE
        if not index_path.exists():
            atomic_write_json(index_path, RunwayIndex().to_dict())

        # Touch episodic files so they exist for appending
        for fname in (_BEAD_OUTCOMES_FILE, _REVIEW_FINDINGS_FILE, _FIX_ATTEMPTS_FILE):
            fpath = episodic / fname
            if not fpath.exists():
                fpath.touch()

        # Place .gitkeep in semantic/ so git tracks the empty directory.
        # Without this, jj/git clones omit semantic/ and is_initialized
        # returns False in workspaces cloned from the user repo.
        gitkeep = semantic / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

        logger.info("runway_initialized", path=str(self._path))

    # -----------------------------------------------------------------
    # Episodic: Append
    # -----------------------------------------------------------------

    async def append_bead_outcome(self, outcome: BeadOutcome) -> None:
        """Append a bead outcome record to the JSONL file."""
        await self._append_jsonl(
            self._path / _EPISODIC_DIR / _BEAD_OUTCOMES_FILE,
            outcome.to_dict(),
        )

    async def append_review_finding(self, finding: RunwayReviewFinding) -> None:
        """Append a review finding record to the JSONL file."""
        await self._append_jsonl(
            self._path / _EPISODIC_DIR / _REVIEW_FINDINGS_FILE,
            finding.to_dict(),
        )

    async def append_fix_attempt(self, attempt: FixAttemptRecord) -> None:
        """Append a fix attempt record to the JSONL file."""
        await self._append_jsonl(
            self._path / _EPISODIC_DIR / _FIX_ATTEMPTS_FILE,
            attempt.to_dict(),
        )

    # -----------------------------------------------------------------
    # Episodic: Read + filter
    # -----------------------------------------------------------------

    async def get_bead_outcomes(
        self,
        *,
        bead_id: str | None = None,
        epic_id: str | None = None,
        limit: int | None = None,
    ) -> list[BeadOutcome]:
        """Read bead outcome records, optionally filtered.

        Args:
            bead_id: Filter by bead ID.
            epic_id: Filter by epic ID.
            limit: Maximum number of records to return.

        Returns:
            List of matching BeadOutcome records.
        """
        records = await self._read_jsonl(
            self._path / _EPISODIC_DIR / _BEAD_OUTCOMES_FILE
        )
        results: list[BeadOutcome] = []
        for raw in records:
            outcome = BeadOutcome.from_dict(raw)
            if bead_id is not None and outcome.bead_id != bead_id:
                continue
            if epic_id is not None and outcome.epic_id != epic_id:
                continue
            results.append(outcome)
        if limit is not None:
            results = results[-limit:]
        return results

    async def get_review_findings(
        self,
        *,
        bead_id: str | None = None,
        file_path: str | None = None,
        limit: int | None = None,
    ) -> list[RunwayReviewFinding]:
        """Read review finding records, optionally filtered.

        Args:
            bead_id: Filter by bead ID.
            file_path: Filter by file path.
            limit: Maximum number of records to return.

        Returns:
            List of matching RunwayReviewFinding records.
        """
        records = await self._read_jsonl(
            self._path / _EPISODIC_DIR / _REVIEW_FINDINGS_FILE
        )
        results: list[RunwayReviewFinding] = []
        for raw in records:
            finding = RunwayReviewFinding.from_dict(raw)
            if bead_id is not None and finding.bead_id != bead_id:
                continue
            if file_path is not None and finding.file_path != file_path:
                continue
            results.append(finding)
        if limit is not None:
            results = results[-limit:]
        return results

    async def get_fix_attempts(
        self,
        *,
        finding_id: str | None = None,
        bead_id: str | None = None,
    ) -> list[FixAttemptRecord]:
        """Read fix attempt records, optionally filtered.

        Args:
            finding_id: Filter by finding ID.
            bead_id: Filter by bead ID.

        Returns:
            List of matching FixAttemptRecord records.
        """
        records = await self._read_jsonl(
            self._path / _EPISODIC_DIR / _FIX_ATTEMPTS_FILE
        )
        results: list[FixAttemptRecord] = []
        for raw in records:
            attempt = FixAttemptRecord.from_dict(raw)
            if finding_id is not None and attempt.finding_id != finding_id:
                continue
            if bead_id is not None and attempt.bead_id != bead_id:
                continue
            results.append(attempt)
        return results

    # -----------------------------------------------------------------
    # Semantic files
    # -----------------------------------------------------------------

    async def read_semantic_file(self, name: str) -> str | None:
        """Read a semantic markdown file by name.

        Args:
            name: Filename (without directory prefix), e.g. "architecture.md".

        Returns:
            File contents as string, or None if file doesn't exist.
        """
        fpath = self._path / _SEMANTIC_DIR / name
        if not fpath.is_file():
            return None
        async with aiofiles.open(fpath, encoding="utf-8") as f:
            return await f.read()

    async def write_semantic_file(self, name: str, content: str) -> None:
        """Write a semantic markdown file.

        Args:
            name: Filename (without directory prefix), e.g. "architecture.md".
            content: Markdown content to write.
        """
        fpath = self._path / _SEMANTIC_DIR / name
        fpath.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
            await f.write(content)

    # -----------------------------------------------------------------
    # Index
    # -----------------------------------------------------------------

    async def read_index(self) -> RunwayIndex:
        """Read and parse the runway index.

        Returns:
            RunwayIndex parsed from index.json.

        Raises:
            RunwayNotInitializedError: If runway is not initialized.
            RunwayCorruptedError: If index.json cannot be parsed.
        """
        index_path = self._path / _INDEX_FILE
        if not index_path.is_file():
            raise RunwayNotInitializedError(str(self._path))
        try:
            async with aiofiles.open(index_path, encoding="utf-8") as f:
                raw = await f.read()
            data = json.loads(raw)
            return RunwayIndex.from_dict(data)
        except (json.JSONDecodeError, Exception) as exc:
            raise RunwayCorruptedError(str(self._path), f"index.json: {exc}") from exc

    async def write_index(self, index: RunwayIndex) -> None:
        """Write the runway index atomically.

        Args:
            index: RunwayIndex to write.
        """
        atomic_write_json(self._path / _INDEX_FILE, index.to_dict())

    # -----------------------------------------------------------------
    # Query (BM25)
    # -----------------------------------------------------------------

    async def query(
        self,
        query_text: str,
        *,
        max_passages: int = 10,
        bm25_top_k: int = 20,
    ) -> RunwayQueryResult:
        """Search across all runway files using BM25.

        Tokenizes all runway content into passages (markdown paragraphs,
        JSONL records), builds a BM25Okapi index per query, and returns
        ranked passages.

        Args:
            query_text: Search query text.
            max_passages: Maximum passages to return.
            bm25_top_k: Top-K candidates from BM25 before truncation.

        Returns:
            RunwayQueryResult with ranked passages.
        """
        passages = await self._collect_passages()
        if not passages:
            return RunwayQueryResult(passages=[], query=query_text, total_candidates=0)

        tokenized_corpus = [self._tokenize(p.content) for p in passages]
        query_tokens = self._tokenize(query_text)

        if not query_tokens:
            return RunwayQueryResult(
                passages=[], query=query_text, total_candidates=len(passages)
            )

        from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)

        # Pair passages with scores, sort descending
        scored = sorted(
            zip(scores, passages, strict=True), key=lambda x: x[0], reverse=True
        )[:bm25_top_k]

        # Include passages where query tokens appear in content.
        # BM25 on tiny corpora can produce negative scores for valid matches
        # (IDF penalizes terms appearing in all documents), so we use a
        # token-overlap fallback instead of a strict score threshold.
        query_set = set(query_tokens)
        result_passages = [
            RunwayPassage(
                source_file=p.source_file,
                content=p.content,
                score=float(s),
                line_start=p.line_start,
                line_end=p.line_end,
            )
            for s, p in scored
            if s > 0 or (query_set & set(self._tokenize(p.content)))
        ][:max_passages]

        return RunwayQueryResult(
            passages=result_passages,
            query=query_text,
            total_candidates=len(passages),
        )

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------

    async def get_status(self) -> RunwayStatus:
        """Get status summary of the runway store.

        Returns:
            RunwayStatus with counts, timestamps, and sizes.
        """
        if not self.is_initialized:
            return RunwayStatus(initialized=False)

        bead_count = await self._count_jsonl_lines(
            self._path / _EPISODIC_DIR / _BEAD_OUTCOMES_FILE
        )
        finding_count = await self._count_jsonl_lines(
            self._path / _EPISODIC_DIR / _REVIEW_FINDINGS_FILE
        )
        attempt_count = await self._count_jsonl_lines(
            self._path / _EPISODIC_DIR / _FIX_ATTEMPTS_FILE
        )

        semantic_dir = self._path / _SEMANTIC_DIR
        semantic_files = [
            f.name
            for f in sorted(semantic_dir.iterdir())
            if f.is_file() and f.name != ".gitkeep"
        ]

        total_size = sum(f.stat().st_size for f in self._path.rglob("*") if f.is_file())

        index = await self.read_index()

        return RunwayStatus(
            initialized=True,
            bead_outcome_count=bead_count,
            review_finding_count=finding_count,
            fix_attempt_count=attempt_count,
            semantic_files=semantic_files,
            total_size_bytes=total_size,
            last_consolidated=index.last_consolidated,
        )

    # -----------------------------------------------------------------
    # Episodic: Rewrite (for consolidation pruning)
    # -----------------------------------------------------------------

    async def rewrite_jsonl(self, path: Path, records: list[dict[str, Any]]) -> None:
        """Atomically rewrite a JSONL file with the given records.

        Used by consolidation to prune old episodic records after they have
        been distilled into semantic summaries.

        Args:
            path: JSONL file path to rewrite.
            records: Records to write (replaces entire file content).
        """
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        atomic_write_text(path, content)

    async def rewrite_bead_outcomes(self, outcomes: list[BeadOutcome]) -> None:
        """Rewrite the bead-outcomes JSONL file with the given records.

        Args:
            outcomes: BeadOutcome records to keep.
        """
        await self.rewrite_jsonl(
            self._path / _EPISODIC_DIR / _BEAD_OUTCOMES_FILE,
            [o.to_dict() for o in outcomes],
        )

    async def rewrite_review_findings(
        self, findings: list[RunwayReviewFinding]
    ) -> None:
        """Rewrite the review-findings JSONL file with the given records.

        Args:
            findings: RunwayReviewFinding records to keep.
        """
        await self.rewrite_jsonl(
            self._path / _EPISODIC_DIR / _REVIEW_FINDINGS_FILE,
            [f.to_dict() for f in findings],
        )

    async def rewrite_fix_attempts(self, attempts: list[FixAttemptRecord]) -> None:
        """Rewrite the fix-attempts JSONL file with the given records.

        Args:
            attempts: FixAttemptRecord records to keep.
        """
        await self.rewrite_jsonl(
            self._path / _EPISODIC_DIR / _FIX_ATTEMPTS_FILE,
            [a.to_dict() for a in attempts],
        )

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    async def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        """Append a single JSON line to a JSONL file."""
        line = json.dumps(record, ensure_ascii=False) + "\n"
        async with aiofiles.open(path, "a", encoding="utf-8") as f:
            await f.write(line)

    async def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        """Read all records from a JSONL file.

        Returns:
            List of parsed JSON objects. Silently skips malformed lines.
        """
        if not path.is_file():
            return []
        records: list[dict[str, Any]] = []
        async with aiofiles.open(path, encoding="utf-8") as f:
            async for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    records.append(json.loads(stripped))
                except json.JSONDecodeError:
                    logger.warning(
                        "runway_jsonl_parse_error",
                        file=str(path),
                        line=stripped[:100],
                    )
        return records

    async def _count_jsonl_lines(self, path: Path) -> int:
        """Count non-empty lines in a JSONL file."""
        if not path.is_file():
            return 0
        count = 0
        async with aiofiles.open(path, encoding="utf-8") as f:
            async for line in f:
                if line.strip():
                    count += 1
        return count

    async def _collect_passages(self) -> list[RunwayPassage]:
        """Collect all passages from runway files for BM25 indexing.

        Markdown files are split by paragraphs. JSONL records become
        individual passages.
        """
        passages: list[RunwayPassage] = []

        # Semantic markdown files
        semantic_dir = self._path / _SEMANTIC_DIR
        if semantic_dir.is_dir():
            for fpath in sorted(semantic_dir.iterdir()):
                if fpath.is_file() and fpath.suffix == ".md":
                    async with aiofiles.open(fpath, encoding="utf-8") as f:
                        content = await f.read()
                    rel = str(fpath.relative_to(self._path))
                    passages.extend(self._split_markdown(content, rel))

        # Episodic JSONL files
        episodic_dir = self._path / _EPISODIC_DIR
        if episodic_dir.is_dir():
            for fpath in sorted(episodic_dir.iterdir()):
                if fpath.is_file() and fpath.suffix == ".jsonl":
                    records = await self._read_jsonl(fpath)
                    rel = str(fpath.relative_to(self._path))
                    for i, rec in enumerate(records):
                        passages.append(
                            RunwayPassage(
                                source_file=rel,
                                content=json.dumps(rec, ensure_ascii=False),
                                score=0.0,
                                line_start=i + 1,
                                line_end=i + 1,
                            )
                        )

        return passages

    @staticmethod
    def _split_markdown(content: str, source_file: str) -> list[RunwayPassage]:
        """Split markdown content into paragraph-level passages."""
        passages: list[RunwayPassage] = []
        lines = content.split("\n")
        current_block: list[str] = []
        block_start = 1

        for i, line in enumerate(lines, start=1):
            if line.strip() == "" and current_block:
                text = "\n".join(current_block).strip()
                if text:
                    passages.append(
                        RunwayPassage(
                            source_file=source_file,
                            content=text,
                            score=0.0,
                            line_start=block_start,
                            line_end=i - 1,
                        )
                    )
                current_block = []
                block_start = i + 1
            else:
                if not current_block:
                    block_start = i
                current_block.append(line)

        # Final block
        if current_block:
            text = "\n".join(current_block).strip()
            if text:
                passages.append(
                    RunwayPassage(
                        source_file=source_file,
                        content=text,
                        score=0.0,
                        line_start=block_start,
                        line_end=len(lines),
                    )
                )

        return passages

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + lowercase tokenizer for BM25.

        Strips JSON punctuation (quotes, braces, colons, commas) so that
        JSONL content is searchable alongside prose.
        """
        import re

        # Remove JSON structural chars and common punctuation
        cleaned = re.sub(r'[{}\[\]":,]', " ", text.lower())
        return [token for token in cleaned.split() if len(token) > 1]
