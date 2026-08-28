"""Cursor agent transcripts, one JSONL file per physical source.

This adapter deliberately reads only ``agent-transcripts``.  Cursor workspace
chat files, databases, uploads, terminals, and agent-tool state are separate
source families; treating their presence as message evidence would invent a
transcript the source does not establish.

``SessionRef.session_id`` is a physical identity, not the filename UUID.  A
transcript UUID is a lineage hint: the same UUID can occur in two projects or
in divergent histories.  The custody API below exposes those relationships;
the scan adapter retains every physical source independently.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..records import Turn, blank_turn, line_digest
from .base import SchemaDrift, SessionRef, bounded, sorted_counts

name = "cursor"


@dataclass(frozen=True, slots=True)
class PhysicalSession:
    """The identity of one retained source object."""

    physical_session_id: str
    transcript_uuid: str
    source_path: str
    source_sha256: str
    project: str
    kind: str
    parent_transcript_uuid: str | None


@dataclass(frozen=True, slots=True)
class ContentBlock:
    """A block in source order, with only its declared safe projection."""

    type: str
    text: str = ""
    tool_name: str = ""


@dataclass(frozen=True, slots=True)
class CursorRecord:
    """Cursor-specific normalized record for custody and characterization.

    ``blocks`` retains the message's order.  A lifecycle record has no blocks
    and carries its declared status instead.  This representation is separate
    from :class:`Turn`, whose aggregate projection deliberately cannot express
    a sequence of heterogeneous blocks.
    """

    physical_session_id: str
    transcript_uuid: str
    path: str
    row: int
    sha256: str
    record_type: str
    role: str
    blocks: tuple[ContentBlock, ...] = ()
    lifecycle_status: str = ""


def default_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_id(project: str, transcript_uuid: str, digest: str) -> str:
    """Stable physical identity: project provenance + UUID + source bytes."""
    return hashlib.sha256(
        f"{project}\0{transcript_uuid}\0{digest}".encode()
    ).hexdigest()


def _location(root: Path, path: Path) -> tuple[str, str]:
    """Return project provenance and parent UUID for one transcript path."""
    rel = path.relative_to(root)
    parts = rel.parts
    try:
        marker = parts.index("agent-transcripts")
    except ValueError as e:  # sessions() only calls this for matched paths.
        raise SchemaDrift(f"{path}: not below agent-transcripts") from e
    project = "/".join(parts[:marker])
    suffix = parts[marker + 1:]
    # Cursor subagents are stored below the enclosing primary UUID.
    parent = suffix[0] if len(suffix) >= 3 and "subagents" in suffix[:-1] else ""
    return project, parent


def sessions(root: Path | None = None, include_subagents: bool = True) -> list[SessionRef]:
    """Every physical JSONL object under Cursor's agent-transcript roots."""
    root = Path(root) if root else default_root()
    if not root.is_dir():
        return []
    out: list[SessionRef] = []
    for path in sorted(root.rglob("agent-transcripts/**/*.jsonl")):
        project, parent = _location(root, path)
        if parent and not include_subagents:
            continue
        digest = _sha(path)
        uuid = path.stem
        out.append(SessionRef(
            name, _source_id(project, uuid, digest), str(path),
            project=project, parent=parent,
        ))
    return out


def physical(ref: SessionRef) -> PhysicalSession:
    """Custody identity for a session ref, recomputed from its source bytes."""
    path = Path(ref.path)
    digest = _sha(path)
    return PhysicalSession(
        _source_id(ref.project, path.stem, digest), path.stem, str(path), digest,
        ref.project, "subagent" if ref.parent else "primary", ref.parent or None,
    )


def records(ref: SessionRef) -> Iterator[tuple[int, dict]]:
    """Validated raw records, preserving source row positions.

    Cursor's known shapes are intentionally closed.  A new record, role, or
    block is schema drift, not an ``other`` count: this custody surface needs a
    characterization before its semantics can enter the corpus.
    """
    try:
        with Path(ref.path).open("rb") as fh:
            for row, raw in enumerate(fh):
                if not raw.strip():
                    continue
                try:
                    rec = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise SchemaDrift(f"{ref.path}:{row}: invalid JSON") from e
                _validate(ref.path, row, rec)
                yield row, rec
    except OSError as e:
        raise SchemaDrift(f"{ref.path}: cannot read source") from e


def _validate(path: str, row: int, rec: object) -> None:
    if not isinstance(rec, dict):
        raise SchemaDrift(f"{path}:{row}: top-level {type(rec).__name__}")
    if rec.get("type") == "turn_ended":
        if set(rec) not in ({"type", "status"}, {"type", "status", "error"}):
            raise SchemaDrift(f"{path}:{row}: lifecycle keys {sorted(rec)}")
        if rec.get("status") not in {"success", "error"}:
            raise SchemaDrift(f"{path}:{row}: lifecycle status {rec.get('status')!r}")
        if "error" in rec and not isinstance(rec["error"], str):
            raise SchemaDrift(f"{path}:{row}: lifecycle error type")
        return
    if set(rec) != {"role", "message"}:
        raise SchemaDrift(f"{path}:{row}: top-level keys {sorted(rec)}")
    role = rec.get("role")
    if role not in {"user", "assistant"}:
        raise SchemaDrift(f"{path}:{row}: role {role!r}")
    message = rec.get("message")
    if not isinstance(message, dict) or set(message) != {"content"}:
        raise SchemaDrift(f"{path}:{row}: message shape")
    content = message["content"]
    if not isinstance(content, list) or not content:
        raise SchemaDrift(
            f"{path}:{row}: content "
            f"{'empty list' if isinstance(content, list) else type(content).__name__}")
    allowed = {"text"} if role == "user" else {"text", "tool_use"}
    for block in content:
        if not isinstance(block, dict):
            raise SchemaDrift(f"{path}:{row}: block {type(block).__name__}")
        btype = block.get("type")
        if btype not in allowed:
            raise SchemaDrift(f"{path}:{row}: block {btype!r}")
        if btype == "text" and not isinstance(block.get("text"), str):
            raise SchemaDrift(f"{path}:{row}: text block")
        if btype == "tool_use" and not isinstance(block.get("name"), str):
            raise SchemaDrift(f"{path}:{row}: tool_use name")


