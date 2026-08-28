"""OpenCode: a SQLite store, not a file per session.

Opened `file:...?mode=ro` through a URI so the connection cannot write, against
a database a running server may be writing to. Three tables are read — session,
message, part. `account` and `credential` are in the same file and hold live
tokens; they are named here so the fact is on the record, and they are never
queried.

**Provenance addresses a row, not a line.** `line` is the message row's rowid
and the digest is over that row's `data` column, so a record re-reads with:

    select data from message where rowid = <line>

Parts are joined on `message_id` and are not covered by the digest, which is
why the digest names the message record rather than the assembled turn.

**Delegation is where the work is.** A parent session that hands off holds the
handoff and little else, while its children hold the tool calls. Child sessions
are enumerated as their own sessions with `parent` set, which is the same
treatment subagent transcripts get in other formats.

Reasoning parts here carry text. `chars.thinking` is therefore non-zero for
this format and zero for formats that withhold it — a difference between
vendors, not between models.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..records import Turn, blank_turn, line_digest
from .base import SchemaDrift, SessionRef, bounded, sorted_counts

name = "opencode"

REQUIRED_TABLES = {"session", "message", "part"}
EDIT_TOOLS = {"edit", "write", "patch", "multiedit"}
REVERT_RE = re.compile(r"\bgit\s+(?:reset|revert|restore|checkout|stash)\b")

#: Depth of the delegation walk. `parent_id` is a column, and a cycle in it
#: would hang an enumeration that trusted it.
MAX_DEPTH = 4

_CONNECTIONS: dict[str, sqlite3.Connection] = {}


def default_root() -> Path:
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _connect(db: Path) -> sqlite3.Connection | None:
    key = str(db)
    con = _CONNECTIONS.get(key)
    if con is not None:
        return con
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5,
                              check_same_thread=False)
    except sqlite3.Error:
        return None
    _CONNECTIONS[key] = con
    return con


def _iso(ms) -> str:
    """Epoch milliseconds to ISO 8601, so every adapter emits one time format."""
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return ""


def sessions(root: Path | None = None, include_subagents: bool = True) -> list[SessionRef]:
    db = Path(root) if root else default_root()
    con = _connect(db)
    if con is None:
        return []
    try:
        rows = con.execute(
            "select id, directory, parent_id, time_created from session "
            "order by time_created, id"
        ).fetchall()
    except sqlite3.Error:
        return []

    parents = {r[0] for r in rows if not r[2]}
    out: list[SessionRef] = []
    for sid, directory, parent_id, _created in rows:
        if parent_id and not include_subagents:
            continue
        out.append(SessionRef(
            name, str(sid), str(db),
            project=Path(str(directory or "")).name,
            cwd=str(directory or ""),
            parent=str(parent_id) if parent_id and parent_id in parents else "",
        ))
    return out


def probe(ref: SessionRef) -> None:
    con = _connect(Path(ref.path))
    if con is None:
        raise SchemaDrift(f"{ref.path}: no readable database")
    have = {r[0] for r in con.execute(
        "select name from sqlite_master where type='table'")}
    missing = REQUIRED_TABLES - have
    if missing:
        raise SchemaDrift(f"{ref.path}: missing table(s) {sorted(missing)}")


def first_ts(ref: SessionRef) -> str:
    """From the session row, with no message scan."""
    con = _connect(Path(ref.path))
    if con is None:
        return ""
    try:
        row = con.execute("select time_created from session where id = ?",
                          (ref.session_id,)).fetchone()
    except sqlite3.Error:
        return ""
    return _iso(row[0]) if row else ""


def turns(ref: SessionRef) -> Iterator[Turn]:
    """One turn per message row, with its parts folded in."""
    db = Path(ref.path)
    con = _connect(db)
    if con is None:
        return
    try:
        messages = con.execute(
            "select rowid, id, data from message where session_id = ? "
            "order by time_created, rowid", (ref.session_id,)).fetchall()
    except sqlite3.Error:
        return

    for rowid, msg_id, data in messages:
        try:
            msg = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            continue
        role = str(msg.get("role") or "event")
        t = blank_turn(name, str(db), int(rowid),
                       line_digest(str(data).encode("utf-8")),
                       ref.session_id, str(msg_id), role, "message")
        t["ts"] = _iso((msg.get("time") or {}).get("created"))
        t["cwd"] = ref.cwd
        t["model"] = str(msg.get("modelID") or "")
        t["effort"] = str(msg.get("agent") or "")   # its "agent" is the role
        t["version"] = str(msg.get("providerID") or "")
        _usage(msg.get("tokens") or {}, t)
        _parts(con, ref.session_id, str(msg_id), t, role)
        yield Turn(**t)


def _usage(tokens: dict, t: dict) -> None:
    cache = tokens.get("cache") or {}
    t["usage"]["input_tokens"] = int(tokens.get("input") or 0)
    t["usage"]["output_tokens"] = int(tokens.get("output") or 0)
    t["usage"]["reasoning_output_tokens"] = int(tokens.get("reasoning") or 0)
    t["usage"]["cache_read_input_tokens"] = int(cache.get("read") or 0)
    t["usage"]["cache_creation_input_tokens"] = int(cache.get("write") or 0)


def _parts(con: sqlite3.Connection, session_id: str, message_id: str,
           t: dict, role: str) -> None:
    try:
        rows = con.execute(
            "select data from part where session_id = ? and message_id = ? "
            "order by time_created, rowid", (session_id, message_id)).fetchall()
    except sqlite3.Error:
        return

    tools: dict[str, int] = {}
    files: dict[str, int] = {}
    text_parts: list[str] = []

    for (data,) in rows:
        try:
            p = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            continue
        ptype = p.get("type")

        if ptype == "text":
            body = str(p.get("text") or "")
            t["kinds"]["text"] += 1
            t["chars"]["text"] += len(body)
            if body.strip() and not p.get("synthetic"):
                text_parts.append(body)
        elif ptype == "reasoning":
            t["kinds"]["thinking"] += 1
            t["chars"]["thinking"] += len(str(p.get("text") or ""))
        elif ptype == "tool":
            t["kinds"]["tool_use"] += 1
            tool = str(p.get("tool") or "?")
            tools[tool] = tools.get(tool, 0) + 1
            state = p.get("state") or {}
            if state.get("status") == "error":
                t["flags"]["error"] = True
            inp = state.get("input") or {}
            if isinstance(inp, dict):
                if tool in EDIT_TOOLS:
                    fp = inp.get("filePath") or inp.get("path")
                    if fp:
                        files[str(fp)] = files.get(str(fp), 0) + 1
                cmd = inp.get("command")
                if isinstance(cmd, str) and REVERT_RE.search(cmd):
                    t["flags"]["revert"] = True
        elif ptype == "patch":
            for fp in p.get("files") or []:
                files[str(fp)] = files.get(str(fp), 0) + 1
        elif ptype == "compaction":
            t["flags"]["compact_summary"] = True
        elif ptype in ("step-start", "step-finish"):
            continue
        else:
            t["kinds"]["other"] += 1

    t["tools"] = sorted_counts(tools)
    t["files"] = sorted_counts(files)

    if role == "user" and text_parts and not t["flags"]["compact_summary"]:
        t["flags"]["typed"] = True
        t["text"] = bounded("\n".join(text_parts))


def close() -> None:
    """Release cached connections. Tests call this; the CLI is short-lived."""
    for con in _CONNECTIONS.values():
        con.close()
    _CONNECTIONS.clear()
