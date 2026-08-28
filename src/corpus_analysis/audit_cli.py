"""`corpus-audit` — freeze, replay, register, record.

No command here calls a model. Replay, verification, validation and summaries
are deterministic; fixture, registration and store creation record time and
identity. Taking draws remains outside the installed package: a confirmatory
run needs a registration the operator signed before the first draw.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import adapters
from .audit import challenge, fixtures, registration
from .publication import refuse_publication_path
from .records import dumps
from .scan.pipeline import scan_sessions
from .store import Store


def _nonnegative_int(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return n


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return n


def _corpus_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--adapter", default="claude", choices=adapters.names())
    p.add_argument("--root", type=Path, default=None)


def _prompt(args) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return args.prompt or ""


def cmd_freeze(args) -> int:
    """Freeze a session or one of its episodes as a fixture."""
    refuse_publication_path(args.out)
    adapter = adapters.get(args.adapter)
    for scan in scan_sessions(adapter, root=args.root, include_self=True):
        if scan.session_id != args.session_id:
            continue
        turns = scan.turns
        kind = "session"
        if args.episode is not None:
            starts = [e.opened_by.line for e in scan.episodes]
            if args.episode >= len(starts):
                print(f"no episode {args.episode} in {args.session_id}",
                      file=sys.stderr)
                return 1
            lo = starts[args.episode]
            hi = starts[args.episode + 1] if args.episode + 1 < len(starts) else None
            turns = [t for t in turns if t.provenance.line >= lo
                     and (hi is None or t.provenance.line < hi)]
            kind = "episode"

        if args.max_spans:
            turns = turns[:args.max_spans]

        fx = fixtures.freeze(
            turns, prompt=_prompt(args), target=args.target, kind=kind,
            config=json.loads(args.config) if args.config else {},
            notes=args.notes,
        )
        fx.write(args.out)
        print(f"{fx.id}  {len(fx.evidence)} spans  "
              f"evidence {fx.evidence_sha256()[:12]}  -> {args.out}",
              file=sys.stderr)
        return 0
    print(f"no session {args.session_id!r}", file=sys.stderr)
    return 1


def cmd_verify(args) -> int:
    fx = fixtures.load(args.fixture)
    problems = fixtures.verify(fx)
    if not problems:
        print(f"{fx.id}: {len(fx.evidence)} spans match their sources")
        return 0
    print(f"{fx.id}: {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    # Drift is a fact about the corpus, not a failure of the fixture. The
    # frozen bytes remain the subject of any measurement already taken.
    return 0 if args.report_only else 1


def cmd_replay(args) -> int:
    fx = fixtures.load(args.fixture)
    payload = fx.replay()
    if args.out:
        refuse_publication_path(args.out)
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


def cmd_register(args) -> int:
    refuse_publication_path(args.out)
    fx = fixtures.load(args.fixture)
    reg = registration.register(
        fx,
        intervention=_prompt(args) or args.intervention,
        condition=args.condition,
        draws=args.draws,
        stopping_rule=args.stopping_rule,
        signal_criterion=args.signal_criterion,
        model=args.model,
        notes=args.notes,
    )
    reg.write(args.out)
    print(f"registered {fx.id} -> {args.out}", file=sys.stderr)
    print("UNSIGNED. Set `signed_off_by` before the first draw; until then "
          "any draw is exploratory.", file=sys.stderr)
    return 0


def cmd_check(args) -> int:
    """Would a draw against this fixture be confirmatory?"""
    fx = fixtures.load(args.fixture)
    reg = registration.load(args.registration)
    problems = registration.validate(reg, fx)
    if not problems:
        print("confirmatory: registration matches the fixture and is signed")
        return 0
    print("exploratory, not confirmatory:")
    for p in problems:
        print(f"  {p}")
    return 1


def cmd_preflight(args) -> int:
    """Every reason the registered battery must not run. Empty means it may.

    The instrument commit is passed in rather than read: this layer runs no
    commands, so the caller that can ask git is the one that asks.
    """
    from .audit import battery

    fx = fixtures.load(args.fixture)
    reg = registration.load(args.registration)
    runtime = (json.loads(Path(args.runtime).read_text(encoding="utf-8"))
               if args.runtime else None)
    problems = battery.preflight(reg, fx, args.instrument_commit,
                                 args.archive or Path("raw"),
                                 args.repo_root or Path.cwd(), runtime=runtime)
    print(f"fixture            {reg.fixture_id}")
    print(f"instrument         {reg.instrument_commit or '(unset)'}")
    print(f"payload sha256     {reg.payload_sha256 or '(unset)'}")
    print(f"taxonomy           {reg.taxonomy_version}")
    print(f"draws              {reg.draws}")
    print(f"status             {reg.status}")
    if not problems:
        print("\nPREFLIGHT PASS: the freeze holds and the battery may run")
        return 0
    print(f"\nPREFLIGHT FAIL: {len(problems)} blocking condition(s)")
    for p_ in problems:
        print(f"  - {p_}")
    return 1


def cmd_record(args) -> int:
    """Append a recorded chain to the results store."""
    refuse_publication_path(args.store)
    raw = json.loads(Path(args.chain).read_text(encoding="utf-8"))
    chain = challenge.chain_from_dict(raw)
    store = Store(args.store)
    key = f"{chain.fixture_id}|{chain.model}|{chain.draw}"
    rec = store.append("chain", chain.to_dict(), key=key)
    print(f"{rec['id']}  {key}  N_k {chain.n_series}  "
          f"converged {chain.converged()}", file=sys.stderr)
    return 0


def cmd_summarize(args) -> int:
    store = Store(args.store)
    chains = [challenge.chain_from_dict(r["body"]) for r in store.of_kind("chain")]
    if args.fixture_id:
        chains = [c for c in chains if c.fixture_id == args.fixture_id]
    print(dumps(challenge.summarize(chains)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="corpus-audit",
        description="freeze, replay, register, and record provenance challenges",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("freeze", help="freeze a session or episode as a fixture")
    _corpus_args(p)
    p.add_argument("session_id")
    p.add_argument("--episode", type=_nonnegative_int, default=None)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", type=Path, default=None)
    p.add_argument("--target", required=True,
                   help="what a draw against this fixture is meant to measure")
    p.add_argument("--config", default="", help="model-facing config as JSON")
    p.add_argument("--max-spans", type=_nonnegative_int, default=0)
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("verify", help="re-read every span from its source")
    p.add_argument("fixture", type=Path)
    p.add_argument("--report-only", action="store_true",
                   help="exit zero even when the corpus has drifted")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("replay", help="render the model-facing payload")
    p.add_argument("fixture", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(fn=cmd_replay)

    p = sub.add_parser("register", help="preregister a confirmatory run")
    p.add_argument("fixture", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--intervention", default="",
                   help="the challenge wording, verbatim")
    p.add_argument("--prompt-file", type=Path, default=None,
                   help="read the intervention from a file")
    p.add_argument("--prompt", default="")
    p.add_argument("--condition", required=True,
                   help="when the challenge is issued")
    p.add_argument("--draws", type=_positive_int, required=True)
    p.add_argument("--stopping-rule", required=True)
    p.add_argument("--signal-criterion", required=True,
                   help="what result counts as signal, and what does not")
    p.add_argument("--model", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_register)

    p = sub.add_parser("check", help="is a draw against this fixture confirmatory?")
    p.add_argument("registration", type=Path)
    p.add_argument("--fixture", type=Path, required=True)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("preflight",
                       help="may the registered battery run? fails closed")
    p.add_argument("registration", type=Path)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--runtime", type=Path, default=None)
    p.add_argument("--instrument-commit", default="")
    p.add_argument("--archive", type=Path, default=None)
    p.add_argument("--repo-root", type=Path, default=None)
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser("record", help="append a recorded chain to the store")
    p.add_argument("chain", type=Path)
    p.add_argument("--store", type=Path, required=True)
    p.set_defaults(fn=cmd_record)

    p = sub.add_parser("summarize", help="outcome distribution over recorded chains")
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--fixture-id", default="")
    p.set_defaults(fn=cmd_summarize)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, KeyError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
