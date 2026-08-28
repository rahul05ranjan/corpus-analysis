"""Claude consumer export: `<export>/conversations.json`, one JSON array.

Distinct from `claude_code`, which reads the CLI's JSONL sessions. Same
vendor, different product and schema. The two adapters share no code.

Five facts about this format decide the mapping.

**A conversation is a tree with no recorded current leaf.** Messages carry
`parent_message_uuid` and nothing else that orders them: no index, no sequence
number, no active-branch pointer. When exactly one message is nobody's parent
the thread is settled — there is one path — and the adapter walks parents from
it. When several are, the conversation **fails closed**: it reports
`ambiguous_active_branch` and emits nothing. Picking the newest leaf
would be a timing heuristic: neither array position nor timestamp is an active
branch key the schema establishes.

**`content[]` is authoritative, `text` is not.** Every message also carries a
flattened `text` field. It disagrees with the concatenation of the message's
`text` blocks in the synthetic conflict fixture. It can fold in
material the blocks keep separate, so reading it would push reasoning and tool
output into the visible answer. Canonical text comes from `text` blocks
alone.

**No supported model field is recorded.** `Turn.model` is empty for
this adapter — see `records.TOKEN_KEYS` for the rule this follows: a
whole-adapter blank means "not recorded", never "unknown model".

**Reasoning is present, and sometimes withheld in place.** A `thinking` block
carries readable prose, unlike the CLI format where it is always empty beside a
signature. A `thinking_hidden` block carries no text, so withheld
reasoning is counted separately in diagnostics rather than left to read as
absent reasoning.

**Three artifacts here are not dialogue.** `memories.json`, `projects/*.json`,
and `reflections/*.json` are counted structurally and never become turns:
project instructions and memory text are standing context, and letting either
open an episode would attribute work to an instruction nobody typed.
`users.json` and `login_history.json` are account records and are never opened
at all.

Provenance follows the same departure the other array-shaped export documents:
the file is one minified array, so `line` is the message's position in the
thread, `turn_id` is the message uuid, and the digest is over the message's
canonical serialization —
`sha256(records.dumps(message))` — reproducible from the export without this
tool.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..records import Turn, blank_turn, dumps
from .base import SchemaDrift, SessionRef, Span, array_spans, bounded, read_span, sorted_counts

name = "claude_export"

#: This format records no working directory. Without the declaration
#: `scan.sessions.meta` cannot take its fast path.
records_cwd = False

#: The whole observed sender vocabulary. Tool and reasoning blocks live inside
#: assistant messages here, so no sender names them.
ROLES = {"human": "user", "assistant": "assistant"}

#: Content-block types this adapter was written against.
KNOWN_BLOCKS = {"text", "thinking", "tool_use", "tool_result"}

#: Tool calls that write a file, and the input keys that name it. Their inputs
#: carry a path and fire once per write, which is what makes per-file churn
#: countable.
WRITE_TOOLS = {"create_file", "str_replace", "memory_write", "memory_str_replace",
               "memory_append"}
PATH_KEYS = ("path", "file_path", "filename")

#: Undo-shaped shell commands, matched against what the agent ran rather than
#: against anything anyone said. Same rule as `claude_code`, `codex` and
#: `opencode`.
REVERT_RE = re.compile(r"\bgit\s+(?:reset|revert|restore|checkout|stash)\b")

#: Upload classification. Buckets are this adapter's own vocabulary, never the
#: source's: a file's name is private, so its extension decides a bucket and
#: then goes no further. Nothing in this format carries file content, so no
#: media payload can reach a record even in principle.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif",
                  ".tiff", ".svg", ".heic", ".heif", ".avif"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".oga", ".flac", ".aac",
                  ".opus", ".aiff", ".wma"}

#: Account records. Named so the promise not to read them is checkable, and so
#: a later reader does not add them to the scan by reflex.
NEVER_READ = ("users.json", "login_history.json")


class _Diagnostics:
    """Content-neutral aggregates for one scan.

    Counts only. Unlike a schema whose discriminators are a closed vendor enum,
    an unknown value here may itself be private text, so no source value is
    echoed — an unknown block type increments a counter and is inspected
    locally, never routed into output.
    """

    __slots__ = ("counts", "skipped", "errors")

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.counts: Counter = Counter()
        self.skipped: Counter = Counter()
        self.errors: Counter = Counter()


_DIAG = _Diagnostics()


def diagnostics() -> dict[str, dict[str, int]]:
    """What the last scan counted, skipped, and failed on. Sorted on the way out."""
    return {
        "counts": sorted_counts(_DIAG.counts),
        "skipped_content": sorted_counts(_DIAG.skipped),
        "errors": sorted_counts(_DIAG.errors),
    }


# --------------------------------------------------------------------------
# Locating conversations
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Conv:
    """One conversation, located in its export but not yet read."""

    span: Span
    uuid: str
    created_at: str
    digest: str     # canonical serialization digest, for conflict detection


_INDEX: dict[str, list[_Conv]] = {}
_CONVS: dict[str, _Conv] = {}
_CONFLICTED: set[str] = set()


def default_root() -> Path:
    return Path.home() / "corpus" / "claude"


def _exports(root: Path) -> list[Path]:
    """`conversations.json` at the root, or one per export directory under it."""
    return sorted({*root.glob("conversations.json"), *root.glob("*/conversations.json")})


def _index(path: Path) -> list[_Conv]:
    key = str(path)
    if key not in _INDEX:
        out: list[_Conv] = []
        for span, element in array_spans(path):
            if not isinstance(element, dict):
                _DIAG.errors["malformed_conversation"] += 1
                continue
            out.append(_Conv(
                span,
                str(element.get("uuid") or f"{path.parent.name}:{span.index}"),
                str(element.get("created_at") or ""),
                hashlib.sha256(dumps(element).encode("utf-8")).hexdigest(),
            ))
        _INDEX[key] = out
    return _INDEX[key]


def _context_counts(export: Path) -> None:
    """Structural counts for the artifacts that are not dialogue.

    Read for their shape and never for their text. `users.json` and
    `login_history.json` are not opened at all.
    """
    import json

    for name_ in NEVER_READ:
        if (export / name_).exists():
            _DIAG.counts["account_files_present_and_unread"] += 1

    memories = export / "memories.json"
    if memories.exists():
        try:
            body = json.loads(memories.read_bytes())
        except (OSError, ValueError):
            _DIAG.errors["malformed_memories"] += 1
        else:
            _DIAG.counts["memory_records_discovered"] += len(
                body if isinstance(body, list) else [body])

    for kind, pattern in (("project", "projects/*.json"),
                          ("reflection", "reflections/*.json")):
        for path in sorted(export.glob(pattern)):
            try:
                body = json.loads(path.read_bytes())
            except (OSError, ValueError):
                _DIAG.errors[f"malformed_{kind}"] += 1
                continue
            _DIAG.counts[f"{kind}_records_discovered"] += 1
            if kind == "project" and isinstance(body, dict):
                _DIAG.counts["project_docs_discovered"] += len(body.get("docs") or [])


def sessions(root: Path | None = None, include_subagents: bool = True) -> list[SessionRef]:
    """One session per conversation, across every export under `root`.

    `root` is an export directory or a directory of them. A conversation uuid
    that repeats is kept once when the two records serialize identically. When
    they do not, the repeat is counted as `duplicate_conflict`; the
    conversation is still enumerated as a session, and `turns()` emits nothing
    for it. File order is not version authority, and this schema records none,
    so no winner is picked.
    """
    root = Path(root) if root else default_root()
    _DIAG.reset()
    _CONVS.clear()
    _CONFLICTED.clear()
    if not root.is_dir():
        return []

    exports = _exports(root)
    _DIAG.counts["files_scanned"] = len(exports)
    for path in exports:
        _context_counts(path.parent)
        for conv in _index(path):
            _DIAG.counts["conversations_discovered"] += 1
            seen = _CONVS.get(conv.uuid)
            if seen is None:
                _CONVS[conv.uuid] = conv
            elif seen.digest == conv.digest:
                _DIAG.counts["duplicate_conversation_ids"] += 1
            else:
                _DIAG.errors["duplicate_conflict"] += 1
                _CONFLICTED.add(conv.uuid)

    # Conversations linked to a project: this export records no link field on a
    # conversation, so the count is zero by structure rather than by absence of
    # projects. Stated as a figure so a reader does not read silence as none.
    _DIAG.counts["conversation_project_links"] = 0

    return sorted(
        (SessionRef(name, uuid, conv.span.path, project=Path(conv.span.path).parent.name)
         for uuid, conv in _CONVS.items()),
        key=lambda ref: ref.session_id,
    )


def _conv_for(ref: SessionRef) -> _Conv | None:
    conv = _CONVS.get(ref.session_id)
    if conv is not None and conv.span.path == ref.path:
        return conv
    for candidate in _index(Path(ref.path)):
        if candidate.uuid == ref.session_id:
            return candidate
    return None


def _messages(conv: _Conv) -> list | None:
    body = read_span(conv.span)
    if not isinstance(body, dict):
        return None
    messages = body.get("chat_messages")
    return messages if isinstance(messages, list) else None


def first_ts(ref: SessionRef) -> str:
    """The conversation's own creation time, read from the index."""
    conv = _conv_for(ref)
    return conv.created_at if conv else ""


