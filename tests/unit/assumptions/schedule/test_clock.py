"""Tests for ``maverick.assumptions.schedule.clock`` — IANA local-zone resolution.

These cover the DST-correctness contract behind research R6: the evaluation
clock injected at the CLI boundary must carry a *real* zone (whose UTC offset
varies across a DST transition), not the fixed-offset ``timezone`` that
``datetime.now().astimezone()`` produces.

Every source (``TZ``, ``/etc/localtime``, ``/etc/timezone``) is stubbed, so no
assertion depends on the timezone the CI machine happens to be configured for.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from maverick.assumptions.schedule import clock

#: A zone with a well-known DST transition (2026-03-08 02:00 local).
_DST_ZONE = "America/New_York"


def _tzdata_available() -> bool:
    """Whether the tz database can be queried at all on this machine."""
    try:
        ZoneInfo(_DST_ZONE)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


#: Tests that need a real zone to exist; everything else (fall-through,
#: fixed-offset degradation) runs regardless of the machine's tz database.
requires_tzdata = pytest.mark.skipif(
    not _tzdata_available(), reason="tz database unavailable on this machine"
)


def _zoneinfo_root() -> Path:
    """Return the system zoneinfo directory, skipping if unavailable."""
    root = Path("/usr/share/zoneinfo")
    if not (root / _DST_ZONE).exists():
        pytest.skip("system zoneinfo directory not available")
    return root


@pytest.fixture(autouse=True)
def _isolate_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every resolution source at nothing, so each test opts in explicitly."""
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(clock, "_LOCALTIME_PATH", tmp_path / "missing-localtime")
    monkeypatch.setattr(clock, "_TIMEZONE_FILE_PATH", tmp_path / "missing-timezone")


