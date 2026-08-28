"""The corpus report. Every figure in it carries its epistemic status.

Numbers reach the page as `Figure` or as a cell under a labelled `Column`;
there is no third route. `labels.lint()` runs on the rendered text before it is
returned, so a report that lost a label fails at generation rather than in
review.
"""

from __future__ import annotations

from ..labels import COUNTED, DERIVED, PROXY, Column, Figure, Report
from .metrics import by_model, daily, position, version_mix
from .pipeline import SessionScan, corpus_totals
from .signals import trigger_mix

#: The rule behind each derived figure, printed beside it.
RULES = {
    "think_share": "think_turns / assistant_turns",
    "out_per_turn": "out_tokens / assistant_turns",
    "turns_per_prompt": "assistant_turns / typed_prompts",
    "char_ratio": "assistant text chars / typed chars",
}

#: What a proxy stands in for. Reasoning text is withheld by the format, so
#: signature length is the only per-turn quantity that varies with it — and it
#: is an opaque blob whose length is assumed, not known, to track its content.
PROXY_BASIS = (
    "signature length stands in for withheld reasoning text; "
    "assumed to track it, never measured against it"
)


def _ratio(num: int, den: int, places: int = 3) -> float | str:
    return round(num / den, places) if den else "—"


def _cell(v) -> object:
    return "—" if v is None else v


def corpus_report(scans: list[SessionScan], since: str | None = None,
                  until: str | None = None) -> str:
    kept = [s for s in scans if not s.meta.excluded]
    excluded = [s for s in scans if s.meta.excluded]
    totals = corpus_totals(scans)

    r = Report("Corpus scan")
    r.prose(
        "Every figure below is labelled with what licenses it: counted is "
        "arithmetic over records, derived combines counted values under a "
        "stated rule, proxy stands in for something the format does not "
        "record and names the assumption. No model produced any of it."
    )

    r.heading("Coverage")
    r.figures(
        Figure("window since", since or "unbounded", COUNTED),
        Figure("window until", until or "unbounded", COUNTED),
        Figure("sessions", totals["sessions"], COUNTED),
        Figure("sessions excluded as self-measurement", len(excluded), COUNTED),
        Figure("turns", totals["turns"], COUNTED),
        Figure("assistant turns", totals["assistant_turns"], COUNTED),
        Figure("typed prompts", totals["typed_prompts"], COUNTED),
        Figure("episodes", totals["episodes"], COUNTED),
        Figure("candidate repair sequences", totals["sequences"], COUNTED),
    )
    if excluded:
        r.prose(
            "Excluded sessions ran with this tool's own directory as their "
            "working directory. Measuring them would let the instrument report "
            "its own development as a property of the corpus."
        )

    r.heading("Depth")
    r.figures(
        Figure("think_share", _ratio(totals["think_turns"],
                                     totals["assistant_turns"]),
               DERIVED, RULES["think_share"]),
        Figure("out_tokens per assistant turn", _ratio(totals["out_tokens"],
                                                       totals["assistant_turns"], 1),
               DERIVED, RULES["out_per_turn"]),
        Figure("signature chars per reasoning turn",
               _ratio(totals["signature_chars"], totals["think_turns"], 1),
               PROXY, PROXY_BASIS),
    )

    r.heading("Shape")
    r.figures(
        Figure("assistant turns per typed prompt",
               _ratio(totals["assistant_turns"], totals["typed_prompts"], 2),
               DERIVED, RULES["turns_per_prompt"]),
        Figure("assistant chars per typed char",
               _ratio(totals["text_chars"], totals["typed_chars"], 1),
               DERIVED, RULES["char_ratio"]),
    )

    r.heading("Behaviour")
    r.prose(
        "Recorded by the harness that caused it: an interrupt is the operator "
        "stopping a turn, a denial is a refused tool call, queued is a message "
        "typed while the agent was still working."
    )
    r.figures(
        Figure("interrupts", totals["interrupts"], COUNTED),
        Figure("tool denials", totals["denials"], COUNTED),
        Figure("queued while working", totals["queued"], COUNTED),
        Figure("tool errors", totals["errors"], COUNTED),
        Figure("undo-shaped commands", totals["reverts"], COUNTED),
        Figure("continuation summaries", totals["compact_summaries"], COUNTED),
    )

    mix = trigger_mix([q for s in kept for q in s.sequences])
    if mix:
        r.heading("What selected the candidate sequences")
        r.prose(
            "A candidate is a pair of consecutive episodes a behavioural signal "
            "marked. Whether the second repaired anything is an audit-layer "
            "judgment, made against the frozen bytes its provenance points at. "
            "One pair can carry more than one trigger, so these do not sum to "
            "the sequence count."
        )
        r.table(
            [Column("trigger", COUNTED), Column("sequences", COUNTED)],
            [[k, v] for k, v in mix.items()],
        )

    _runtime(r, kept)
    _daily(r, kept)
    _by_model(r, kept)
    _position(r, kept)

    if kept:
        r.heading("Sessions")
        r.table(
            [
                Column("session", COUNTED),
                Column("first_ts", COUNTED),
                Column("turns", COUNTED),
                Column("prompts", COUNTED),
                Column("episodes", COUNTED),
                Column("candidates", COUNTED),
                Column("think_share", DERIVED, RULES["think_share"]),
            ],
            [
                [
                    s.session_id[:8],
                    (s.meta.first_ts or "—")[:19],
                    s.totals["turns"],
                    s.totals["typed_prompts"],
                    len(s.episodes),
                    len(s.sequences),
                    _ratio(s.totals["think_turns"], s.totals["assistant_turns"]),
                ]
                for s in kept
            ],
        )

    return r.render()


