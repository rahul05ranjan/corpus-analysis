"""Temporal views: when the work happened, as labelled heat tables.

Aggregation is arithmetic over normalised turn records; rendering scales each
row to its own maximum in eighths of a block glyph. Both are order-independent:
every counter is sorted before it reaches the page, so two runs that read the
same records in a different sequence render the same bytes.

The timezone is an argument, never the machine's. A clock view depends on the
reader's zone, and reading it from the environment would let two machines
render different bytes from the same corpus. The default is UTC.

Two windows are DESIGN CHOICE, stated on the figures they license: night is
22:00-04:59 local, weekend is Saturday and Sunday.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

from ..labels import COUNTED, DERIVED, Column, Figure, Report
from .sessions import parse_ts

#: A model under this many assistant turns is omitted from the model strip; a
#: row over a handful of turns is noise. Same threshold `scan.report._by_model`
#: filters on, where the value is duplicated as a literal rather than imported.
MIN_MODEL_TURNS = 50

#: Night window, half-open on the morning side: hour >= NIGHT_FROM or < NIGHT_TO.
NIGHT_FROM = 22
NIGHT_TO = 5

HEAVIEST_DAYS = 10

_SHADES = "·▁▂▃▄▅▆▇█"

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: What licenses a shade strip. The strip carries no digits; the counts it
#: scales are printed beside it under a counted column.
STRIP_RULE = "each cell scales the bucket count to the row maximum, in eighths"

RULES = {
    "median_len": "median length of the retained typed prompt text; "
                  "retention is bounded at adapters.base.MAX_TEXT chars",
    "chars_per_prompt": "assistant text+thinking chars / typed prompts",
    "tokens_per_prompt": "assistant output_tokens / typed prompts",
    "tools_per_prompt": "tool_use blocks / typed prompts",
    "night_share": "typed prompts 22:00-04:59 local / typed prompts "
                   "(window is DESIGN CHOICE)",
    "weekend_share": "typed prompts on Sat or Sun / typed prompts "
                     "(window is DESIGN CHOICE)",
    "per_100": "flagged turns per 100 typed prompts in the month",
    "prompts_per_day": "median typed prompts over active days",
}


@dataclass(slots=True)
class Temporal:
    """Counters over one pass, every one keyed by strings and small ints."""

    tz: str
    turns_seen: int = 0
    turns_without_ts: int = 0
    prompts: int = 0
    weekday_hour: Counter = field(default_factory=Counter)   # (0-6, 0-23)
    month_hour: Counter = field(default_factory=Counter)     # ("YYYY-MM", 0-23)
    hour: Counter = field(default_factory=Counter)
    source_month: Counter = field(default_factory=Counter)   # (adapter, ym)
    model_month: Counter = field(default_factory=Counter)    # (model, ym)
    model_turns: Counter = field(default_factory=Counter)
    month_prompts: Counter = field(default_factory=Counter)
    month_out_chars: Counter = field(default_factory=Counter)
    month_out_tokens: Counter = field(default_factory=Counter)
    month_tools: Counter = field(default_factory=Counter)
    month_night: Counter = field(default_factory=Counter)
    month_weekend: Counter = field(default_factory=Counter)
    month_flags: Counter = field(default_factory=Counter)    # (ym, flag)
    hour_lens: dict = field(default_factory=lambda: defaultdict(list))
    month_lens: dict = field(default_factory=lambda: defaultdict(list))
    day_prompts: Counter = field(default_factory=Counter)    # "YYYY-MM-DD"
    day_sources: dict = field(default_factory=lambda: defaultdict(set))

    def months(self) -> list[str]:
        """Every month from first to last seen, gaps included: an empty month
        is a fact about the corpus, not a rendering accident."""
        seen = {ym for ym, _ in self.month_hour} | set(self.month_prompts)
        seen |= {ym for _, ym in self.source_month} | {ym for _, ym in self.model_month}
        if not seen:
            return []
        y, m = (int(p) for p in min(seen).split("-"))
        last = max(seen)
        out = []
        while True:
            ym = f"{y:04d}-{m:02d}"
            out.append(ym)
            if ym == last:
                return out
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)


#: Flags a turn can carry that read as friction. Behavioural, not lexical.
FRICTION_FLAGS = ("interrupted", "denied", "revert", "error")


def aggregate(turns, tz: str = "UTC") -> Temporal:
    """One pass over turn dicts (`Turn.to_dict()` payloads or ingest lines).

    A turn with no convertible timestamp is counted in `turns_without_ts` and
    reaches no bucket: a clock view built on repaired timestamps would be the
    mtime mistake with extra steps.
    """
    zone = timezone.utc if tz == "UTC" else ZoneInfo(tz)
    agg = Temporal(tz=tz)
    for t in turns:
        agg.turns_seen += 1
        dt = parse_ts(t.get("ts") or None)
        if dt is None:
            agg.turns_without_ts += 1
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        loc = dt.astimezone(zone)
        ym = f"{loc.year:04d}-{loc.month:02d}"
        flags = t.get("flags") or {}
        for flag in FRICTION_FLAGS:
            if flags.get(flag):
                agg.month_flags[(ym, flag)] += 1
        role = t.get("role")
        if role == "assistant":
            chars = t.get("chars") or {}
            agg.month_out_chars[ym] += chars.get("text", 0) + chars.get("thinking", 0)
            agg.month_out_tokens[ym] += (t.get("usage") or {}).get("output_tokens", 0)
            agg.month_tools[ym] += (t.get("kinds") or {}).get("tool_use", 0)
            model = t.get("model") or ""
            if model:
                agg.model_month[(model, ym)] += 1
                agg.model_turns[model] += 1
        if role == "user" and flags.get("typed"):
            agg.prompts += 1
            agg.weekday_hour[(loc.weekday(), loc.hour)] += 1
            agg.month_hour[(ym, loc.hour)] += 1
            agg.hour[loc.hour] += 1
            agg.month_prompts[ym] += 1
            if loc.hour >= NIGHT_FROM or loc.hour < NIGHT_TO:
                agg.month_night[ym] += 1
            if loc.weekday() >= 5:
                agg.month_weekend[ym] += 1
            day = loc.date().isoformat()
            agg.day_prompts[day] += 1
            adapter = (t.get("provenance") or {}).get("adapter", "?")
            agg.day_sources[day].add(adapter)
            agg.source_month[(adapter, ym)] += 1
            n = len(t.get("text") or "")
            if n:
                agg.hour_lens[loc.hour].append(n)
                agg.month_lens[ym].append(n)
    return agg


def _strip(values: list[int]) -> str:
    mx = max(values, default=0)
    if not mx:
        return _SHADES[0] * len(values)
    return "".join(
        _SHADES[0] if v == 0 else _SHADES[max(1, min(8, round(v / mx * 8)))]
        for v in values
    )


def _share(part: int, whole: int) -> float | str:
    return round(part / whole, 3) if whole else "—"


def _med(values: list[int]) -> int | str:
    return round(statistics.median(values)) if values else "—"


def _streak(days: list[str]) -> int:
    best = run = 0
    prev: date | None = None
    for d in (date.fromisoformat(s) for s in days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def temporal_report(agg: Temporal) -> str:
    r = Report("Temporal views")
    r.prose(
        f"Clock buckets are attributed per typed prompt, in the {agg.tz} "
        "timezone the caller named. A turn with no convertible timestamp "
        "reaches no bucket and is counted below; nothing is repaired or "
        "inferred. Shade strips carry no numbers - the counts they scale sit "
        "beside them."
    )
    r.figures(
        Figure("turns read", agg.turns_seen, COUNTED),
        Figure("turns without a convertible timestamp", agg.turns_without_ts,
               COUNTED),
        Figure("typed prompts placed on the clock", agg.prompts, COUNTED),
    )
    if not agg.prompts:
        r.prose("No typed prompt carried a timestamp; there is nothing to plot.")
        return r.render()

    months = agg.months()
    span = f"{months[0]} to {months[-1]}"

    r.heading("Day of week by hour")
    r.table(
        [Column("day", COUNTED),
         Column("hours 00-23", DERIVED, STRIP_RULE),
         Column("prompts", COUNTED)],
        [[name,
          _strip([agg.weekday_hour.get((wd, h), 0) for h in range(24)]),
          sum(agg.weekday_hour.get((wd, h), 0) for h in range(24))]
         for wd, name in enumerate(_WEEKDAYS)],
    )

    r.heading("Month by hour")
    r.table(
        [Column("month", COUNTED),
         Column("hours 00-23", DERIVED, STRIP_RULE),
         Column("prompts", COUNTED)],
        [[ym,
          _strip([agg.month_hour.get((ym, h), 0) for h in range(24)]),
          agg.month_prompts.get(ym, 0)]
         for ym in months],
    )

    r.heading("Hour of day")
    r.table(
        [Column("hour", COUNTED),
         Column("prompts", COUNTED),
         Column("median prompt chars", DERIVED, RULES["median_len"])],
        [[f"{h:02d}", agg.hour.get(h, 0), _med(agg.hour_lens.get(h, []))]
         for h in range(24)],
    )

    r.heading("Sources by month")
    sources = sorted({a for a, _ in agg.source_month})
    r.table(
        [Column("source", COUNTED),
         Column(span, DERIVED, STRIP_RULE),
         Column("prompts", COUNTED)],
        [[a,
          _strip([agg.source_month.get((a, ym), 0) for ym in months]),
          sum(agg.source_month.get((a, ym), 0) for ym in months)]
         for a in sources],
    )

    heavy_models = sorted(
        ((m, n) for m, n in agg.model_turns.items() if n >= MIN_MODEL_TURNS),
        key=lambda kv: (-kv[1], kv[0]),
    )
    if heavy_models:
        r.heading("Models by month")
        r.prose(
            "Assistant turns, attributed per turn. Models under the "
            "same fifty-turn floor the depth table uses are omitted."
        )
        r.table(
            [Column("model", COUNTED),
             Column(span, DERIVED, STRIP_RULE),
             Column("assistant turns", COUNTED)],
            [[m,
              _strip([agg.model_month.get((m, ym), 0) for ym in months]),
              n]
             for m, n in heavy_models],
        )

    r.heading("Monthly series")
    r.table(
        [Column("month", COUNTED),
         Column("prompts", COUNTED),
         Column("median prompt chars", DERIVED, RULES["median_len"]),
         Column("out chars/prompt", DERIVED, RULES["chars_per_prompt"]),
         Column("out tokens/prompt", DERIVED, RULES["tokens_per_prompt"]),
         Column("tools/prompt", DERIVED, RULES["tools_per_prompt"]),
         Column("night share", DERIVED, RULES["night_share"]),
         Column("weekend share", DERIVED, RULES["weekend_share"])],
        [[ym, p, _med(agg.month_lens.get(ym, [])),
          round(agg.month_out_chars.get(ym, 0) / p) if p else "—",
          round(agg.month_out_tokens.get(ym, 0) / p) if p else "—",
          round(agg.month_tools.get(ym, 0) / p, 2) if p else "—",
          _share(agg.month_night.get(ym, 0), p),
          _share(agg.month_weekend.get(ym, 0), p)]
         for ym in months
         for p in [agg.month_prompts.get(ym, 0)]],
    )

    if any(agg.month_flags.values()):
        r.heading("Friction by month")
        r.prose(
            "Recorded by the harness that caused it, normalised so a heavy "
            "month cannot read as a worse one by volume alone."
        )
        r.table(
            [Column("month", COUNTED)]
            + [Column(f"{flag}/100", DERIVED, RULES["per_100"])
               for flag in FRICTION_FLAGS],
            [[ym] + [
                round(100 * agg.month_flags.get((ym, flag), 0) / p, 1)
                if p else "—"
                for flag in FRICTION_FLAGS]
             for ym in months
             for p in [agg.month_prompts.get(ym, 0)]],
        )

    days = sorted(agg.day_prompts)
    r.heading("Cadence")
    r.figures(
        Figure("first active day", days[0], COUNTED),
        Figure("last active day", days[-1], COUNTED),
        Figure("active days", len(days), COUNTED),
        Figure("longest run of consecutive active days", _streak(days), COUNTED),
        Figure("median prompts per active day",
               _med(list(agg.day_prompts.values())), DERIVED,
               RULES["prompts_per_day"]),
    )
    r.table(
        [Column("heaviest days", COUNTED),
         Column("prompts", COUNTED),
         Column("sources", COUNTED)],
        [[day, n, ",".join(sorted(agg.day_sources[day]))]
         for day, n in sorted(agg.day_prompts.items(),
                              key=lambda kv: (-kv[1], kv[0]))[:HEAVIEST_DAYS]],
    )
    return r.render()
