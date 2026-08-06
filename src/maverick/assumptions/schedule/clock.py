"""The evaluation clock for the assumption batch scheduler (``maverick notify``).

``assumptions.schedule`` windows and quiet hours are *machine-local wall
clock* (contracts/config-schema.md), and
:func:`maverick.assumptions.schedule.evaluate.evaluate` reuses the ``tzinfo``
of the ``now`` it is handed to build every window occurrence it considers —
including occurrences on dates other than today (yesterday's catch-up, a
rolled-forward window). That only produces correct wall-clock times if the
``tzinfo`` is a real IANA zone: ``datetime.now().astimezone()`` returns a
*fixed-offset* :class:`datetime.timezone` frozen at today's offset, so an
occurrence on the far side of a DST transition comes out shifted by the DST
delta (in ``America/New_York``, evaluating at 10:00 EDT on 2026-03-08 would
build 2026-03-07's occurrence with UTC-4 when that date was UTC-5).

This module resolves the machine's real IANA zone with the standard library
only — no ``tzlocal`` dependency — in the order:

1. the ``TZ`` environment variable, when it names a zone :class:`ZoneInfo`
   accepts (POSIX offset spellings such as ``EST5EDT`` or ``<+07>-7`` do not
   and fall through);
2. the ``/etc/localtime`` symlink target, mapped back to a zone key by taking
   the path tail after its ``zoneinfo`` component;
3. the contents of ``/etc/timezone`` (Debian family).

When none resolve — a distro that ships ``/etc/localtime`` as a plain copy
with no ``/etc/timezone``, a container with no tz database — resolution
*degrades* to the historical fixed-offset behaviour rather than raising, and
logs that once per process. A fixed offset is still a correct instant; only
cross-DST wall-clock arithmetic loses fidelity, which is strictly better than
refusing to notify at all.
"""

from __future__ import annotations

import os
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from maverick.logging import get_logger

__all__ = ["local_timezone", "now_local", "resolve_local_zone"]

logger = get_logger(__name__)

#: The symlink every systemd-era distro points at the active zone's tzfile.
#: Module-level so tests can redirect it without touching the real ``/etc``.
_LOCALTIME_PATH: Final = Path("/etc/localtime")

#: Debian-family plain-text zone key (e.g. ``America/New_York\n``).
_TIMEZONE_FILE_PATH: Final = Path("/etc/timezone")

#: The path component that separates the tz-database root from the zone key.
_ZONEINFO_DIR_NAME: Final = "zoneinfo"

#: Whether this process has already reported a failed zone resolution. The
#: degradation is a property of the machine, not of the call, so repeating it
#: on every :func:`local_timezone` call would be pure noise.
_degradation_logged = False


def _zone_or_none(key: str) -> ZoneInfo | None:
    """Return :class:`ZoneInfo` for *key*, or ``None`` if it names no zone.

    Args:
        key: A candidate IANA zone key (e.g. ``"America/New_York"``).

    Returns:
        The constructed zone, or ``None`` when *key* is empty, malformed, or
        absent from the tz database.
    """
    if not key:
        return None
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def _zone_from_env() -> ZoneInfo | None:
    """Resolve the zone named by ``TZ``, if it names one.

    A leading ``":"`` is legal POSIX (``TZ=:America/New_York``) and is
    stripped before lookup. POSIX offset specs (``EST5EDT``, ``<+07>-7``)
    that are not also zone keys resolve to ``None``.
    """
    raw = os.environ.get("TZ")
    if raw is None:
        return None
    return _zone_or_none(raw.strip().lstrip(":"))


def _zone_key_from_path(path: Path) -> str | None:
    """Map a tzfile path back to its zone key.

    Args:
        path: An absolute path such as
            ``/usr/share/zoneinfo/America/New_York``.

    Returns:
        The path tail after the last ``zoneinfo`` component
        (``"America/New_York"``), or ``None`` when the path has no such
        component — the case when ``/etc/localtime`` is a plain copy of a
        tzfile rather than a symlink into the database.
    """
    parts = path.parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == _ZONEINFO_DIR_NAME:
            tail = parts[index + 1 :]
            return "/".join(tail) if tail else None
    return None


def _zone_from_localtime_symlink() -> ZoneInfo | None:
    """Resolve the zone ``/etc/localtime`` points at, if it is a symlink."""
    path = _LOCALTIME_PATH
    try:
        if not path.is_symlink():
            return None
        target = path.resolve()
    except OSError:
        return None
    key = _zone_key_from_path(target)
    return _zone_or_none(key) if key is not None else None


def _zone_from_timezone_file() -> ZoneInfo | None:
    """Resolve the zone named by ``/etc/timezone`` (Debian family)."""
    try:
        contents = _TIMEZONE_FILE_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in contents.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#"):
            return _zone_or_none(candidate)
    return None


def resolve_local_zone() -> ZoneInfo | None:
    """Resolve the machine's local IANA timezone.

    Returns:
        The machine's zone as a :class:`zoneinfo.ZoneInfo`, or ``None`` when
        no source (``TZ``, ``/etc/localtime``, ``/etc/timezone``) names a zone
        the tz database knows. Never raises.
    """
    for source in (_zone_from_env, _zone_from_localtime_symlink, _zone_from_timezone_file):
        zone = source()
        if zone is not None:
            return zone
    return None


def local_timezone() -> tzinfo:
    """Return the timezone to bind the evaluation clock to.

    Returns:
        The machine's IANA zone when resolvable — DST-aware, so wall-clock
        arithmetic on any date is correct — otherwise the fixed-offset
        :class:`datetime.timezone` of the current moment, which is the
        historical behaviour and is logged once per process as a degradation.
    """
    global _degradation_logged

    zone = resolve_local_zone()
    if zone is not None:
        return zone

    fallback = datetime.now().astimezone().tzinfo
    assert fallback is not None  # astimezone() always yields an aware datetime
    if not _degradation_logged:
        _degradation_logged = True
        logger.warning(
            "local_timezone_unresolved",
            fallback_offset=str(fallback),
            detail=(
                "could not resolve an IANA local timezone from TZ, "
                "/etc/localtime, or /etc/timezone; falling back to a "
                "fixed UTC offset (wall-clock times across a DST "
                "transition may be off by the DST delta)"
            ),
        )
    return fallback


def now_local() -> datetime:
    """Return the current time as an aware datetime in the machine's local zone.

    This is the injected clock seam (research R6) every ``maverick notify``
    evaluation is driven from: the CLI boundary calls it once and passes the
    result to :func:`~maverick.assumptions.schedule.evaluate.evaluate`, which
    reuses its ``tzinfo`` for every window occurrence it builds.

    Returns:
        ``datetime.now()`` bound to :func:`local_timezone`'s result — always
        aware, never naive.
    """
    return datetime.now(tz=local_timezone())
