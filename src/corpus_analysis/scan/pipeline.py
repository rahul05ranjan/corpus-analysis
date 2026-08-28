"""adapter -> turns -> episodes -> candidate sequences, in one pass per session.

Deterministic and read-only. No model, no network. Useful with nothing attached
to it, which is the property that keeps the scanner honest: every number the
audit layer reasons about was produced here first, and can be recomputed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..records import Episode, Sequence, Turn
from . import episodes as ep
from . import signals
from .sessions import SessionMeta, scan


@dataclass(slots=True)
class SessionScan:
    """One session, measured."""

    meta: SessionMeta
    turns: list[Turn]
    episodes: list[Episode]
    sequences: list[Sequence]
    totals: dict[str, int]
    lexicon_hits: dict[str, int]

    @property
    def session_id(self) -> str:
        return self.meta.ref.session_id


def scan_sessions(adapter, root: Path | None = None, since: str | None = None,
                  until: str | None = None, include_self: bool = False,
                  self_path: Path | None = None,
                  lexicons: dict[str, re.Pattern] | None = None,
                  fast_seconds: int = ep.FAST_REPROMPT_SECONDS,
                  ) -> Iterator[SessionScan]:
    """Every session in the window, in a stable order."""
    from .lexicon import match

    lexicons = lexicons or {}
    for meta in scan(adapter, root, since, until, self_path, include_self):
        turns = list(adapter.turns(meta.ref))
        eps = ep.segment(meta.ref.session_id, turns, fast_seconds)
        hits: dict[str, int] = dict.fromkeys(lexicons, 0)
        for t in turns:
            if not t.flags.get("typed"):
                continue
            for group, hit in match(lexicons, t.text).items():
                hits[group] += int(hit)
        yield SessionScan(
            meta=meta,
            turns=turns,
            episodes=eps,
            sequences=signals.repair_candidates(meta.ref.session_id, eps),
            totals=signals.session_totals(turns),
            lexicon_hits=hits,
        )


def corpus_totals(scans: list[SessionScan]) -> dict[str, int]:
    """Sums over included sessions. Excluded sessions are counted separately."""
    keys = signals.session_totals([]).keys()
    out = dict.fromkeys(keys, 0)
    out["sessions"] = 0
    out["episodes"] = 0
    out["sequences"] = 0
    for s in scans:
        if s.meta.excluded:
            continue
        out["sessions"] += 1
        out["episodes"] += len(s.episodes)
        out["sequences"] += len(s.sequences)
        for k in keys:
            out[k] += s.totals[k]
    return out
