"""Copilot CLI per-session ``events.jsonl`` transcripts.

The adapter deliberately selects the event log as its one conversational source.
The captured global store has incomplete session coverage and is not merged with
these logs; session-local todo databases are ancillary state.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..records import Turn, blank_turn, line_digest
from .base import SchemaDrift, SessionRef, bounded

name = "copilot_cli"
records_cwd = False

#: The event vocabulary this adapter was written against, intentionally closed.
#: `_records` raises on the first unrecognised event rather than counting it, so
#: one new vendor event type makes every session carrying it unreadable
#: mid-iteration. A new event is drift to characterize, not an `other` count.
KNOWN = {"user.message", "assistant.message", "tool.execution_start",
         "tool.execution_complete", "assistant.turn_start", "assistant.turn_end",
         "session.start", "session.resume", "session.shutdown", "session.info",
         "session.mode_changed", "session.model_change", "session.plan_changed",
         "session.task_complete", "session.compaction_start",
         "session.compaction_complete", "subagent.started", "subagent.completed",
         "system.notification", "system.message", "skill.invoked", "hook.start",
         "hook.end", "permission.requested", "permission.completed",
         "session.error", "abort"}


def default_root() -> Path:
    return Path.home() / ".copilot"


def sessions(root: Path | None = None) -> list[SessionRef]:
    root = Path(root) if root else default_root()
    if not root.is_dir():
        return []
    return [SessionRef(name, path.parent.name, str(path), project=str(path.parent))
            for path in sorted(root.rglob("events.jsonl"))]


def _records(ref: SessionRef) -> Iterator[tuple[int, bytes, dict]]:
    try:
        with Path(ref.path).open("rb") as fh:
            for row, raw in enumerate(fh):
                if not raw.strip():
                    continue
                try:
                    item = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise SchemaDrift(f"{ref.path}:{row}: invalid JSON") from e
                if not isinstance(item, dict) or set(item) != {"id", "parentId", "timestamp", "type", "data"}:
                    seen = sorted(item)[:6] if isinstance(item, dict) else type(item).__name__
                    raise SchemaDrift(f"{ref.path}:{row}: top-level shape {seen}")
                if item["type"] not in KNOWN or not isinstance(item["data"], dict):
                    raise SchemaDrift(f"{ref.path}:{row}: event shape {item['type']!r}, "
                                      f"data {type(item['data']).__name__}")
                yield row, raw, item
    except OSError as e:
        raise SchemaDrift(f"{ref.path}: cannot read source") from e


def probe(ref: SessionRef) -> None:
    for _ in _records(ref):
        pass


def turns(ref: SessionRef) -> Iterator[Turn]:
    model = effort = ""
    for row, raw, item in _records(ref):
        event, data = item["type"], item["data"]
        if event == "session.model_change":
            model = str(data.get("newModel") or model)
            effort = str(data.get("reasoningEffort") or effort)
        role = "user" if event == "user.message" else "assistant" if event == "assistant.message" else "event"
        turn = blank_turn(name, ref.path, row, line_digest(raw), ref.session_id,
                          str(item["id"]), role, event)
        turn["ts"], turn["model"], turn["effort"] = str(item["timestamp"] or ""), model, effort
        if event == "user.message":
            body = data.get("content")
            if not isinstance(body, str):
                raise SchemaDrift(f"{ref.path}:{row}: user content {type(body).__name__}")
            turn["kinds"]["text"] = 1
            turn["chars"]["text"] = len(body)
            if body.strip():
                turn["flags"]["typed"] = True
                turn["text"] = bounded(body)
        elif event == "assistant.message":
            body = data.get("content")
            if not isinstance(body, str):
                raise SchemaDrift(f"{ref.path}:{row}: assistant content {type(body).__name__}")
            turn["kinds"]["text"] = 1
            turn["chars"]["text"] = len(body)
            reasoning = data.get("reasoningText")
            if reasoning is not None:
                if not isinstance(reasoning, str):
                    raise SchemaDrift(
                        f"{ref.path}:{row}: reasoning text {type(reasoning).__name__}")
                turn["kinds"]["thinking"] = 1
                turn["chars"]["thinking"] = len(reasoning)
            turn["usage"]["output_tokens"] = int(data.get("outputTokens") or 0)
        elif event == "tool.execution_start":
            tool = data.get("toolName")
            if not isinstance(tool, str):
                raise SchemaDrift(f"{ref.path}:{row}: tool name {type(tool).__name__}")
            turn["kinds"]["tool_use"] = 1
            turn["tools"] = {tool: 1}
        elif event == "tool.execution_complete":
            turn["kinds"]["tool_result"] = 1
            turn["flags"]["error"] = data.get("success") is False
        elif event == "abort":
            turn["flags"]["interrupted"] = True
        elif event == "session.error":
            turn["flags"]["error"] = True
        elif event.startswith("session.compaction"):
            turn["flags"]["compact_summary"] = True
        yield Turn(**turn)


def first_ts(ref: SessionRef) -> str:
    for _row, _raw, item in _records(ref):
        return str(item["timestamp"] or "")
    return ""
