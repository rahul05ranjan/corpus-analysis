"""Claude Code JSONL: one file per session under `<root>/<project>/<id>.jsonl`.

Subagent transcripts live at `<project>/<id>/subagents/agent-*.jsonl` and are a
substantial share of a working corpus. A reader that globs one level returns
only parent sessions and attributes none of that work to anyone, so they are
enumerated separately and attributed to the session that dispatched them.

Reasoning text is not in this format. Every `thinking` block carries an empty
`thinking` field and an encrypted `signature`, so depth is measurable three
ways — whether a turn reasoned at all, its `output_tokens`, and signature
length. The first two are counted; the third is a proxy and is labelled as one
wherever it is printed.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from ..records import KINDS, TOKEN_KEYS, Turn, blank_turn
from .base import SchemaDrift, SessionRef, bounded, parsed, sorted_counts

name = "claude"

#: Record types this adapter was written against. `probe()` fails when none of
#: them appears, which is the difference between an unreadable store and a quiet
#: one.
KNOWN_TYPES = {
    "assistant", "user", "system", "attachment", "mode", "permission-mode",
    "ai-title", "last-prompt", "queue-operation", "file-history-delta",
    "file-history-snapshot", "agent-name",
}

#: Tool calls that write a file. Their input carries an absolute path and fires
#: once per write, which is what makes per-file churn countable.
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

#: Undo-shaped shell commands. A behavioural signal, not a lexical one: this
#: matches what the agent ran, not what anyone said about it. Kept narrow —
#: `rm` and `git clean` discard work that was never committed, which is
#: ordinary cleanup rather than a reversal.
REVERT_RE = re.compile(r"\bgit\s+(?:reset|revert|restore|checkout|stash)\b")

#: `promptSource` values that mean the operator produced this text. `system`
#: and `sdk` are the harness driving itself; absent is normal on older releases
#: and falls through to the content rules below.
TYPED_SOURCES = {None, "typed", "queued", "suggestion_accepted"}

#: The harness talking to itself through the user channel. Counting these as
#: operator input would inflate typed volume with text nobody wrote.
NOT_TYPED = re.compile(
    r"<command-name>|<local-command-stdout>|<local-command-caveat>|"
    r"<system-reminder>|\[Request interrupted"
)

#: A continuation summary injected when a session runs out of context. It is
#: prose in a user record with no harness markup, so it passes NOT_TYPED and
#: reads as a typed prompt — which opens a spurious episode and attributes the
#: turns after a compaction to an instruction the operator never gave.
#: `isCompactSummary` is the flag; this pattern is the fallback for releases
#: that do not set it.
CONTINUATION = re.compile(
    r"^\s*(?:<[^>]+>\s*)?This session is being continued from a previous "
    r"conversation"
)


def default_root() -> Path:
    return Path.home() / ".claude" / "projects"


def sessions(root: Path | None = None, include_subagents: bool = True) -> list[SessionRef]:
    """Every session under `root`, parents first, each subagent after its parent."""
    root = Path(root) if root else default_root()
    out: list[SessionRef] = []
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*/*.jsonl")):
        ref = SessionRef(name, path.stem, str(path), project=path.parent.name)
        out.append(ref)
        if include_subagents:
            out.extend(subagents(ref))
    return out


def subagents(ref: SessionRef) -> list[SessionRef]:
    """Subagent transcripts, attributed to the session that dispatched them."""
    parent = Path(ref.path)
    d = parent.parent / parent.stem / "subagents"
    if not d.is_dir():
        return []
    return [
        SessionRef(name, p.stem, str(p), project=ref.project, parent=ref.session_id)
        for p in sorted(d.glob("agent-*.jsonl"))
    ]


def probe(ref: SessionRef, limit: int = 200) -> None:
    """Raise `SchemaDrift` when the file carries none of the known record types."""
    seen: set[str] = set()
    for n, (_i, _sha, rec) in enumerate(parsed(Path(ref.path))):
        seen.add(str(rec.get("type")))
        if seen & KNOWN_TYPES:
            return
        if n >= limit:
            break
    if not seen:
        return  # an empty or unreadable file is not drift
    raise SchemaDrift(
        f"{ref.path}: no known record type in the first {limit} records; "
        f"saw {sorted(seen)[:6]}"
    )


def typed_text(rec: dict) -> str:
    """The text the operator typed in this record, or "".

    Three exclusions in order of authority: the harness's own flags, the
    `promptSource` field when the release sets it, and the content rules that
    cover releases that do not.
    """
    if rec.get("type") != "user":
        return ""
    if rec.get("isMeta") or rec.get("isCompactSummary"):
        return ""
    if rec.get("isVisibleInTranscriptOnly") or rec.get("interruptedMessageId"):
        return ""
    if rec.get("promptSource") not in TYPED_SOURCES:
        return ""

    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return ""
        content = "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        return ""
    if NOT_TYPED.search(content) or CONTINUATION.match(content):
        return ""
    return content


def turns(ref: SessionRef) -> Iterator[Turn]:
    """Every record in one session, normalised."""
    path = Path(ref.path)
    for i, sha, rec in parsed(path):
        rtype = str(rec.get("type") or "")
        role = {"assistant": "assistant", "user": "user"}.get(rtype, "event")
        t = blank_turn(
            name, str(path), i, sha, ref.session_id,
            str(rec.get("uuid") or f"{ref.session_id}:{i}"), role, rtype,
        )
        t["ts"] = str(rec.get("timestamp") or "")
        t["version"] = str(rec.get("version") or "")
        t["effort"] = str(rec.get("effort") or "")
        t["cwd"] = str(rec.get("cwd") or "")
        t["flags"]["sidechain"] = bool(rec.get("isSidechain") or ref.parent)

        if rtype == "assistant":
            _assistant(rec, t)
        elif rtype == "user":
            _user(rec, t)
        elif rtype == "queue-operation":
            t["flags"]["queued"] = rec.get("operation") == "enqueue"

        yield Turn(**t)


def _assistant(rec: dict, t: dict) -> None:
    msg = rec.get("message") or {}
    t["model"] = str(msg.get("model") or "")
    kinds = Counter()
    tools: Counter = Counter()
    files: Counter = Counter()

    for b in msg.get("content") or []:
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        if btype == "thinking":
            kinds["thinking"] += 1
            t["chars"]["thinking"] += len(b.get("thinking") or "")
            t["chars"]["signature"] += len(b.get("signature") or "")
        elif btype == "text":
            kinds["text"] += 1
            t["chars"]["text"] += len(b.get("text") or "")
        elif btype == "tool_use":
            kinds["tool_use"] += 1
            tool = str(b.get("name") or "?")
            tools[tool] += 1
            inp = b.get("input") or {}
            if tool in WRITE_TOOLS:
                fp = inp.get("file_path")
                if fp:
                    files[str(fp)] += 1
            cmd = inp.get("command")
            if isinstance(cmd, str) and REVERT_RE.search(cmd):
                t["flags"]["revert"] = True
        elif btype == "image":
            kinds["image"] += 1
        else:
            kinds["other"] += 1

    usage = msg.get("usage") or {}
    for k in TOKEN_KEYS:
        t["usage"][k] = int(usage.get(k) or 0)
    for k in t["invariants"]:
        t["invariants"][k] = str(usage.get(k) or "")
    for k in KINDS:
        t["kinds"][k] = kinds.get(k, 0)
    t["tools"] = sorted_counts(tools)
    t["files"] = sorted_counts(files)


def _user(rec: dict, t: dict) -> None:
    t["flags"]["meta"] = bool(rec.get("isMeta"))
    t["flags"]["compact_summary"] = bool(rec.get("isCompactSummary"))
    t["flags"]["interrupted"] = bool(rec.get("interruptedMessageId"))
    t["flags"]["denied"] = bool(rec.get("toolDenialKind"))

    content = (rec.get("message") or {}).get("content")
    kinds = Counter()
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype == "tool_result":
                kinds["tool_result"] += 1
                if b.get("is_error"):
                    t["flags"]["error"] = True
            elif btype == "text":
                kinds["text"] += 1
                t["chars"]["text"] += len(b.get("text") or "")
            elif btype == "image":
                kinds["image"] += 1
            else:
                kinds["other"] += 1
    elif isinstance(content, str):
        kinds["text"] += 1
        t["chars"]["text"] += len(content)

    for k in KINDS:
        t["kinds"][k] = kinds.get(k, 0)

    text = typed_text(rec)
    if text:
        t["flags"]["typed"] = True
        t["text"] = bounded(text)
