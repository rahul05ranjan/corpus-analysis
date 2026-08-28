# AGENTS.md — rules for agents working in this repo

`CLAUDE.md` is a symlink to this file. Edit this one, never the link, so no
tool reads a second copy that has drifted.

## What this is

A toolkit that turns agent transcript corpora into inspectable evidence with
exact provenance. Read `ARCHITECTURE.md` before changing anything structural
and `TASKS.md` for what phase the work is in.

## The gates that decide whether a change is acceptable

A change that trips one is wrong until the check is wrong, and the check being
wrong is an argument you have to make. Gates 1, 4 and 5 are tests. Gates 2 and 3
are checked by reading; each says so below.

1. **Determinism.** Same corpus in, byte-identical bytes out. Any new counter,
   dict, or set that reaches output is sorted before it gets there —
   `adapters.base.sorted_counts` exists for this. Insertion order is
   deterministic for one file and differs between two runs that read the same
   records in a different sequence.
2. **Offline.** No network module appears anywhere in `src/`. Checked by
   reading it. A grep over module names used to stand in for this and was
   removed: it missed most of the stdlib's network surface while reading as
   coverage.
3. **Nothing identifying ships.** No machine paths, no private repository
   names, no currency figures, no session text. Test fixtures are written by
   hand for this reason: a fixture is the easiest route for a private
   transcript to reach a public commit. The four scrub greps that enforced this
   were removed in commit `9c4225d` on 2026-08-15 and were not replaced, so
   this gate currently rests on review alone.
4. **Every report figure carries a label.** Numbers reach a report as `Figure`
   or as a cell under a labelled `Column`. There is no third route, and
   `labels.lint` re-checks the rendered text.
5. **Observed and interpretive fields stay disjoint.** `Finding.observed` is
   what a record says; `Finding.labels` is what a reader concluded. Sharing a
   key makes an audit unreviewable.

## The layer boundary

`scan/` is deterministic and model-free. `audit/` interprets. Anything that
needs a model, a rule, or a human judgment is audit-layer, and every claim it
makes references a scan-layer provenance id.

The scanner must remain useful with the auditor deleted. If a change makes
`scan/` depend on `audit/`, the change is in the wrong module.

## Working principles

- **One data path per fact.** Format knowledge lives in exactly one adapter. A
  second reader of the same format is the thing to avoid.
- **Never infer freshness from file mtime.** Sessions are bucketed by their
  first recorded timestamp. mtime moves on resume, on backup, and on sync —
  none of which is when the work happened.
- **Adapters fail loudly.** The store is vendor-controlled. A format reshape
  must raise `SchemaDrift`, not degrade into a corpus that reads as quiet.
- **A signal defaults to behaviour, not vocabulary.** Anything lexical is
  configuration the user supplies. This repo ships no word lists.
- **Bound what grows.** Canonical scan records retain assistant size, not body
  text. Audit fixtures deliberately re-read and retain the complete source
  records named by their provenance.

## Development workflow

```sh
make check                      # compile + the full suite. What CI runs.
make test                       # unittest discovery, verbose
make lint                       # ruff
make determinism ROOT=<corpus>  # scan a real corpus twice, compare bytes
make stats ROOT=<corpus> SINCE=7d
```

The suite runs in well under a second against a synthetic fixture corpus and
touches no network and no real transcript. Run it before anything long.

## Adding an adapter

1. A module in `src/corpus_analysis/adapters/` exposing `name`,
   `default_root()`, `sessions()`, `turns()`, `probe()`.
2. `turns()` yields `Turn` built from `records.blank_turn`, so a field the
   vendor does not record stays at its zero value rather than being invented.
3. `probe()` raises `SchemaDrift` when none of the record types it was written
   against appears.
4. Register it in `adapters/__init__.py`.
5. Add a synthetic fixture and a drift fixture under `tests/fixtures/`.

Two optional module attributes, both declarations rather than behaviour:
`records_cwd = False` when the format has no working-directory concept, so
enumeration takes the `first_ts` fast path instead of parsing every session to
look for a field the vendor never wrote; and `diagnostics()` returning sorted
aggregate counts, which `stats` prints. Diagnostics carry category names and
closed-vocabulary discriminators — never a title, body, identifier, or
filename, because they are printed from runs over private corpora.

## Epistemic rule

This project is partly about detecting semantic overreach, so it does not get
to commit it. For any claim in a docstring, a report, a commit message, or a
plan, answer: **what observation establishes that claim?** Mark design claims
OBSERVED, DERIVED, HYPOTHESIS, or DESIGN CHOICE. Do not convert "this seems
useful" into "the corpus proves X".

## Prose

Every line has to reduce ambiguity. If a sentence does not change the reader's
decision, cut it. Prefer nouns and verbs over adjectives, exact dates over
vague recency, concrete facts over promises. Claims need evidence: name the
test, the commit, or the measurement. This applies to commit messages and
handoff notes as much as to the README.
