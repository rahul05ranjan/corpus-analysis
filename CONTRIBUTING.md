# Contributing

## Setup

The runtime has no third-party dependencies. Install the development checkout:

```sh
git clone https://github.com/TGPSKI/corpus-analysis && cd corpus-analysis
python3 -m pip install -e ".[dev]"
make check
```

Ruff is the only development dependency.

## Commands

| Command | What it does |
|---|---|
| `make check` | Compile + the full suite. What CI runs. |
| `make test` | unittest discovery, verbose |
| `make lint` | ruff over the tree |
| `make determinism ROOT=<corpus>` | Scan a real corpus twice, compare bytes |
| `make stats ROOT=<corpus> SINCE=7d` | Corpus totals, read-only |
| `make temporal ROOT=<corpus> SINCE=7d ZONE=UTC` | Clock and calendar tables |
| `make m3a-preflight` | Check whether the registered battery may run |
| `make m3a-smoke` | Check experiment transport; does not take a draw |
| `make m3a-score LABELS=<path>` | Score archived M3a draws against labels |

`make help` lists the rest.

The suite is offline and runs against a synthetic fixture corpus. The command's
exit status is the gate.

## The five gates

Every change is measured against the contracts in
[ARCHITECTURE.md](ARCHITECTURE.md): determinism, offline, nothing identifying
ships, every report figure labelled, observed and interpretive fields disjoint.
Determinism, the label gate and field disjointness are tests. Offline and
nothing-identifying are checked by reading — the scrub greps were removed in
`9c4225d` and not replaced, so a PR touching fixtures or diagnostics gets read
for it. A PR that trips a gate is not merged until either the change or the
check is fixed, and fixing the check is an argument you make in the PR.

## Contribution types

**A new adapter** is self-contained.
The steps are in [AGENTS.md](AGENTS.md). Two requirements beyond the interface:
a `probe()` that raises on format drift, and a synthetic fixture — never a real
transcript, however scrubbed.

**A new signal** must be computable from what a transcript records. Say which
field it reads. Behavioural signals are the default; a lexical one belongs in
user configuration, not in the shipped defaults.

**A measurement change** needs its confound named. If a series can move for a
reason other than the one being claimed, the report says so beside the figure
or the change is incomplete.

**A report figure** carries `counted`, `derived`, or `proxy`. Derived cites its
rule. Proxy names its assumption. There is no unlabeled route to the page.

## Test fixtures

Fixtures are written by hand and contain no text from any real corpus. This is
a publication constraint, not a preference: a test fixture is the easiest place
for a private transcript to reach a public repository. `test_boundaries.py`
checks their identifiers are synthetic; nothing checks their prose but a
reader.

## Pull requests

- `make check` green. CI runs it on the oldest supported CPython and the
  newest; a change that depends on a newer feature has to raise the floor in
  `pyproject.toml` deliberately.
- Add the `full-test` label to run the cross-platform matrix. Apply it before
  the last push, so the matrix runs on the tree that merges.
- Update [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`.
- A commit message states what changed and what establishes it. "Fix episode
  segmentation" is half a message; the other half is which record shape broke
  it and which test now pins it.

## Claims

This project detects unsupported inferential expansion, so it does not get to
commit it. If your PR description says a change improves something, name the
measurement. If you cannot, say so — "this seems better and I have not measured
it" is an acceptable sentence here and a preferable one to a claim with nothing
under it.