def probe(ref: SessionRef) -> None:
    """Raise `SchemaDrift` when a conversation carries no readable message list."""
    conv = _conv_for(ref)
    if conv is None:
        raise SchemaDrift(f"{ref.path}: no conversation {ref.session_id!r}")
    messages = _messages(conv)
    if messages is None:
        body = read_span(conv.span)
        seen = sorted(body)[:6] if isinstance(body, dict) else type(body).__name__
        raise SchemaDrift(
            f"{ref.path}: conversation carries no `chat_messages` list; "
            f"keys are {seen}"
        )
    if not any(isinstance(m, dict) and "sender" in m and "content" in m
               for m in messages):
        raise SchemaDrift(
            f"{ref.path}: no message carries `sender` and `content`; "
            "the record shape this adapter reads is gone"
        )


# --------------------------------------------------------------------------
# Thread reconstruction
# --------------------------------------------------------------------------


def _thread(messages: list) -> tuple[list[dict], str]:
    """The one unambiguous root-first thread, and how it was established.

    Fails closed rather than choosing. A conversation with several tips has
    several readings and this schema records no pointer to the one the reader
    saw; emitting a plausible truncation would put an abandoned branch into
    canonical history looking exactly like the real thing.
    """
    by_uuid: dict[str, dict] = {}
    for m in messages:
        if isinstance(m, dict) and m.get("uuid"):
            by_uuid[str(m["uuid"])] = m
    if not by_uuid:
        return [], "no_messages"

    parents = {str(m.get("parent_message_uuid") or "") for m in by_uuid.values()}
    tips = sorted(uuid for uuid in by_uuid if uuid not in parents)
    if len(tips) != 1:
        return [], "ambiguous"

    chain: list[dict] = []
    walked: set[str] = set()
    node = tips[0]
    while node in by_uuid:
        if node in walked:
            return [], "cycle"
        walked.add(node)
        chain.append(by_uuid[node])
        node = str(by_uuid[node].get("parent_message_uuid") or "")
    chain.reverse()

    if len(chain) != len(by_uuid):
        # A single tip with unreachable messages means a cycle or a second root
        # hiding behind one. Neither has a safe reading.
        return [], "unreachable"
    return chain, "sole_tip"