def normalized(ref: SessionRef) -> Iterator[CursorRecord]:
    """Yield custody records without turning lifecycle entries into dialogue."""
    source = physical(ref)
    try:
        raw_digests = {
            row: line_digest(raw)
            for row, raw in enumerate(Path(ref.path).read_bytes().splitlines(keepends=True))
            if raw.strip()
        }
    except OSError as e:
        raise SchemaDrift(f"{ref.path}: cannot read source") from e
    for row, rec in records(ref):
        common = dict(
            physical_session_id=source.physical_session_id,
            transcript_uuid=source.transcript_uuid,
            path=ref.path,
            row=row,
            sha256=raw_digests[row],
        )
        if rec.get("type") == "turn_ended":
            yield CursorRecord(**common, record_type="turn_ended", role="event",
                               lifecycle_status=rec["status"])
            continue
        blocks = tuple(ContentBlock(
            type=block["type"], text=block.get("text", ""),
            tool_name=block.get("name", ""),
        ) for block in rec["message"]["content"])
        yield CursorRecord(**common, record_type="message", role=rec["role"],
                           blocks=blocks)


def turns(ref: SessionRef) -> Iterator[Turn]:
    """Safe aggregate projection of each Cursor message plus lifecycle events."""
    for record in normalized(ref):
        turn = blank_turn(name, record.path, record.row, record.sha256,
                          record.physical_session_id,
                          f"{record.transcript_uuid}:{record.row}", record.role,
                          record.record_type)
        turn["flags"]["sidechain"] = bool(ref.parent)
        if record.record_type == "turn_ended":
            turn["flags"]["error"] = record.lifecycle_status == "error"
            yield Turn(**turn)
            continue
        kinds: Counter[str] = Counter()
        tools: Counter[str] = Counter()
        text: list[str] = []
        for block in record.blocks:
            kinds[block.type] += 1
            if block.type == "text":
                turn["chars"]["text"] += len(block.text)
                text.append(block.text)
            else:
                tools[block.tool_name] += 1
        turn["kinds"].update(kinds)
        turn["tools"] = sorted_counts(tools)
        if record.role == "user":
            prompt = "\n".join(text)
            if prompt.strip():
                turn["flags"]["typed"] = True
                turn["text"] = bounded(prompt)
        yield Turn(**turn)


def probe(ref: SessionRef) -> None:
    """Validate every source row; an empty transcript is not schema drift."""
    for _ in records(ref):
        pass


def lineage(refs: list[SessionRef]) -> list[dict[str, object]]:
    """Parsed-record lineage, never inferred from a filename or file size."""
    by_uuid: dict[str, list[SessionRef]] = {}
    for ref in refs:
        by_uuid.setdefault(Path(ref.path).stem, []).append(ref)
    out: list[dict[str, object]] = []
    for uuid, group in sorted(by_uuid.items()):
        group = sorted(group, key=lambda r: (r.project, r.path, r.session_id))
        if len(group) == 1:
            out.append({"relation": "UNIQUE_UUID", "uuid": uuid,
                        "physical_session_id": group[0].session_id})
            continue
        parsed = [(ref, [record for _row, record in records(ref)]) for ref in group]
        for index, (left, left_rows) in enumerate(parsed):
            for right, right_rows in parsed[index + 1:]:
                result: dict[str, object] = {
                    "uuid": uuid, "left": left.session_id, "right": right.session_id,
                }
                if left_rows == right_rows:
                    result["relation"] = "EXACT_SAME_CONTENT"
                    out.append(result)
                elif left_rows == right_rows[:len(left_rows)]:
                    result["relation"] = "PREFIX_OF"
                    out.append(result)
                    out.append({"uuid": uuid, "left": right.session_id,
                                "right": left.session_id,
                                "relation": "SUPERSEDES_PREFIX"})
                elif right_rows == left_rows[:len(right_rows)]:
                    result["relation"] = "SUPERSEDES_PREFIX"
                    out.append(result)
                    out.append({"uuid": uuid, "left": right.session_id,
                                "right": left.session_id,
                                "relation": "PREFIX_OF"})
                else:
                    result["relation"] = "SAME_UUID_DIVERGED"
                    result["first_divergence_row"] = next(
                        row for row, (a, b) in enumerate(
                            zip(left_rows, right_rows, strict=False)
                        )
                        if a != b
                    )
                    out.append(result)
    return out


def first_ts(ref: SessionRef) -> str:
    """Cursor agent transcripts do not establish timestamps in this schema."""
    return ""


records_cwd = False
