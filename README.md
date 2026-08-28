# corpus-analysis

[releases](https://github.com/TGPSKI/corpus-analysis/releases) | [changelog](CHANGELOG.md) | [architecture](ARCHITECTURE.md) | [adapters](docs/ADAPTERS.md) | [user guide](docs/USER_GUIDE.md) | [tasks](TASKS.md) | [pate.sh](https://pate.sh)

**Turns agent and chat transcript corpora into inspectable evidence with exact
provenance.**

The installed package is stdlib-only. Its scan and audit commands require no
network or model. Scan figures derive from transcript records; audit summaries
derive from labelled stores whose records retain transcript provenance.
The experiment runners under `experiments/` have a separate, explicit network
and write surface documented in [SECURITY.md](SECURITY.md).

```
raw transcripts
  -> normalized deterministic records      (adapters)
  -> measured corpus observations          (corpus-scan)
  -> candidate evidence/claim sequences    (corpus-scan)
  -> provenance-grounded audit             (corpus-audit, optional)
  -> frozen fixtures -> prospective evals  (corpus-audit)
```

Two layers, and the boundary is the point. **corpus-scan** is deterministic: no
model, no network, read-only, and the whole of it is useful with nothing
attached. **corpus-audit** is optional. It interprets, it can freeze a
naturalistic failure into a replayable experiment, and every claim it makes
references a scan-layer provenance id.

## State

The current tree registers eight adapters — Claude Code, Codex, OpenCode,
ChatGPT and Claude consumer exports, Copilot CLI, Cursor, and VS Code chat.
The adapter matrix and source boundaries are in the [adapter reference](docs/ADAPTERS.md);
workflow and output contracts are in the [user guide](docs/USER_GUIDE.md).
v0.1.0 shipped the first five. The 0.2.0 tree adds the remaining three; they are
covered by conformance tests, synthetic fixtures, and byte-identical scans over
static real-corpus snapshots.

Built against one operator's corpus. That anything in it generalises to a second
corpus is a hypothesis, not a finding.

## What it is not

- Not an agent framework.
- Not a judge. The scanner is useful with no model attached.
- Not a claim about any vendor's model behaviour. It is the instrument you would
  use to investigate one; it asserts none.

## Install

From a source checkout, build and install the package with pip:

```sh
git clone https://github.com/TGPSKI/corpus-analysis && cd corpus-analysis
python3 -m pip install .
corpus-scan --help
corpus-audit --help
```

For development, `python3 -m pip install -e ".[dev]"` also installs Ruff.

## Quick start

```sh
corpus-scan sessions --since 7d          # what is in the corpus
corpus-scan stats    --since 7d          # totals, as one JSON object
corpus-scan report   --since 7d          # markdown, every figure labelled
corpus-scan find     --since 7d          # candidate repair sequences
```

`corpus-scan` also provides `ingest`, `episodes`, `extract`, and `temporal`; run
`corpus-scan <command> --help` for flags. `corpus-audit` provides
`freeze`, `verify`, `replay`, `register`, `check`, `preflight`, `record`, and
`summarize`. The Python modules are implementation details in v0.2.x; the two
command interfaces are the supported surface. See the [user guide](docs/USER_GUIDE.md)
for command output shapes, multi-adapter scans, downstream handoffs, and
flow-indicator usage.

`--adapter` selects the format — `chatgpt`, `claude`, `claude_export`, `codex`,
`copilot_cli`, `cursor`, `opencode`, `vscode_chat` — and `--root` the corpus
directory. The default is Claude Code at
`~/.claude/projects`. `claude` is the CLI's JSONL sessions; `claude_export` is
the consumer data export, a different product with a different schema.

Both consumer exports are conversation trees and text-only. ChatGPT records
`current_node`, so the visible thread is recoverable; Claude records no
equivalent, so a conversation with more than one tip **fails closed** and emits
nothing. The rationale is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Provenance is checkable outside this tool

Every record carries the path, line index and sha256 of the source line it came
from, over the raw bytes:

```sh
./bin/corpus-scan ingest --since 1d | head -1 | python3 -m json.tool
# ... "provenance": {"path": "...", "line": 181, "sha256": "8d673b56..."}

python3 -c 'import itertools,sys; n=int(sys.argv[1]); sys.stdout.buffer.write(next(itertools.islice(sys.stdin.buffer,n-1,None)).rstrip(b"\r\n"))' 182 < <path> | sha256sum
# 8d673b56...
```

A format with no source line addresses its records differently and says so. The
consumer exports are JSON arrays, so `line` is the message's position in the
reconstructed thread, `turn_id` is the vendor's message id, and the digest is
over that message's canonical serialization.

## Every figure carries its epistemic status

Reports print one of three labels beside every number, and a report line without
one fails a test:

- `counted` — arithmetic over records; entailed by the corpus.
- `derived` — counted values combined under a rule, and the rule is printed.
- `proxy` — stands in for something the format does not record, with the
  assumption named inline.

```
- think_share 0.245 [derived: think_turns / assistant_turns]
- signature chars per reasoning turn 2745.7 [proxy: signature length stands in
  for withheld reasoning text; assumed to track it, never measured against it]
```

## Freezing an experiment

A fixture holds the evidence bytes, the prompt, the model-facing config, and the
provenance of every span:

```sh
./bin/corpus-audit freeze <session-id> --episode 3 \
    --target "whether the claim is derived from the frozen spans" \
    --prompt "What observation establishes that claim?" \
    --out fixtures/case.fixture.json

./bin/corpus-audit verify fixtures/case.fixture.json
./bin/corpus-audit replay fixtures/case.fixture.json
```

It freezes bytes rather than pointing at them: the store is vendor-controlled,
and a format reshape must not invalidate a measurement already taken. `verify`
reports drift without invalidating the fixture.

A challenged claim gets one of seven outcomes — SURVIVE, PERSIST, NARROW,
RETRACT, SEEK, SUBSTITUTE, OVERCONTRACT — and each round records `N_k`, the
number of newly introduced unsupported bridges. SURVIVE and PERSIST both leave
the claim standing and disagree about the evidence. Convergence is `N_k = 0`,
not a good outcome label: a round can retract its target and introduce two fresh
bridges in the same breath.

**Confirmatory runs are preregistered.** `corpus-audit register` records the
fixture, prompt, config, intervention, draw count, stopping rule and what would
count as signal. `check` validates fixture hashes and the operator signature;
the committed registration digest records the registration bytes themselves.
Changing either after a draw makes that draw exploratory. An unsigned
registration gates nothing.

The installed commands do not take draws. The M3a runner is a separate
experiment-side client.

### An experiment built with it

[`experiments/`](experiments/README.md) holds the batteries built on this
machinery and the rules all of them follow.
[`m3a`](experiments/m3a/README.md) is the first: does a provenance challenge
repair an unsupported claim while introducing a replacement? It is unsigned, it
has not run, and zero confirmatory draws exist.

Nothing there is a finding, and the tool does not depend on it.

## Signals are behavioural by default

The defaults are acts the harness recorded, not words anyone used: interrupts,
refused tool calls, messages typed while the agent was still working, a prompt
arriving seconds after the last answer, the same file rewritten across an
episode boundary, undo-shaped commands.

Word lists are supported and **ship empty**. A lexicon written while looking at
the corpus it will run against is tuned to that corpus by construction, so the
resulting series partly measures its author. Supply your own with `--lexicon`,
knowingly.

## Privacy

A transcript corpus contains whatever was pasted into a session, secrets
included.

- `corpus-scan` is read-only apart from an explicit `--out`; the installed
  package opens no network connection and starts no subprocess.
- `--no-text` drops typed prompt text from scan output. Canonical scan records
  retain assistant sizes, not assistant bodies. Audit fixtures deliberately
  re-read and retain the complete source records named by their provenance.
- Sessions whose working directory is this tool's own are excluded from
  aggregates by default, so the instrument does not measure its own development
  and report the result as a property of the corpus.

## Layout

```
src/corpus_analysis/
  records.py        Turn, Provenance, Episode, Sequence, Finding
  labels.py         counted / derived / proxy, and the gate that enforces them
  cli.py            corpus-scan
  audit_cli.py      corpus-audit
  store.py          append-only results ledger
  publication.py    the output-path guard shared by scan, audit and M3a
  adapters/         chatgpt, claude, claude_export, codex, copilot_cli,
                    cursor, opencode, vscode_chat — each with a drift probe
  scan/             sessions, pipeline, episodes, signals, metrics, temporal,
                    lexicon, report
  audit/            fixtures, challenge taxonomy, preregistration, battery, panel
experiments/        prospective batteries; one directory each
tests/              unittest; fixtures are synthetic by construction
bin/                corpus-scan, corpus-audit — run from a checkout
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The rule worth reading first: a claim in
a docstring, a report or a commit message names the observation that establishes
it.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