def turns(ref: SessionRef) -> Iterator[Turn]:
    """One conversation's thread, root first, as canonical turns."""
    conv = _conv_for(ref)
    if conv is None:
        _DIAG.errors["malformed_conversation"] += 1
        return
    if ref.session_id in _CONFLICTED:
        return
    messages = _messages(conv)
    if messages is None:
        _DIAG.errors["missing_conversation_messages"] += 1
        return

    _DIAG.counts["messages_discovered"] += len(messages)
    chain, how = _thread(messages)
    if how != "sole_tip":
        _DIAG.errors[{"ambiguous": "ambiguous_active_branch",
                      "cycle": "branch_cycle",
                      "unreachable": "unreachable_messages",
                      "no_messages": "missing_conversation_messages"}[how]] += 1
        return

    _DIAG.counts["conversations_emitted"] += 1
    _DIAG.counts["branch_resolved_by_sole_tip"] += 1

    for position, message in enumerate(chain):
        yield _turn(ref, conv, position, message)


# --------------------------------------------------------------------------
# One message -> one Turn
# --------------------------------------------------------------------------


def _turn(ref: SessionRef, conv: _Conv, position: int, message: dict) -> Turn:
    source_role = str(message.get("sender") or "")
    role = ROLES.get(source_role)
    if role is None:
        _DIAG.errors["unsupported_role"] += 1
        role = "event"

    t = blank_turn(name, conv.span.path, position, _digest(message), ref.session_id,
                   str(message.get("uuid") or f"{ref.session_id}:{position}"),
                   role, source_role)
    t["ts"] = _timestamp(message.get("created_at"))

    body = _blocks(message.get("content"), t)
    _uploads(message, t)

    if role == "user" and body.strip():
        t["flags"]["typed"] = True
        t["text"] = bounded(body)
        _DIAG.counts["typed_prompts"] += 1

    if t["kinds"]["text"]:
        _DIAG.counts[f"{role}_text_turns"] += 1
    if role == "assistant":
        # No model field exists in this format, so this counter is the whole
        # corpus. Recorded anyway: a reader comparing adapters needs the zero.
        _DIAG.counts["model_identity_absent"] += 1

    return Turn(**t)


