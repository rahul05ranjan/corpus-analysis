"""Provider-neutral VS Code ``chatSessions`` files.

The file format establishes a workspace-scoped request history, not a provider.
This adapter intentionally makes no Copilot, Cursor, Gemini, or OpenAI claim.
``chatEditingSessions`` is a separate edit-state source family and is excluded.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..records import Turn, blank_turn, dumps
from .base import SchemaDrift, SessionRef, bounded

name = "vscode_chat"
records_cwd = False


def default_root() -> Path:
    return Path.home() / ".config" / "Code" / "User" / "workspaceStorage"


def sessions(root: Path | None = None) -> list[SessionRef]:
    root = Path(root) if root else default_root()
    if not root.is_dir():
        return []
    out = []
    paths = sorted(root.rglob("chatSessions/*.json")) + sorted(root.rglob("chatSessions/*.jsonl"))
    for path in paths:
        raw = path.read_bytes()
        workspace = str(path.parent.parent.relative_to(root))
        # Physical identity: the session id covers the file's bytes, so a
        # conversation gets a new id every time VS Code appends to it. A
        # `corpus-audit freeze <session_id>` therefore stops resolving once the
        # session is written to again. The alternative — keying on the filename
        # alone — would silently merge two divergent histories under one id.
        sid = hashlib.sha256(
            workspace.encode() + b"\0" + path.stem.encode() + b"\0" + hashlib.sha256(raw).digest()
        ).hexdigest()
        out.append(SessionRef(name, sid, str(path), project=workspace))
    return out


def _session(ref: SessionRef) -> dict:
    try:
        raw = Path(ref.path).read_text(encoding="utf-8")
        obj = json.loads(raw) if Path(ref.path).suffix == ".json" else _jsonl_session(ref.path, raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SchemaDrift(f"{ref.path}: invalid JSON") from e
    if not isinstance(obj, dict) or not isinstance(obj.get("requests"), list):
        seen = sorted(obj)[:6] if isinstance(obj, dict) else type(obj).__name__
        raise SchemaDrift(f"{ref.path}: expected session requests; keys are {seen}")
    for index, request in enumerate(obj["requests"]):
        if not isinstance(request, dict):
            raise SchemaDrift(f"{ref.path}: request {index} is not an object")
        message, response = request.get("message"), request.get("response")
        if not isinstance(message, dict) or not isinstance(message.get("text"), str):
            raise SchemaDrift(
                f"{ref.path}: request {index} message shape "
                f"{type(message).__name__}, text "
                f"{type(message.get('text')).__name__ if isinstance(message, dict) else '-'}")
        if not isinstance(response, list) or not all(isinstance(item, dict) for item in response):
            raise SchemaDrift(
                f"{ref.path}: request {index} response shape "
                f"{type(response).__name__}")
    return obj


def _jsonl_session(path: str, raw: str) -> dict:
    """One explicit session-state value in the VS Code storage journal."""
    candidates = []
    # JSONL is framed by LF. str.splitlines() also treats Unicode separators
    # inside a JSON string as record boundaries, splitting a valid journal row.
    for row, line in enumerate(raw.split("\n")):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            raise SchemaDrift(f"{path}:{row}: invalid JSON") from e
        if not isinstance(item, dict):
            raise SchemaDrift(f"{path}:{row}: storage record")
        value = item.get("v")
        if isinstance(value, dict) and "requests" in value:
            candidates.append(value)
    if len(candidates) != 1:
        raise SchemaDrift(f"{path}: expected one session-state value, found {len(candidates)}")
    return candidates[0]


def probe(ref: SessionRef) -> None:
    _session(ref)


def _timestamp(value: object) -> str:
    if not isinstance(value, int):
        return ""
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return ""


def _response(response: list[dict]) -> tuple[int, int, int]:
    """Visible text counts; metadata messages are excluded until deduplication is proved."""
    chunks = chars = other = 0
    for item in response:
        body = item.get("value")
        if not isinstance(body, str):
            content = item.get("content")
            body = content.get("value") if isinstance(content, dict) else None
        if isinstance(body, str):
            chunks += 1
            chars += len(body)
        else:
            other += 1
    return chunks, chars, other


def turns(ref: SessionRef) -> Iterator[Turn]:
    session = _session(ref)
    for index, request in enumerate(session["requests"]):
        digest = hashlib.sha256(dumps(request).encode()).hexdigest()
        timestamp = _timestamp(request.get("timestamp"))
        user = blank_turn(name, ref.path, index * 2, digest, ref.session_id,
                          f"{Path(ref.path).stem}:{index}:user", "user", "request")
        text = request["message"]["text"]
        user["ts"], user["kinds"]["text"], user["chars"]["text"] = timestamp, 1, len(text)
        if text.strip():
            user["flags"]["typed"] = True
            user["text"] = bounded(text)
        yield Turn(**user)
        assistant = blank_turn(name, ref.path, index * 2 + 1, digest, ref.session_id,
                               f"{Path(ref.path).stem}:{index}:assistant", "assistant", "response")
        chunks, chars, other = _response(request["response"])
        assistant["ts"], assistant["kinds"]["text"], assistant["chars"]["text"] = timestamp, chunks, chars
        assistant["kinds"]["other"] = other
        yield Turn(**assistant)


def first_ts(ref: SessionRef) -> str:
    for request in _session(ref)["requests"]:
        timestamp = _timestamp(request.get("timestamp"))
        if timestamp:
            return timestamp
    return ""
