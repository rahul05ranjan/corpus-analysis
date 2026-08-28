"""Behavioural signals and the candidate sequences they select.

Defaults are acts the harness recorded, not words anyone used: an interrupt, a
refused tool call, a message typed while the agent was still working, a prompt
arriving seconds after the last answer, the same file rewritten across a
boundary, an undo-shaped command.

Lexical markers are available and ship empty. A word list written while looking
at the corpus it will be run against is tuned to that corpus by construction,
and the resulting series measures the author as much as the subject. See
`lexicon.py`.
"""

from __future__ import annotations

from collections import Counter

from ..adapters.base import sorted_counts
from ..records import Episode, Provenance, Sequence, Turn

#: Ordered by how directly each one records the operator intervening.
TRIGGERS = ("interrupt", "denial", "edit_churn", "fast_reprompt")


def session_totals(turns: list[Turn]) -> dict[str, int]:
    """Behavioural counts over one session."""
    totals = {
        "turns": len(turns),
        "assistant_turns": 0,
        "typed_prompts": 0,
        "think_turns": 0,
        "out_tokens": 0,
        "reasoning_tokens": 0,
        "text_chars": 0,
        "signature_chars": 0,
        "thinking_chars": 0,
        "typed_chars": 0,
        "tool_calls": 0,
        "writes": 0,
        "interrupts": 0,
        "denials": 0,
        "queued": 0,
        "errors": 0,
        "reverts": 0,
        "compact_summaries": 0,
        "sidechain_turns": 0,
    }
    for t in turns:
        f = t.flags
        if t.role == "assistant":
            totals["assistant_turns"] += 1
            # Assistant-scoped on purpose: this is the numerator of the
            # assistant-text-per-typed-char ratio, and a tool result's body is
            # not the model answering.
            totals["text_chars"] += t.chars.get("text", 0)
        # Vendor-neutral. One format nests usage and reasoning inside the
        # assistant message; another records each as its own event. Scoping
        # these to assistant turns reports zero tokens and zero reasoning for
        # the second, which reads as a model that never thought.
        totals["out_tokens"] += t.usage.get("output_tokens", 0)
        totals["reasoning_tokens"] += t.usage.get("reasoning_output_tokens", 0)
        totals["think_turns"] += int(bool(t.kinds.get("thinking")))
        totals["signature_chars"] += t.chars.get("signature", 0)
        totals["thinking_chars"] += t.chars.get("thinking", 0)
        if f.get("typed"):
            totals["typed_chars"] += len(t.text)
        totals["typed_prompts"] += int(bool(f.get("typed")))
        totals["tool_calls"] += t.kinds.get("tool_use", 0)
        totals["writes"] += sum(t.files.values())
        totals["interrupts"] += int(bool(f.get("interrupted")))
        totals["denials"] += int(bool(f.get("denied")))
        totals["queued"] += int(bool(f.get("queued")))
        totals["errors"] += int(bool(f.get("error")))
        totals["reverts"] += int(bool(f.get("revert")))
        totals["compact_summaries"] += int(bool(f.get("compact_summary")))
        totals["sidechain_turns"] += int(bool(f.get("sidechain")))
    return totals


def triggers_between(prev: Episode, cur: Episode) -> list[str]:
    """Which behavioural signals mark this episode pair as a repair candidate.

    All that fire are returned, because a pair carrying both an interrupt and a
    rewritten file is different evidence from a pair carrying one.
    """
    fired: list[str] = []
    if prev.signals.get("interrupts"):
        fired.append("interrupt")
    if prev.signals.get("denials"):
        fired.append("denial")
    if set(prev.files) & set(cur.files):
        fired.append("edit_churn")
    if cur.signals.get("fast_open") and prev.assistant_turns:
        fired.append("fast_reprompt")
    return [t for t in TRIGGERS if t in fired]


def repair_candidates(session_id: str, episodes: list[Episode]) -> list[Sequence]:
    """Consecutive episode pairs a behavioural signal selects.

    A candidate, not a finding. Whether the second episode repaired anything is
    an audit-layer judgment, made against the frozen bytes these provenance
    records point at.
    """
    out: list[Sequence] = []
    for i in range(1, len(episodes)):
        prev, cur = episodes[i - 1], episodes[i]
        fired = triggers_between(prev, cur)
        if not fired:
            continue
        out.append(Sequence(
            session_id=session_id,
            kind="repair_candidate",
            trigger=",".join(fired),
            episodes=[prev.index, cur.index],
            provenance=[prev.opened_by, cur.opened_by],
        ))
    return out


def trigger_mix(sequences: list[Sequence]) -> dict[str, int]:
    """How many candidates each trigger contributed to, heaviest first."""
    counts: Counter = Counter()
    for s in sequences:
        for t in s.trigger.split(","):
            counts[t] += 1
    return sorted_counts(counts)


def provenance_of(turns: list[Turn]) -> list[Provenance]:
    return [t.provenance for t in turns]