def _digest(message: dict) -> str:
    """sha256 over the message's canonical serialization.

    The export is one minified array, so a message has no source line to hash.
    `records.dumps` sorts every key at every level, which makes this
    reproducible from the export without this tool.
    """
    return hashlib.sha256(dumps(message).encode("utf-8")).hexdigest()


def _timestamp(value: object) -> str:
    """Source timestamps pass through. A non-string is reported, not repaired."""
    if value is None:
        return ""
    if isinstance(value, str) and value:
        return value
    _DIAG.errors["malformed_timestamp"] += 1
    return ""


def _blocks(content: object, t: dict) -> str:
    """Visible conversation text from a message's content blocks.

    Reasoning and tool traffic are counted in their own fields and never join
    the returned text: folding them in would put internal state into the
    visible answer and into any prompt statistic built on it.
    """
    kept: list[str] = []
    if not isinstance(content, list):
        if content is not None:
            _DIAG.errors["unknown_content_type"] += 1
            t["kinds"]["other"] += 1
        return ""

    for block in content:
        if not isinstance(block, dict):
            _DIAG.errors["unknown_content_type"] += 1
            t["kinds"]["other"] += 1
            continue
        btype = str(block.get("type") or "")

        if btype == "text":
            text = str(block.get("text") or "")
            t["kinds"]["text"] += 1
            t["chars"]["text"] += len(text)
            if text:
                kept.append(text)
        elif btype == "thinking":
            t["kinds"]["thinking"] += 1
            t["chars"]["thinking"] += len(str(block.get("thinking") or ""))
            t["chars"]["signature"] += len(str(block.get("signature") or ""))
            if block.get("thinking_hidden") or block.get("hidden"):
                # Withheld in place. `chars.thinking` cannot distinguish this
                # from a short thought, so the distinction is kept here.
                _DIAG.counts["thinking_blocks_withheld"] += 1
            else:
                _DIAG.counts["thinking_blocks_readable"] += 1
        elif btype == "tool_use":
            _tool_use(block, t)
        elif btype == "tool_result":
            t["kinds"]["tool_result"] += 1
            _DIAG.counts["tool_results"] += 1
            if block.get("is_error"):
                t["flags"]["error"] = True
        else:
            # Counted, never echoed: an unknown type here may carry private text.
            t["kinds"]["other"] += 1
            _DIAG.errors["unknown_content_type"] += 1

    return "\n".join(kept)


def _tool_use(block: dict, t: dict) -> None:
    """A tool call, identified by the block's own `name` rather than by its text."""
    tool = str(block.get("name") or "?")
    t["kinds"]["tool_use"] += 1
    _DIAG.counts["tool_calls"] += 1
    tools = Counter(t["tools"])
    tools[tool] += 1
    t["tools"] = sorted_counts(tools)

    payload = block.get("input")
    if not isinstance(payload, dict):
        return
    command = payload.get("command")
    if isinstance(command, str) and REVERT_RE.search(command):
        t["flags"]["revert"] = True
    if tool not in WRITE_TOOLS:
        return
    files = Counter(t["files"])
    for key in PATH_KEYS:
        target = payload.get(key)
        if isinstance(target, str) and target:
            files[target] += 1
            break
    if files:
        t["files"] = sorted_counts(files)


def _uploads(message: dict, t: dict) -> None:
    """Attachments and files: counted, never read.

    An attachment carries `extracted_content`, the text of a file the operator
    uploaded. It is not typed conversational input, and adding it to canonical
    text would charge a whole document to a prompt nobody wrote. A file carries
    no content at all — only a name, which stays private, and an extension,
    which chooses a bucket and is then discarded.
    """
    attachments = message.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if isinstance(attachment, dict):
                t["kinds"]["other"] += 1
                _DIAG.skipped["attachment"] += 1

    files = message.get("files")
    if not isinstance(files, list):
        return
    for entry in files:
        if not isinstance(entry, dict):
            continue
        suffix = Path(str(entry.get("file_name") or "")).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            t["kinds"]["image"] += 1
            _DIAG.skipped["image"] += 1
        elif suffix in AUDIO_SUFFIXES:
            t["kinds"]["other"] += 1
            _DIAG.skipped["audio"] += 1
        else:
            t["kinds"]["other"] += 1
            _DIAG.skipped["other_upload"] += 1
