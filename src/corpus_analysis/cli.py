"""`corpus-scan` — the deterministic layer, as a command.

Same corpus in, byte-identical bytes out. `--hash` prints the sha256 of what was
written, which is what the double-run gate in CI compares.

Read-only and offline. The only thing it writes is the path `--out` names.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from . import adapters
from .publication import refuse_publication_path
from .records import dumps
from .scan import lexicon
from .scan.pipeline import SessionScan, corpus_totals, scan_sessions
from .scan.signals import trigger_mix


def _nonnegative_int(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return n


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--adapter", default="claude", choices=adapters.names())
    ap.add_argument("--root", type=Path, default=None,
                    help="corpus root (default: the adapter's own)")
    ap.add_argument("--since", help="ISO time, a date, or a relative age: 5h, 7d")
    ap.add_argument("--until", help="same forms; the window is [since, until)")
    ap.add_argument("--include-self", action="store_true",
                    help="count sessions whose cwd is this tool's own")
    ap.add_argument("--self-path", type=Path, default=None,
                    help="what counts as this tool's directory (default: cwd)")
    ap.add_argument("--lexicon", type=Path, default=None,
                    help="JSON word lists; none ship with this tool")
    ap.add_argument("--out", type=Path, default=None, help="write here, not stdout")
    ap.add_argument("--hash", action="store_true",
                    help="print the sha256 of the output to stderr")


def _scans(args) -> list[SessionScan]:
    adapter = adapters.get(args.adapter)
    lex = lexicon.load(args.lexicon)
    return list(scan_sessions(
        adapter, root=args.root, since=args.since, until=args.until,
        include_self=args.include_self, self_path=args.self_path, lexicons=lex,
    ))


def _refuse_tracked_out(out: Path) -> None:
    refuse_publication_path(out)


def _emit(text: str, args) -> int:
    if args.out:
        _refuse_tracked_out(args.out)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.hash:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        print(f"sha256 {digest}", file=sys.stderr)
    return 0


def cmd_sessions(args) -> int:
    lines = []
    for s in _scans(args):
        lines.append(dumps({
            "session_id": s.session_id,
            "adapter": s.meta.ref.adapter,
            "project": s.meta.ref.project,
            "parent": s.meta.ref.parent,
            "path": s.meta.ref.path,
            "first_ts": s.meta.first_ts,
            "cwd": s.meta.cwd,
            "excluded": s.meta.excluded,
            "reason": s.meta.reason,
            "turns": s.totals["turns"],
            "episodes": len(s.episodes),
        }))
    return _emit("".join(f"{ln}\n" for ln in lines), args)


def cmd_ingest(args) -> int:
    out = []
    for s in _scans(args):
        if s.meta.excluded and not args.include_self:
            continue
        for turn in s.turns:
            out.append(turn.to_line(with_text=not args.no_text))
    return _emit("".join(f"{ln}\n" for ln in out), args)


def cmd_episodes(args) -> int:
    out = []
    for s in _scans(args):
        if s.meta.excluded and not args.include_self:
            continue
        out.extend(e.to_line() for e in s.episodes)
    return _emit("".join(f"{ln}\n" for ln in out), args)


def cmd_find(args) -> int:
    """Candidate repair sequences, located behaviourally."""
    out = []
    for s in _scans(args):
        if s.meta.excluded and not args.include_self:
            continue
        for seq in s.sequences:
            if args.trigger and args.trigger not in seq.trigger.split(","):
                continue
            out.append(seq.to_line())
    return _emit("".join(f"{ln}\n" for ln in out), args)


def cmd_extract(args) -> int:
    """One session's turns, with provenance, for freezing or reading."""
    for s in _scans(args):
        if s.session_id != args.session_id:
            continue
        turns = s.turns
        if args.episode is not None:
            eps = {e.index: e for e in s.episodes}
            if args.episode not in eps:
                print(f"no episode {args.episode} in {args.session_id}",
                      file=sys.stderr)
                return 1
            turns = _episode_turns(s, args.episode)
        body = "".join(f"{t.to_line(with_text=not args.no_text)}\n" for t in turns)
        return _emit(body, args)
    print(f"no session {args.session_id!r} in this window", file=sys.stderr)
    return 1