@requires_tzdata
class TestTzEnvironmentVariable:
    def test_resolves_zone_named_by_tz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", _DST_ZONE)

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE

    def test_strips_posix_leading_colon(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", f":{_DST_ZONE}")

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE

    def test_unknown_tz_value_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", "Not/AZone")

        tz = clock.local_timezone()

        assert not isinstance(tz, ZoneInfo)

    def test_posix_offset_string_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # "EST5EDT" is a legal POSIX TZ spelling that also happens to be a
        # zoneinfo key on most systems; "<+07>-7" is not a key anywhere.
        monkeypatch.setenv("TZ", "<+07>-7")

        tz = clock.local_timezone()

        assert not isinstance(tz, ZoneInfo)

    def test_empty_tz_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", "")

        tz = clock.local_timezone()

        assert not isinstance(tz, ZoneInfo)


@requires_tzdata
class TestLocaltimeSymlink:
    def test_resolves_zone_from_symlink_target(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        target = _zoneinfo_root() / _DST_ZONE
        link = tmp_path / "localtime"
        link.symlink_to(target)
        monkeypatch.setattr(clock, "_LOCALTIME_PATH", link)

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE

    def test_resolves_relative_symlink_target(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Mirrors distros that ship /etc/localtime -> ../usr/share/zoneinfo/...
        zone_dir = tmp_path / "usr" / "share" / "zoneinfo" / "America"
        zone_dir.mkdir(parents=True)
        (zone_dir / "New_York").write_bytes(b"TZif")
        etc = tmp_path / "etc"
        etc.mkdir()
        link = etc / "localtime"
        link.symlink_to(Path("..") / "usr" / "share" / "zoneinfo" / "America" / "New_York")
        monkeypatch.setattr(clock, "_LOCALTIME_PATH", link)

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE

    def test_tz_env_wins_over_symlink(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        link = tmp_path / "localtime"
        link.symlink_to(_zoneinfo_root() / "Europe" / "Berlin")
        monkeypatch.setattr(clock, "_LOCALTIME_PATH", link)
        monkeypatch.setenv("TZ", _DST_ZONE)

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE

    def test_plain_file_without_zoneinfo_component_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        copied = tmp_path / "localtime"
        copied.write_bytes(b"TZif2")
        monkeypatch.setattr(clock, "_LOCALTIME_PATH", copied)

        tz = clock.local_timezone()

        assert not isinstance(tz, ZoneInfo)


@requires_tzdata
class TestTimezoneFile:
    def test_resolves_zone_from_etc_timezone(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tz_file = tmp_path / "timezone"
        tz_file.write_text(f"{_DST_ZONE}\n")
        monkeypatch.setattr(clock, "_TIMEZONE_FILE_PATH", tz_file)

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE

    def test_garbage_contents_fall_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tz_file = tmp_path / "timezone"
        tz_file.write_text("# nothing useful here\n")
        monkeypatch.setattr(clock, "_TIMEZONE_FILE_PATH", tz_file)

        tz = clock.local_timezone()

        assert not isinstance(tz, ZoneInfo)

    def test_symlink_wins_over_timezone_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        link = tmp_path / "localtime"
        link.symlink_to(_zoneinfo_root() / _DST_ZONE)
        monkeypatch.setattr(clock, "_LOCALTIME_PATH", link)
        tz_file = tmp_path / "timezone"
        tz_file.write_text("Europe/Berlin\n")
        monkeypatch.setattr(clock, "_TIMEZONE_FILE_PATH", tz_file)

        tz = clock.local_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == _DST_ZONE


class TestFallback:
    def test_unresolvable_degrades_to_fixed_offset(self) -> None:
        tz = clock.local_timezone()

        assert not isinstance(tz, ZoneInfo)
        assert isinstance(tz, timezone)

    def test_unresolvable_now_local_is_aware(self) -> None:
        now = clock.now_local()

        assert now.tzinfo is not None
        assert now.utcoffset() is not None

    def test_degradation_is_logged_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events: list[tuple[str, dict[str, object]]] = []

        class _Recorder:
            def warning(self, event: str, **kwargs: object) -> None:
                events.append((event, kwargs))

        monkeypatch.setattr(clock, "_degradation_logged", False)
        monkeypatch.setattr(clock, "logger", _Recorder())

        clock.local_timezone()
        clock.local_timezone()

        assert len(events) == 1
        assert events[0][0] == "local_timezone_unresolved"

    @requires_tzdata
    def test_resolved_zone_logs_no_degradation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events: list[str] = []

        class _Recorder:
            def warning(self, event: str, **kwargs: object) -> None:
                events.append(event)

        monkeypatch.setattr(clock, "_degradation_logged", False)
        monkeypatch.setattr(clock, "logger", _Recorder())
        monkeypatch.setenv("TZ", _DST_ZONE)

        clock.local_timezone()

        assert events == []


class TestDstAwareness:
    """The regression this module exists for: a resolvable zone must yield a
    *different* UTC offset on either side of a DST transition."""

    @requires_tzdata
    def test_offset_differs_across_dst_boundary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", _DST_ZONE)

        tz = clock.local_timezone()

        before = datetime(2026, 3, 7, 10, 0, tzinfo=tz)  # EST (UTC-5)
        after = datetime(2026, 3, 9, 10, 0, tzinfo=tz)  # EDT (UTC-4)
        assert before.utcoffset() != after.utcoffset()

    def test_fixed_offset_fallback_cannot_vary(self) -> None:
        tz = clock.local_timezone()

        before = datetime(2026, 3, 7, 10, 0, tzinfo=tz)
        after = datetime(2026, 3, 9, 10, 0, tzinfo=tz)
        assert before.utcoffset() == after.utcoffset()


@requires_tzdata
class TestNowLocal:
    def test_carries_resolved_zone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", _DST_ZONE)

        now = clock.now_local()

        assert isinstance(now.tzinfo, ZoneInfo)
        assert now.tzinfo.key == _DST_ZONE

    def test_matches_wall_clock_instant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TZ", _DST_ZONE)

        before = datetime.now(tz=ZoneInfo(_DST_ZONE))
        now = clock.now_local()
        after = datetime.now(tz=ZoneInfo(_DST_ZONE))

        assert before <= now <= after
