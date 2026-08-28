"""Segment a session into episodes at each typed prompt.

The typed prompt is the only boundary a transcript records unambiguously. A
gap-based split would need a threshold, and the threshold would decide the
answer.

Turns that precede the first typed prompt keep their own episode with
`prompt_chars` zero and an `unopened` signal — a resumed session opens with a
continuation summary rather than an instruction, and inventing an opening
prompt for those turns would attribute them to something nobody typed.
"""

from __future__ import annotations

from collections import Counter

from ..adapters.base import sorted_counts
from ..records import Episode, Turn
from .sessions import parse_ts

#: A typed prompt arriving within this many seconds of the last assistant turn.
#: Behavioural evidence that the operator was reacting rather than composing;
#: a knob rather than a constant, because typing speed and task mix differ.
FAST_REPROMPT_SECONDS = 45

#: Per-episode counters. Present with an explicit zero so a quiet episode and an
#: unmeasured one stay distinguishable.
SIGNAL_KEYS = (
    "interrupts", "denials", "queued", "errors", "reverts", "writes",
    "unopened", "fast_open",
)


def _blank(session_id: str, index: int, turn: Turn, prompt_chars: int,
           unopened: bool) -> dict:
    signals = dict.fromkeys(SIGNAL_KEYS, 0)
    signals["unopened"] = int(unopened)
    return {
        "session_id": session_id,
        "index": index,
        "ts": turn.ts,
        "prompt_chars": prompt_chars,
        "turns": 0,
        "assistant_turns": 0,
        "think_turns": 0,
        "out_tokens": 0,
        "models": Counter(),
        "files": Counter(),
        "signals": signals,
        "opened_by": turn.provenance,
    }


def segment(session_id: str, turns: list[Turn],
            fast_seconds: int = FAST_REPROMPT_SECONDS) -> list[Episode]:
    """Episodes in order. An empty session yields none."""
    out: list[dict] = []
    cur: dict | None = None
    last_assistant: str = ""

    for turn in turns:
        if turn.flags.get("typed"):
            if cur is not None:
                out.append(cur)
            cur = _blank(session_id, len(out), turn, len(turn.text), False)
            cur["signals"]["fast_open"] = int(
                _gap(last_assistant, turn.ts) <= fast_seconds
            )
            continue

        if turn.role == "assistant" and turn.ts:
            last_assistant = turn.ts

        if cur is None:
            if turn.role == "event" and not any(turn.flags.values()):
                continue  # nothing to attribute yet
            cur = _blank(session_id, 0, turn, 0, True)

        cur["turns"] += 1
        _accumulate(cur, turn)

    if cur is not None:
        out.append(cur)
    return [_freeze(e) for e in out]


def _gap(earlier: str, later: str) -> float:
    """Seconds between two timestamps; infinity when either is missing."""
    a, b = parse_ts(earlier), parse_ts(later)
    if a is None or b is None:
        return float("inf")
    return (b - a).total_seconds()


def _accumulate(ep: dict, turn: Turn) -> None:
    if turn.role == "assistant":
        ep["assistant_turns"] += 1
        if turn.model:
            ep["models"][turn.model] += 1
    # Not assistant-scoped: one format nests usage and reasoning inside the
    # assistant message, another records each as its own event.
    ep["out_tokens"] += turn.usage.get("output_tokens", 0)
    if turn.kinds.get("thinking"):
        ep["think_turns"] += 1
    flags = turn.flags
    s = ep["signals"]
    s["interrupts"] += int(bool(flags.get("interrupted")))
    s["denials"] += int(bool(flags.get("denied")))
    s["queued"] += int(bool(flags.get("queued")))
    s["errors"] += int(bool(flags.get("error")))
    s["reverts"] += int(bool(flags.get("revert")))
    s["writes"] += sum(turn.files.values())
    for path, n in turn.files.items():
        ep["files"][path] += n


def _freeze(ep: dict) -> Episode:
    ep["models"] = sorted_counts(ep["models"])
    ep["files"] = sorted_counts(ep["files"])
    return Episode(**ep)


def written_files(turns: list[Turn]) -> dict[str, int]:
    """Every path written in this span, heaviest first."""
    files: Counter = Counter()
    for turn in turns:
        for path, n in turn.files.items():
            files[path] += n
    return sorted_counts(files)
