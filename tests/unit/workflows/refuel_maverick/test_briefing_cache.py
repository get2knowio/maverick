"""Tests for the hashed briefing/outline cache envelopes (REFUEL_ISSUES #5).

The workflow reads caches from .maverick/plans/<name>/ and the supervisor
writes them. Both sides agree on a sha256-based ``cache_key`` so stale
caches are invalidated instead of silently misapplied.

These tests cover the pure helpers and the envelope schema — they do
NOT exercise the Thespian path, which is covered by the broader
workflow tests.
"""

from __future__ import annotations

import json

import maverick.actors.refuel_supervisor as refuel_supervisor_module
from maverick.workflows.refuel_maverick.workflow import (
    BRIEFING_CACHE_SCHEMA_VERSION,
    OUTLINE_CACHE_SCHEMA_VERSION,
    _briefing_cache_key,
    _outline_cache_key,
)


class TestBriefingCacheKey:
    def test_identical_inputs_produce_identical_keys(self) -> None:
        a = _briefing_cache_key("fp", {"files": ["a.py"]}, "prompt")
        b = _briefing_cache_key("fp", {"files": ["a.py"]}, "prompt")
        assert a == b

    def test_flight_plan_change_changes_key(self) -> None:
        a = _briefing_cache_key("fp1", {"files": ["a.py"]}, "prompt")
        b = _briefing_cache_key("fp2", {"files": ["a.py"]}, "prompt")
        assert a != b

    def test_codebase_context_change_changes_key(self) -> None:
        a = _briefing_cache_key("fp", {"files": ["a.py"]}, "prompt")
        b = _briefing_cache_key("fp", {"files": ["b.py"]}, "prompt")
        assert a != b

    def test_prompt_change_changes_key(self) -> None:
        a = _briefing_cache_key("fp", {"files": ["a.py"]}, "prompt-v1")
        b = _briefing_cache_key("fp", {"files": ["a.py"]}, "prompt-v2")
        assert a != b


class TestOutlineCacheKey:
    def test_identical_inputs_produce_identical_keys(self) -> None:
        a = _outline_cache_key("fp", "props", {"navigator": {"x": 1}})
        b = _outline_cache_key("fp", "props", {"navigator": {"x": 1}})
        assert a == b

    def test_briefing_change_changes_key(self) -> None:
        a = _outline_cache_key("fp", "props", {"navigator": {"x": 1}})
        b = _outline_cache_key("fp", "props", {"navigator": {"x": 2}})
        assert a != b

    def test_missing_briefing_is_stable(self) -> None:
        a = _outline_cache_key("fp", "props", None)
        b = _outline_cache_key("fp", "props", {})
        assert a == b


class TestSupervisorBriefingCacheWrite:
    def test_writes_envelope_with_key(self, tmp_path) -> None:
        cache_path = tmp_path / "refuel-briefing.json"

        sup = object.__new__(refuel_supervisor_module.RefuelSupervisorActor)
        sup._briefing_cache_path = str(cache_path)
        sup._briefing_cache_key = "deadbeef12345678"
        sup._briefing_cache_schema_version = BRIEFING_CACHE_SCHEMA_VERSION
        sup._briefing_results = {"navigator": object()}  # truthy sentinel
        sup._initial_payload = {
            "briefing": {"navigator": {"summary": "ok"}},
        }

        sup._cache_briefing_results()

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == BRIEFING_CACHE_SCHEMA_VERSION
        assert data["cache_key"] == "deadbeef12345678"
        assert data["payloads"] == {"navigator": {"summary": "ok"}}

    def test_overwrites_existing_cache(self, tmp_path) -> None:
        cache_path = tmp_path / "refuel-briefing.json"
        cache_path.write_text(
            json.dumps({"schema_version": 1, "cache_key": "old", "payloads": {}}),
            encoding="utf-8",
        )

        sup = object.__new__(refuel_supervisor_module.RefuelSupervisorActor)
        sup._briefing_cache_path = str(cache_path)
        sup._briefing_cache_key = "new-key-value"
        sup._briefing_cache_schema_version = BRIEFING_CACHE_SCHEMA_VERSION
        sup._briefing_results = {"navigator": object()}
        sup._initial_payload = {"briefing": {"navigator": {}}}

        sup._cache_briefing_results()

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["cache_key"] == "new-key-value"


class TestSupervisorOutlineCacheWrite:
    def test_writes_envelope_with_computed_key(self, tmp_path) -> None:
        cache_path = tmp_path / "refuel-outline.json"

        class _Outline:
            work_units = ()  # just needs __len__

            def to_dict(self):
                return {"work_units": []}

        sup = object.__new__(refuel_supervisor_module.RefuelSupervisorActor)
        sup._outline_cache_path = str(cache_path)
        sup._outline_cache_key_inputs = {
            "flight_plan_content": "fp",
            "verification_properties": "props",
        }
        sup._outline_cache_schema_version = OUTLINE_CACHE_SCHEMA_VERSION
        sup._outline = _Outline()
        sup._initial_payload = {"briefing": {"navigator": {"x": 1}}}
        sup._outline_payload = lambda: {"work_units": []}  # type: ignore[assignment]

        sup._cache_outline()

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == OUTLINE_CACHE_SCHEMA_VERSION
        assert data["payload"] == {"work_units": []}
        # Recomputing the key with the same inputs must match what the
        # supervisor wrote.
        expected = _outline_cache_key("fp", "props", {"navigator": {"x": 1}})
        assert data["cache_key"] == expected
