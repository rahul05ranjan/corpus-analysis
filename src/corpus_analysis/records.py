"""Canonical records. Every layer above the adapters speaks these and nothing else.

Two rules hold across all of them:

1. Observed values and interpretive labels live in separate fields and are never
   merged. `Finding.observed` is what a record says; `Finding.labels` is what a
   reader concluded. A schema that lets them share a key makes an audit
   unreviewable.
2. Serialization is deterministic. `to_line()` sorts keys at every level, so the
   same corpus produces byte-identical output and a run can be hashed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

SCHEMA_VERSION = 1

#: Content-block kinds counted per turn. `other` absorbs anything an adapter
#: does not recognise, so a new vendor block type changes a count rather than
#: disappearing.
KINDS = ("text", "thinking", "tool_use", "tool_result", "image", "other")

#: Behavioural flags. Present on every turn with an explicit value; a missing
#: key and a false one would otherwise be indistinguishable downstream.
FLAGS = (
    "typed",            # the operator typed this prompt
    "interrupted",      # the operator stopped a turn in flight
    "denied",           # a tool call was refused
    "queued",           # typed while the agent was still working
    "meta",             # harness talking to itself through the user channel
    "compact_summary",  # continuation summary injected on context overflow
    "error",            # carries a tool result marked as an error
    "sidechain",        # subagent turn
    "revert",           # ran an undo-shaped command
)

#: Usage keys are always present. A vendor that does not record one reports
#: zero, so a whole-adapter zero means "not recorded" and never "none happened"
#: — `reasoning_output_tokens` is zero across formats that withhold it, and a
#: report must not read that as an absence of reasoning.
TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_output_tokens",
)

#: API-level fields that either held constant across a corpus or did not.
#: Movement in one is a fact about the runtime, not about the operator.
INVARIANTS = ("service_tier", "speed", "inference_geo")


def line_digest(raw: bytes) -> str:
    """sha256 of one source line, excluding its terminator.

    Verifiable outside this tool by reading the named physical line as bytes,
    removing its CR/LF terminator when present, and hashing the result. Hashing
    the decoded string instead would make the digest depend on this process's
    error handling.
    """
    return hashlib.sha256(raw.rstrip(b"\r\n")).hexdigest()


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a record came from, precisely enough to re-read it."""

    adapter: str
    path: str
    line: int          # 0-based index into the source file
    sha256: str        # line_digest of the source line
    session_id: str
    turn_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Turn:
    """One exchange record, normalised across vendors."""

    schema_version: int
    role: str                      # user | assistant | event
    source_type: str               # the vendor's own record type, uninterpreted
    ts: str                        # ISO 8601, or "" when the record carries none
    model: str
    version: str                   # harness release that produced the turn
    effort: str
    cwd: str
    kinds: dict[str, int]
    chars: dict[str, int]          # text, thinking, signature
    usage: dict[str, int]
    invariants: dict[str, str]
    tools: dict[str, int]
    files: dict[str, int]          # path -> writes, for edit-churn measurement
    flags: dict[str, bool]
    text: str                      # typed prompt text only; see MAX_TEXT
    provenance: Provenance

    def to_dict(self, with_text: bool = True) -> dict:
        d = asdict(self)
        if not with_text:
            d["text"] = ""
        return d

    def to_line(self, with_text: bool = True) -> str:
        return dumps(self.to_dict(with_text))


@dataclass(frozen=True, slots=True)
class Episode:
    """A typed prompt and the work that ran under it.

    The only segmentation boundary a transcript records unambiguously. A
    gap-based split would need a threshold, and the threshold would decide the
    answer.
    """

    session_id: str
    index: int
    ts: str
    prompt_chars: int
    turns: int
    assistant_turns: int
    think_turns: int
    out_tokens: int
    models: dict[str, int]
    files: dict[str, int]
    signals: dict[str, int]
    opened_by: Provenance

    def to_dict(self) -> dict:
        return asdict(self)

    def to_line(self) -> str:
        return dumps(self.to_dict())


@dataclass(frozen=True, slots=True)
class Sequence:
    """Consecutive episodes flagged as a candidate challenge/repair chain.

    A candidate, named by the signal that selected it. Whether it is a repair is
    an audit-layer judgment and is not recorded here.
    """

    session_id: str
    kind: str                      # repair_candidate
    trigger: str                   # the behavioural signal that opened it
    episodes: list[int]
    provenance: list[Provenance]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_line(self) -> str:
        return dumps(self.to_dict())


@dataclass(slots=True)
class Finding:
    """An inspectable turn or sequence.

    `observed` holds counts and spans produced by the scan layer. `labels` holds
    every interpretation. The two key sets must stay disjoint — `check()`
    enforces it, and a test calls `check()` on the canonical field lists.
    """

    id: str
    observed: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    provenance: list[Provenance] = field(default_factory=list)

    def check(self) -> None:
        overlap = set(self.observed) & set(self.labels)
        if overlap:
            raise ValueError(
                f"observed and labels share {sorted(overlap)}; "
                "an interpretation may not occupy an observation's key"
            )

    def to_dict(self) -> dict:
        self.check()
        return asdict(self)

    def to_line(self) -> str:
        return dumps(self.to_dict())


def dumps(obj) -> str:
    """One deterministic JSON line. Sorted keys at every level, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def blank_turn(adapter: str, path: str, line: int, sha: str, session_id: str,
               turn_id: str, role: str, source_type: str = "") -> dict:
    """The keyword payload for a Turn with every field at its zero value.

    Adapters fill what their format carries and leave the rest alone, so a field
    a vendor does not record reads as absent rather than as zero-with-meaning.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "role": role,
        "source_type": source_type,
        "ts": "",
        "model": "",
        "version": "",
        "effort": "",
        "cwd": "",
        "kinds": dict.fromkeys(KINDS, 0),
        "chars": {"text": 0, "thinking": 0, "signature": 0},
        "usage": dict.fromkeys(TOKEN_KEYS, 0),
        "invariants": dict.fromkeys(INVARIANTS, ""),
        "tools": {},
        "files": {},
        "flags": dict.fromkeys(FLAGS, False),
        "text": "",
        "provenance": Provenance(adapter, path, line, sha, session_id, turn_id),
    }