def _runtime(r: Report, kept: list[SessionScan]) -> None:
    """What changed underneath the work. A runtime change has a date."""
    mix = version_mix(kept)
    if len(mix) < 2:
        return
    r.heading("Harness releases")
    r.prose(
        "Attributed per turn, not per session: a long session crosses "
        "releases, and the turn records which one produced it. Alignment "
        "between a release and a change in a series below is timing, not "
        "cause — the operator's own behaviour also moves over a window."
    )
    r.table(
        [Column("release", COUNTED), Column("assistant turns", COUNTED)],
        [[k, v] for k, v in mix.items()],
    )


def _daily(r: Report, kept: list[SessionScan]) -> None:
    days = daily(kept)
    if len(days) < 2:
        return
    r.heading("Daily series")
    r.prose(
        "Each turn lands on the day it ran, not the day its session opened. "
        "A short series supports no test; it shows the shape and leaves the "
        "reading to you."
    )
    r.table(
        [
            Column("day", COUNTED),
            Column("sessions", COUNTED),
            Column("turns", COUNTED),
            Column("prompts", COUNTED),
            Column("think_share", DERIVED, RULES["think_share"]),
            Column("out/turn", DERIVED, RULES["out_per_turn"]),
            Column("turns/prompt", DERIVED, RULES["turns_per_prompt"]),
            Column("char_ratio", DERIVED, RULES["char_ratio"]),
        ],
        [
            [d.date, len(d.sessions), d.turns, d.typed_prompts,
             _cell(d.ratios()["think_share"]), _cell(d.ratios()["out_per_turn"]),
             _cell(d.ratios()["turns_per_prompt"]),
             _cell(d.ratios()["char_ratio"])]
            for d in days.values()
        ],
    )


def _by_model(r: Report, kept: list[SessionScan]) -> None:
    """Depth per model, so a shifting mix cannot pose as a shift in depth."""
    models = {k: v for k, v in by_model(kept).items() if v["turns"] >= 50}
    if len(models) < 2:
        return
    r.heading("Depth, with the model mix held out")
    r.prose(
        "A pooled decline in reasoning share is equally well explained by two "
        "models blended in changing proportion. Held per model the question is "
        "answerable; pooled it is not. Models under fifty turns are omitted, "
        "because a ratio over a handful of turns is noise."
    )
    r.table(
        [
            Column("model", COUNTED),
            Column("assistant turns", COUNTED),
            Column("think_share", DERIVED, RULES["think_share"]),
            Column("out/turn", DERIVED, RULES["out_per_turn"]),
        ],
        [
            [name, m["turns"],
             _ratio(m["think"], m["turns"]),
             _ratio(m["out_tokens"], m["turns"], 0)]
            for name, m in models.items()
        ],
    )


def _position(r: Report, kept: list[SessionScan]) -> None:
    """The position measurement and the control that explains most of it.

    Printed together or not at all. The ratio alone reads as evidence that a
    model slackens as a task runs on; the control below shows conversation
    shape predicting the same result with no change in the model.
    """
    p = position(kept)
    if not p.sessions_measured or p.think_near is None or p.think_far is None:
        return

    r.heading("Position, and its control")
    r.figures(
        Figure("sessions long enough to measure", p.sessions_measured, COUNTED),
        Figure("median last-third / first-third output tokens",
               _cell(p.ratio_median), DERIVED,
               "mean output_tokens of the last third over the first"),
        Figure("sessions below one", p.below_one, COUNTED),
    )
    r.prose(
        "Below one means less was generated toward the end of a session. Read "
        "on before treating that as slackening: the null it rejects is that "
        "position within a session does not matter, and conversation shape "
        "defeats that null on its own."
    )
    r.figures(
        Figure("think_share near a typed prompt", _cell(p.think_near), DERIVED,
               "reasoning turns / assistant turns within four turns of a prompt"),
        Figure("think_share beyond it", _cell(p.think_far), DERIVED,
               "the same ratio, further than four turns from a prompt"),
        Figure("mean distance from a prompt, first third",
               _cell(p.mean_distance_first), COUNTED),
        Figure("mean distance from a prompt, last third",
               _cell(p.mean_distance_last), COUNTED),
    )
    r.prose(
        "Reasoning clusters near fresh instruction, and late thirds sit "
        "structurally farther from it. If the two distance figures differ and "
        "the two share figures differ in the same direction, the position "
        "ratio is explained by where the turns sit in the conversation rather "
        "than by any change in diligence. Isolating a real effect means "
        "conditioning the ratio on distance, and this report does not claim to "
        "have done so."
    )
