"""Adapter contract: vendor format in, `Turn` + `Provenance` out.

Every adapter answers three questions and nothing else — which sessions exist,
what turns a session holds, and whether the format still looks like what this
code was written against. The third is `probe()`, and it raises rather than
degrading: the store is vendor-controlled, so a silent reshape would turn into
a corpus that reads as quiet rather than as unreadable.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..records import line_digest

#: Typed prompt text is retained for episode segmentation and user-supplied
#: lexicons. Assistant bodies are not: their size is recorded in `chars.text`,
#: and provenance re-reads the exact bytes when a fixture needs them. That keeps
#: memory flat over a corpus of any size and shrinks what a scan can leak.
MAX_TEXT = 8000


class SchemaDrift(Exception):
    """The source no longer carries what this adapter was written against."""


@dataclass(frozen=True, slots=True)
class SessionRef:
    """One session, located but not yet read."""

    adapter: str
    session_id: str
    path: str
    project: str = ""
    cwd: str = ""
    parent: str = ""    # dispatching session, when this is a subagent transcript


class Adapter(Protocol):
    name: str

    def default_root(self) -> Path: ...

    def sessions(self, root: Path) -> list[SessionRef]: ...

    def turns(self, ref: SessionRef) -> Iterator: ...

    def probe(self, ref: SessionRef) -> None: ...


def iter_lines(path: Path) -> Iterator[tuple[int, bytes]]:
    """(line_index, raw_bytes) for each non-empty line.

    Binary, because the provenance digest is over source bytes. Decoding first
    would make the hash depend on this process's error handling rather than on
    the file.
    """
    try:
        fh = path.open("rb")
    except OSError:
        return
    with fh:
        for i, raw in enumerate(fh):
            if raw.strip():
                yield i, raw


def parsed(path: Path) -> Iterator[tuple[int, str, dict]]:
    """(line_index, sha256, record) for each parseable JSON line.

    A malformed line is skipped, not fatal: a session still being written ends
    in a partial record, and refusing the file would drop everything before it.
    """
    import json

    for i, raw in iter_lines(path):
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict):
            yield i, line_digest(raw), obj


@dataclass(frozen=True, slots=True)
class Span:
    """A byte range holding one element of a JSON array file."""

    path: str
    index: int
    start: int
    end: int


def array_spans(path: Path) -> list[tuple[Span, object]]:
    """(span, element) for every top-level element of a JSON array file.

    A consumer export ships a corpus as one array rather than as a line per
    record, and its elements run large enough that re-parsing the file to reach
    one of them costs a full pass per session. Returning the byte range beside
    the element lets a caller index the file once and later re-read a single
    element with a seek.

    Offsets are in bytes because that is what a seek takes, and they accumulate
    as the scan advances, so the character-to-byte conversion costs one pass
    over the file rather than one per element.
    """
    import json

    try:
        raw = path.read_bytes()
    except OSError:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SchemaDrift(f"{path}: not utf-8 at byte {e.start}") from e

    opener = text.find("[")
    if opener < 0:
        raise SchemaDrift(f"{path}: expected a JSON array")

    decoder = json.JSONDecoder()
    limit = len(text)
    i = opener + 1
    seen_i, seen_b = i, len(text[:i].encode("utf-8"))
    out: list[tuple[Span, object]] = []

    while True:
        while i < limit and text[i] in " \t\r\n,":
            i += 1
        if i >= limit or text[i] == "]":
            return out
        seen_b += len(text[seen_i:i].encode("utf-8"))
        seen_i = i
        try:
            element, j = decoder.raw_decode(text, i)
        except json.JSONDecodeError as e:
            raise SchemaDrift(
                f"{path}: element {len(out)} does not parse: {e.msg}"
            ) from e
        end = seen_b + len(text[i:j].encode("utf-8"))
        out.append((Span(str(path), len(out), seen_b, end), element))
        seen_i, seen_b = j, end
        i = j


def read_span(span: Span) -> object:
    """Re-read one element located by `array_spans`, without parsing the file."""
    import json

    try:
        with Path(span.path).open("rb") as fh:
            fh.seek(span.start)
            raw = fh.read(span.end - span.start)
    except OSError:
        return None
    return json.loads(raw.decode("utf-8"))


def bounded(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[:limit] + " …"


def sorted_counts(counter) -> dict[str, int]:
    """Counts in a stable order: heaviest first, ties broken by name.

    Insertion order would be deterministic for one file and would differ
    between two runs that read the same records in a different sequence.
    """
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))
