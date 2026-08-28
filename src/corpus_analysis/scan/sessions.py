"""Session enumeration, time bucketing, and self-exclusion.

Sessions are bucketed by their FIRST recorded timestamp, never by file mtime.
mtime moves when a session is resumed, when a backup is written, and when a
sync tool touches the file — none of which is when the work happened.

A session that starts inside one window and runs past its end belongs to the
window it started in. That is what makes a session countable at all; splitting
it would put one session in two buckets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..adapters import SessionRef


@dataclass(frozen=True, slots=True)
class SessionMeta:
    """A located session with the two facts needed to filter it."""

    ref: SessionRef
    first_ts: str
    cwd: str
    excluded: bool = False
    reason: str = ""


def parse_when(s: str | None) -> datetime | None:
    """An ISO time, a bare date, or a relative age such as `5h`, `30m`, `7d`.

    A value with no timezone is read as LOCAL time, because that is the clock
    the operator typed it off. Transcripts record UTC, so reading a bare date as
    UTC returns an empty window on any machine west of Greenwich — and an empty
    result is indistinguishable from a window in which nothing ran.
    """
    if not s:
        return None
    m = re.fullmatch(r"(\d+)([mhd])", s.strip())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n),
                 "d": timedelta(days=n)}[unit]
        return datetime.now(timezone.utc) - delta
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(
            f"unparseable time {s!r}: expected ISO, a date, or 5h/30m/2d"
        ) from e
    return dt if dt.tzinfo else dt.astimezone()


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def meta(adapter, ref: SessionRef) -> SessionMeta:
    """First timestamp and working directory, read with an early exit.

    An adapter whose store already holds both answers them directly: a session
    row carries its creation time, and walking every message to rediscover it
    would make enumeration cost a full parse of the corpus.

    A format with no working-directory concept sets `records_cwd = False` and
    takes the same path. Requiring a non-empty `cwd` would otherwise hold that
    adapter to a field its vendor never records, and the only way to satisfy it
    would be to invent one.
    """
    cwd = ref.cwd
    fast = getattr(adapter, "first_ts", None)
    if fast is not None and (cwd or not getattr(adapter, "records_cwd", True)):
        return SessionMeta(ref, fast(ref), cwd)

    first_ts = ""
    for turn in adapter.turns(ref):
        if not first_ts and turn.ts:
            first_ts = turn.ts
        if not cwd and turn.cwd:
            cwd = turn.cwd
        if first_ts and cwd:
            break
    return SessionMeta(ref, first_ts, cwd)


def under(path: str, root: Path) -> bool:
    if not path:
        return False
    try:
        return Path(path).resolve() == root or root in Path(path).resolve().parents
    except (OSError, ValueError):
        return False


def scan(adapter, root: Path | None = None, since: str | None = None,
         until: str | None = None, self_path: Path | None = None,
         include_self: bool = False) -> list[SessionMeta]:
    """Sessions in `[since, until)`, sorted by first timestamp.

    SELF-EXCLUSION IS ON BY DEFAULT. A session whose working directory is this
    tool's own is a session about the instrument, and folding it into an
    aggregate lets the instrument measure its own development and report the
    result as a finding about the corpus. Flagged either way; `include_self`
    only decides whether it counts.

    A session with no parseable timestamp is dropped when a bound is given and
    kept when none is: it cannot be placed, and dropping it from an unfiltered
    scan would understate the corpus.
    """
    lo, hi = parse_when(since), parse_when(until)
    self_root = (self_path or Path.cwd()).resolve()

    out: list[SessionMeta] = []
    for ref in adapter.sessions(root):
        # Enumeration is not validation: vendor stores can still name a
        # session after the record shape the adapter understands disappears.
        # Probe before any fast-path metadata read so drift never becomes a
        # quiet, zero-turn session.
        adapter.probe(ref)
        m = meta(adapter, ref)
        if lo or hi:
            first = parse_ts(m.first_ts)
            if first is None:
                continue
            if lo and first < lo:
                continue
            if hi and first >= hi:
                continue
        if under(m.cwd, self_root):
            m = SessionMeta(m.ref, m.first_ts, m.cwd, not include_self,
                            "cwd is the tool's own working directory")
        out.append(m)
    return sorted(out, key=lambda s: (s.first_ts or "9999", s.ref.session_id))


def included(metas: list[SessionMeta]) -> list[SessionMeta]:
    return [m for m in metas if not m.excluded]
