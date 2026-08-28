"""Daily series, distance-from-prompt, and position — with its control attached.

Two measurement rules are structural here rather than advisory.

**A day is attributed per turn, not per session.** A session that opens at
23:50 and runs until 04:00 worked two days. Attributing its turns to the day it
started puts a release's whole footprint on one date and leaves the day the
work ran on blank.

**The position measurement never ships alone.** Splitting a session's turns
into thirds and comparing the last to the first tests the null that position
within a session does not matter — and conversation shape defeats that null
without any change in the model: reasoning clusters near fresh operator input,
and late thirds sit structurally farther from a prompt than early ones.
`position()` therefore returns the ratio and its control together, and the
report prints both or neither.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..adapters.base import sorted_counts
from ..records import Turn

#: Turns within this many of a typed prompt count as "near" it. The control's
#: one knob; the effect it isolates is visible at any small value.
NEAR_TURNS = 4

#: A session shorter than this has no interior, and a ratio over two or three
#: turns is noise.
MIN_TURNS_FOR_POSITION = 9

THIRDS = 3


@dataclass(slots=True)
class Day:
    """One day's counters, attributed by each turn's own timestamp."""

    date: str
    turns: int = 0
    assistant_turns: int = 0
    typed_prompts: int = 0
    think_turns: int = 0
    out_tokens: int = 0
    text_chars: int = 0
    typed_chars: int = 0
    tool_calls: int = 0
    interrupts: int = 0
    denials: int = 0
    queued: int = 0
    errors: int = 0
    sessions: set = field(default_factory=set)
    models: Counter = field(default_factory=Counter)
    versions: Counter = field(default_factory=Counter)
    efforts: Counter = field(default_factory=Counter)

    def ratios(self) -> dict[str, float | None]:
        return {
            "think_share": _div(self.think_turns, self.assistant_turns, 3),
            "out_per_turn": _div(self.out_tokens, self.assistant_turns, 0),
            "turns_per_prompt": _div(self.assistant_turns, self.typed_prompts, 2),
            "char_ratio": _div(self.text_chars, self.typed_chars, 1),
        }


def _div(num: int, den: int, places: int) -> float | None:
    if not den:
        return None
    v = num / den
    return round(v, places) if places else round(v)


def daily(scans) -> dict[str, Day]:
    """Per-day counters across every included session, in date order."""
    days: dict[str, Day] = {}
    for scan in scans:
        if scan.meta.excluded:
            continue
        for turn in scan.turns:
            if not turn.ts:
                continue
            key = turn.ts[:10]
            d = days.get(key)
            if d is None:
                d = days[key] = Day(key)
            d.sessions.add(scan.session_id)
            d.turns += 1
            d.out_tokens += turn.usage.get("output_tokens", 0)
            d.tool_calls += turn.kinds.get("tool_use", 0)
            if turn.kinds.get("thinking"):
                d.think_turns += 1
            if turn.role == "assistant":
                d.assistant_turns += 1
                d.text_chars += turn.chars.get("text", 0)
                # A long session crosses releases; the turn records which one
                # produced it.
                d.models[turn.model or "?"] += 1
                d.versions[turn.version or "?"] += 1
                d.efforts[turn.effort or "?"] += 1
            if turn.flags.get("typed"):
                d.typed_prompts += 1
                d.typed_chars += len(turn.text)
            d.interrupts += int(bool(turn.flags.get("interrupted")))
            d.denials += int(bool(turn.flags.get("denied")))
            d.queued += int(bool(turn.flags.get("queued")))
            d.errors += int(bool(turn.flags.get("error")))
    return dict(sorted(days.items()))


def by_model(scans) -> dict[str, dict[str, int]]:
    """Depth per model, so a shifting model mix cannot pose as a shift in depth.

    A pooled decline in `think_share` is equally well explained by two models
    blended in changing proportion. Held per model, the question is answerable;
    pooled, it is not.
    """
    out: dict[str, dict[str, int]] = defaultdict(
        lambda: {"turns": 0, "think": 0, "out_tokens": 0})
    for scan in scans:
        if scan.meta.excluded:
            continue
        for turn in scan.turns:
            if turn.role != "assistant":
                continue
            m = out[turn.model or "?"]
            m["turns"] += 1
            m["think"] += int(bool(turn.kinds.get("thinking")))
            m["out_tokens"] += turn.usage.get("output_tokens", 0)
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["turns"], kv[0])))


def distances(turns: list[Turn]) -> list[tuple[int, Turn]]:
    """(turns since the last typed prompt, turn) for each measurable turn.

    Distance is counted in turns rather than seconds: a pause is the operator's
    clock, and the quantity of interest is how far the model is from fresh
    instruction.
    """
    out: list[tuple[int, Turn]] = []
    since = -1
    for turn in turns:
        if turn.flags.get("typed"):
            since = 0
            continue
        if since < 0:
            continue
        since += 1
        if turn.role == "assistant":
            out.append((since, turn))
    return out


@dataclass(slots=True)
class Position:
    """The position ratio and the control that explains most of it."""

    sessions_measured: int
    ratio_median: float | None            # last third / first third
    below_one: int
    think_near: float | None              # think_share within NEAR_TURNS
    think_far: float | None               # think_share beyond it
    mean_distance_first: float | None
    mean_distance_last: float | None


def position(scans, near: int = NEAR_TURNS) -> Position:
    """The position measurement, never separable from its control.

    A caller cannot obtain the ratio without also obtaining the distance
    profile that predicts it, because reporting the first alone is the error
    this measurement exists to not repeat.
    """
    ratios: list[float] = []
    near_turns = near_think = far_turns = far_think = 0
    first_d: list[float] = []
    last_d: list[float] = []

    for scan in scans:
        if scan.meta.excluded:
            continue
        assistant = [t for t in scan.turns if t.role == "assistant"]
        r = _thirds_ratio(assistant)
        if r is not None:
            ratios.append(r)

        d = distances(scan.turns)
        for dist, turn in d:
            thought = int(bool(turn.kinds.get("thinking")))
            if dist <= near:
                near_turns += 1
                near_think += thought
            else:
                far_turns += 1
                far_think += thought

        if len(d) >= MIN_TURNS_FOR_POSITION:
            k = len(d) // THIRDS
            first_d.append(statistics.mean(x for x, _ in d[:k]))
            last_d.append(statistics.mean(x for x, _ in d[-k:]))

    return Position(
        sessions_measured=len(ratios),
        ratio_median=round(statistics.median(ratios), 3) if ratios else None,
        below_one=sum(1 for r in ratios if r < 1.0),
        think_near=_div(near_think, near_turns, 3),
        think_far=_div(far_think, far_turns, 3),
        mean_distance_first=round(statistics.mean(first_d), 1) if first_d else None,
        mean_distance_last=round(statistics.mean(last_d), 1) if last_d else None,
    )


def _thirds_ratio(assistant: list[Turn]) -> float | None:
    n = len(assistant)
    if n < MIN_TURNS_FOR_POSITION:
        return None
    k = n // THIRDS
    head = statistics.mean(t.usage.get("output_tokens", 0) for t in assistant[:k])
    tail = statistics.mean(t.usage.get("output_tokens", 0) for t in assistant[-k:])
    return round(tail / head, 3) if head else None


def self_normalized(values: list[float], baseline: int = 10) -> list[float | None]:
    """Each value against this corpus's own earlier values.

    Scored in median-absolute-deviation units against the preceding `baseline`
    observations. Absolute rates are never compared across corpora: writing
    style, task mix, and tooling differ enough that a cross-corpus difference
    measures the operators.

    This removes one confound and names it. Drift within a single corpus — a
    changing task mix, a changing idiolect — is untouched, which is why the
    baseline window is a parameter rather than a constant.
    """
    out: list[float | None] = []
    for i, v in enumerate(values):
        window = values[max(0, i - baseline):i]
        if len(window) < 3:
            out.append(None)
            continue
        med = statistics.median(window)
        mad = statistics.median([abs(w - med) for w in window]) or 1e-9
        out.append(round((v - med) / (1.4826 * mad), 2))
    return out


def version_mix(scans) -> dict[str, int]:
    """Harness releases seen, heaviest first. A runtime change has a date."""
    counts: Counter = Counter()
    for scan in scans:
        if scan.meta.excluded:
            continue
        for turn in scan.turns:
            if turn.role == "assistant" and turn.version:
                counts[turn.version] += 1
    return sorted_counts(counts)