def _episode_turns(s: SessionScan, index: int) -> list:
    """Turns belonging to one episode, by provenance line range."""
    starts = [e.opened_by.line for e in s.episodes]
    lo = starts[index]
    hi = starts[index + 1] if index + 1 < len(starts) else None
    return [t for t in s.turns
            if t.provenance.line >= lo and (hi is None or t.provenance.line < hi)]


def cmd_stats(args) -> int:
    scans = _scans(args)
    kept = [s for s in scans if not s.meta.excluded]
    doc = {
        "window": {"since": args.since, "until": args.until},
        "adapter": args.adapter,
        "totals": corpus_totals(scans),
        "excluded_sessions": sum(1 for s in scans if s.meta.excluded),
        "triggers": trigger_mix([q for s in kept for q in s.sequences]),
        "lexicon_hits": _lexicon_totals(kept),
    }
    # What the adapter skipped, failed on, or could not resolve. Aggregate
    # counts and schema vocabulary only; an adapter with nothing to report omits
    # the key rather than printing an empty one.
    report = getattr(adapters.get(args.adapter), "diagnostics", None)
    if report is not None:
        doc["adapter_diagnostics"] = report()
    return _emit(dumps(doc) + "\n", args)


def _lexicon_totals(scans: list[SessionScan]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in scans:
        for group, n in s.lexicon_hits.items():
            out[group] = out.get(group, 0) + n
    return dict(sorted(out.items()))


def cmd_report(args) -> int:
    from .scan.report import corpus_report

    scans = _scans(args)
    return _emit(corpus_report(scans, since=args.since, until=args.until), args)


def cmd_temporal(args) -> int:
    """Clock and calendar views. Cross-tool when fed ingest files.

    With no positional files this measures one adapter, like every other
    command. With them it aggregates normalised turn lines that `ingest`
    already wrote — the route for a heatmap across adapters, without this
    command growing a second reader of any vendor format.
    """
    import json

    from .scan.temporal import aggregate, temporal_report

    if args.turns_files:
        def turn_dicts():
            for path in args.turns_files:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            yield json.loads(line)
    else:
        def turn_dicts():
            for s in _scans(args):
                if s.meta.excluded and not args.include_self:
                    continue
                for turn in s.turns:
                    yield turn.to_dict()

    return _emit(temporal_report(aggregate(turn_dicts(), tz=args.tz)), args)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="corpus-scan",
        description="deterministic measurement over agent transcript corpora",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    for cmd, fn, help_text in (
        ("sessions", cmd_sessions, "list located sessions, one JSON object each"),
        ("ingest", cmd_ingest, "normalised turns as JSONL, with provenance"),
        ("episodes", cmd_episodes, "episodes as JSONL"),
        ("find", cmd_find, "candidate repair sequences, located behaviourally"),
        ("extract", cmd_extract, "one session or episode, with provenance"),
        ("stats", cmd_stats, "corpus totals as one JSON object"),
        ("report", cmd_report, "markdown report; every figure carries its label"),
        ("temporal", cmd_temporal,
         "clock and calendar heat tables; every figure carries its label"),
    ):
        p = sub.add_parser(cmd, help=help_text)
        _common(p)
        p.set_defaults(fn=fn)
        if cmd in ("ingest", "extract"):
            p.add_argument("--no-text", action="store_true",
                           help="drop typed prompt text from the output")
        if cmd == "find":
            p.add_argument("--trigger", help="keep only sequences with this trigger")
        if cmd == "extract":
            p.add_argument("session_id")
            p.add_argument("--episode", type=_nonnegative_int, default=None)
        if cmd == "temporal":
            p.add_argument("turns_files", nargs="*", type=Path, metavar="TURNS_JSONL",
                           help="ingest output to aggregate instead of scanning; "
                                "several files merge adapters into one view")
            p.add_argument("--tz", default="UTC",
                           help="IANA zone for clock buckets (default UTC; "
                                "never read from the machine)")

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "no_text"):
        args.no_text = False
    try:
        return args.fn(args)
    except adapters.SchemaDrift as e:
        print(f"schema drift: {e}", file=sys.stderr)
        return 2
    except (ValueError, OSError, ZoneInfoNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
