"""Tests for the hashed briefing/outline cache key helpers.

The workflow reads caches from ``.maverick/plans/<name>/`` and the
supervisor writes them via ``RefuelSupervisor._cache_*`` methods. Both
sides agree on a sha256-based ``cache_key`` so stale caches are
invalidated instead of silently misapplied.

These tests cover the pure key-derivation helpers. Supervisor-side
cache-write behaviour is tested in
``tests/unit/actors/xoscar_runtime/test_refuel_cache_writes.py``.
"""

from __future__ import annotations

from maverick.workflows.refuel_maverick.workflow import (
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
