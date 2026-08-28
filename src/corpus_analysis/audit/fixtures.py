"""Freeze a naturalistic sequence into a replayable experiment.

A fixture holds the evidence bytes, the prompt, the model-facing config, the
measurement target, and the provenance of every span. It freezes bytes rather
than pointing at them, because the store it came from is vendor-controlled: a
format reshape or a deleted session must not invalidate a measurement already
taken.

`verify()` is the other half of that. It re-reads each span from its source and
reports drift. Drift does not invalidate the fixture — the frozen bytes are the
subject — it records that the corpus and the fixture have diverged.

`replay()` renders the model-facing payload deterministically. Byte-identical
across runs is the property under test; sending it to a model is the audit
layer's job and is gated on a preregistration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..records import SCHEMA_VERSION, Provenance, dumps, line_digest


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """One frozen source line and where it came from."""

    text: str
    sha256: str
    provenance: Provenance

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PriorTurn:
    """A conversation turn frozen ahead of the draw, carried as fixture material.

    An experiment that measures what a model does to an unsupported claim needs
    that claim to exist before the draw starts. Generating it from the model
    makes the denominator depend on the model breaking a rule the prompt states
    outright, so the claim is frozen here and the correction is what gets
    measured. The claim is discovery material; the response to it is not.

    Frozen with provenance and a digest for the same reason evidence is: the
    text a draw was taken against has to be re-readable after the fact, and a
    turn that can be edited without moving a hash is not frozen.
    """

    role: str                       # user | assistant
    text: str
    sha256: str
    provenance: Provenance

    def to_dict(self) -> dict:
        return asdict(self)

    def as_message(self) -> dict:
        return {"role": self.role, "content": self.text}


@dataclass(slots=True)
class Fixture:
    """A frozen experiment."""

    id: str
    created_at: str
    kind: str                       # episode | sequence | manual
    session_id: str
    prompt: str
    target: str                     # what the draw is supposed to measure
    config: dict = field(default_factory=dict)
    evidence: list[EvidenceSpan] = field(default_factory=list)

    #: Turns that precede the draw. Empty for a fixture whose first model output
    #: is the measurement; non-empty when the experiment measures what the model
    #: does to text that was fixed in advance.
    prior_turns: list[PriorTurn] = field(default_factory=list)

    schema_version: int = SCHEMA_VERSION
    notes: str = ""

    def evidence_sha256(self) -> str:
        """One digest over every span, in order. The fixture's identity."""
        joined = "\n".join(s.sha256 for s in self.evidence)
        return sha256_text(joined)

    def prompt_sha256(self) -> str:
        return sha256_text(self.prompt)

    def config_sha256(self) -> str:
        return sha256_text(dumps(self.config))

    def prior_turns_sha256(self) -> str:
        """One digest over the frozen turns, roles included.

        Roles are hashed alongside the text because the same sentence spoken by
        the user and by the assistant are different experiments.
        """
        joined = "\n".join(f"{t.role}:{t.sha256}" for t in self.prior_turns)
        return sha256_text(joined)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_sha256"] = self.evidence_sha256()
        d["prompt_sha256"] = self.prompt_sha256()
        d["config_sha256"] = self.config_sha256()
        d["prior_turns_sha256"] = self.prior_turns_sha256()
        return d

    def write(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1, sort_keys=True,
                                   default=str) + "\n", encoding="utf-8")
        return path

    def replay(self) -> str:
        """The model-facing payload, rendered the same way every time.

        Spans are labelled by index and digest, never by source path. Two
        reasons: a payload carrying an absolute path leaks the machine it was
        frozen on to whatever reads it, and a fixture that renders differently
        after being copied is not portable. `verify()` uses the provenance to
        re-read the source; the payload does not need it.
        """
        lines = [f"# fixture {self.id}", f"# target: {self.target}", ""]
        for i, span in enumerate(self.evidence):
            lines.append(f"[{i}] sha256:{span.sha256[:12]}")
            lines.append(span.text)
        lines.append("")
        lines.append(self.prompt)
        return "\n".join(lines) + "\n"


def load(path: Path | str) -> Fixture:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    evidence = [
        EvidenceSpan(
            text=s["text"],
            sha256=s["sha256"],
            provenance=Provenance(**s["provenance"]),
        )
        for s in raw.get("evidence", [])
    ]
    prior_turns = [
        PriorTurn(
            role=t["role"],
            text=t["text"],
            sha256=t["sha256"],
            provenance=Provenance(**t["provenance"]),
        )
        for t in raw.get("prior_turns", [])
    ]
    return Fixture(
        id=raw["id"],
        created_at=raw["created_at"],
        kind=raw.get("kind", "manual"),
        session_id=raw.get("session_id", ""),
        prompt=raw.get("prompt", ""),
        target=raw.get("target", ""),
        config=raw.get("config", {}),
        evidence=evidence,
        prior_turns=prior_turns,
        schema_version=raw.get("schema_version", SCHEMA_VERSION),
        notes=raw.get("notes", ""),
    )


def freeze(turns, prompt: str, target: str, kind: str = "manual",
           config: dict | None = None, notes: str = "",
           fixture_id: str | None = None) -> Fixture:
    """Freeze the source lines behind a set of turns.

    The evidence is read back from each turn's provenance rather than taken
    from the turn, so what is frozen is the source line the digest names.
    """
    spans: list[EvidenceSpan] = []
    session_id = ""
    for turn in turns:
        p = turn.provenance
        session_id = session_id or p.session_id
        text = read_span(p)
        spans.append(EvidenceSpan(text=text, sha256=p.sha256, provenance=p))

    created = datetime.now(timezone.utc).isoformat()
    fid = fixture_id or f"fx-{sha256_text(created + session_id)[:12]}"
    return Fixture(
        id=fid,
        created_at=created,
        kind=kind,
        session_id=session_id,
        prompt=prompt,
        target=target,
        config=config or {},
        evidence=spans,
        notes=notes,
    )


def read_span(p: Provenance) -> str:
    """The source line a provenance record names.

    A row-addressed store is read by rowid; a line-addressed one by index.
    Either way the bytes come from the source, never from a cached copy.
    """
    path = Path(p.path)
    if p.adapter == "opencode":
        return _read_row(path, p.line)
    try:
        with path.open("rb") as fh:
            for i, raw in enumerate(fh):
                if i == p.line:
                    return raw.rstrip(b"\r\n").decode("utf-8", "replace")
    except OSError:
        return ""
    return ""


def _read_row(db: Path, rowid: int) -> str:
    import sqlite3

    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return ""
    try:
        row = con.execute("select data from message where rowid = ?",
                          (rowid,)).fetchone()
        return str(row[0]) if row else ""
    except sqlite3.Error:
        return ""
    finally:
        con.close()


def verify(fixture: Fixture) -> list[str]:
    """Spans whose source no longer matches. Empty means the corpus agrees.

    Drift is reported, not raised. The frozen bytes remain the subject of any
    measurement already taken; what changed is the corpus.
    """
    problems: list[str] = []
    for i, turn in enumerate(fixture.prior_turns):
        if line_digest(turn.text.encode("utf-8")) != turn.sha256:
            problems.append(
                f"prior turn {i} ({turn.role}): frozen text does not match its "
                "own digest")
    for i, span in enumerate(fixture.evidence):
        if line_digest(span.text.encode("utf-8")) != span.sha256:
            problems.append(f"span {i}: frozen text does not match its own digest")
            continue
        current = read_span(span.provenance)
        if not current:
            problems.append(f"span {i}: source line no longer readable "
                            f"({span.provenance.path}:{span.provenance.line})")
        elif line_digest(current.encode("utf-8")) != span.sha256:
            problems.append(f"span {i}: source has changed since the freeze "
                            f"({span.provenance.path}:{span.provenance.line})")
    return problems
