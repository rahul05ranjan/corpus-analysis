# User guide

## Choose a workflow

| Question | Start here | Output |
|---|---|---|
| What sessions are available? | `corpus-scan sessions` | one JSON object per located session |
| What did the corpus record? | `corpus-scan stats` | one JSON object with aggregate counts and adapter diagnostics |
| What are the normalized turns? | `corpus-scan ingest` | deterministic JSONL `Turn` records |
| How are prompts and work grouped? | `corpus-scan episodes` | deterministic JSONL `Episode` records |
| Which prompt pairs deserve inspection? | `corpus-scan find` | JSONL candidate `Sequence` records |
| What happened in one session? | `corpus-scan extract SESSION_ID` | JSONL turns, or one episode with `--episode` |
| When did activity occur? | `corpus-scan temporal` | labelled Markdown clock/calendar tables |
| How does the corpus compare with itself over time? | `corpus-scan report` | labelled Markdown report |
| Can a candidate become an inspectable experiment? | `corpus-audit freeze` | hashed fixture with evidence spans |
| Is a proposed run confirmatory? | `corpus-audit preflight` | pass/fail gate and unresolved decisions |

The scan layer is deterministic, offline, model-free, and read-only except for
an explicit output path. The audit layer is optional and interpretive. It may
freeze bytes and record labels, but it never replaces scan observations with
interpretations.

## Adapter coverage

Pass `--root` when the source is not at the adapter's default location. The
adapter name is the value of `--adapter`. The detailed source contract and
fixture map are in the [adapter reference](ADAPTERS.md).

| Adapter | Default source | What is enumerated | Important boundary |
|---|---|---|---|
| `claude` | `~/.claude/projects` | Claude Code parent JSONL and subagent JSONL | Subagents are separate sessions attributed to their parent; continuation summaries do not open false episodes. |
| `codex` | `~/.codex/sessions` | dated or flat `rollout-*.jsonl` files | Cumulative usage is converted to per-turn deltas; do not sum cumulative fields downstream. |
| `opencode` | `~/.local/share/opencode/opencode.db` | SQLite `session`, `message`, and `part` rows | The database is opened read-only; delegated child sessions are retained as child sessions. |
| `chatgpt` | `~/corpus/chatgpt` | `conversations*.json` export shards | The active branch follows `current_node`; ambiguous trees emit diagnostics and no turns. Media is counted and dropped. |
| `claude_export` | `~/corpus/claude` | `conversations.json` export arrays | There is no active-branch pointer; multiple tips fail closed. Memories, projects, reflections, and account data are not emitted as turns. |
| `copilot_cli` | `~/.copilot` | recursive `events.jsonl` session logs | Session-local event logs are the source; ancillary global stores are not merged. |
| `cursor` | `~/.cursor/projects` | agent transcript JSONL | Primary and subagent transcripts are attributed separately; physical source identity includes source bytes. |
| `vscode_chat` | `~/.config/Code/User/workspaceStorage` | JSON and storage-journal chat sessions | A session id is tied to the physical source bytes; freezing it after the file changes requires a new session reference. |

Every adapter exposes a `probe()` that raises `SchemaDrift` when the expected
record shape is absent. The CLI invokes it before reading session metadata, and
the conformance suite exercises each registered adapter.

## Scan commands and output shapes

All JSON output is UTF-8. JSONL records are one deterministic JSON object per
line with sorted keys. Markdown reports are linted before they are returned.

### `sessions`

Use this to discover ids before `extract` or `freeze`:

```sh
./bin/corpus-scan sessions --adapter claude --root /path/to/projects \
  --since 2026-08-01T00:00:00+00:00 --until 2026-08-18T00:00:00+00:00
```

Each object contains a session reference, source path, first timestamp, project
or parent metadata when the format records it, and whether self-measurement
excluded it from aggregates. `--include-self` counts the excluded sessions;
`--self-path` sets what counts as this tool's directory (default: the current
directory). Session windows use the first recorded timestamp; file mtime is
never used.

### `ingest`

```sh
./bin/corpus-scan ingest --adapter codex --root /path/to/sessions \
  --since 7d --no-text --out out/turns.jsonl --hash
```

Each line is a canonical `Turn`; the field list is in the
[adapter reference](ADAPTERS.md#shared-canonical-fields).

`provenance` contains `adapter`, `path`, zero-based `line`, `sha256`,
`session_id`, and `turn_id`. `text` is typed prompt text only. Assistant bodies
are not retained; their sizes are available in `chars` and provenance can
re-read source bytes when a fixture needs them. `--no-text` removes typed text
from the output as well.

### `episodes`, `find`, and `extract`

An `Episode` starts at a typed prompt and includes the subsequent work until
the next typed prompt. It carries prompt and turn counts, model counts, file
writes, behavioural signals, and the provenance of its opening prompt.

`find` emits `Sequence` objects. A sequence is only a candidate: it contains
the consecutive episode indexes and the behavioural trigger(s) that selected
them (`interrupt`, `denial`, `edit_churn`, or `fast_reprompt`). It is not a
finding and does not establish that a repair occurred. Use `--trigger` to
filter candidates.

`extract SESSION_ID` emits the session's turns with provenance. Add
`--episode N` to restrict the output to one episode. Use `--no-text` when the
consumer needs structure but not prompt content.

### `stats`, `report`, and `temporal`

`stats` emits one JSON object. It includes aggregate counts, sorted mixes, and
adapter diagnostics. Diagnostics are structural categories and closed-vocabulary
counts; they do not echo titles, bodies, ids, filenames, or source values.

`report` emits Markdown sections for coverage, depth, behaviour, harness
release mix, daily series, model mix, position and its distance-from-prompt
control, and per-session counts. Every numeric figure is `counted`, `derived`
with its rule, or `proxy` with its assumption. A zero can mean “not recorded”
when the vendor does not expose a field; it must not be read as proof that the
event did not happen.

`temporal` accepts a fresh corpus or previously written ingest JSONL:

```sh
./bin/corpus-scan temporal out/turns-claude.jsonl out/turns-codex.jsonl \
  --tz America/Los_Angeles --out out/temporal.md
```

The timezone is explicit and defaults to UTC. It affects buckets only; it is
never read from the host environment. The command emits calendar and clock
views, source/month and model/month tables, prompt-length summaries, and
friction flags. Heat strips are scaled to their row maximum; the adjacent
labelled counts are the values downstream consumers should use.

## A complete local scan

Use an absolute window for a reproducible run over a live corpus:

```sh
OUT=out            # ignored by the repo; any operator-selected path works
mkdir -p "$OUT"

./bin/corpus-scan sessions --adapter claude --root "$CLAUDE_ROOT" \
  --since 2026-08-01T00:00:00+00:00 --until 2026-08-18T00:00:00+00:00 \
  --out "$OUT/sessions.jsonl"
./bin/corpus-scan ingest --adapter claude --root "$CLAUDE_ROOT" \
  --since 2026-08-01T00:00:00+00:00 --until 2026-08-18T00:00:00+00:00 --no-text \
  --out "$OUT/turns.jsonl" --hash
./bin/corpus-scan stats --adapter claude --root "$CLAUDE_ROOT" \
  --since 2026-08-01T00:00:00+00:00 --until 2026-08-18T00:00:00+00:00 \
  --out "$OUT/stats.json"
./bin/corpus-scan report --adapter claude --root "$CLAUDE_ROOT" \
  --since 2026-08-01T00:00:00+00:00 --until 2026-08-18T00:00:00+00:00 \
  --out "$OUT/report.md"
```

For two adapters, run `ingest` once per source and give both JSONL files to
`temporal`. Do not concatenate arbitrary JSONL from different schema versions
without preserving each record's `provenance.adapter` and `schema_version`.

## Handoff to `flow-indicator` or another downstream tool

There is no built-in `flow-indicator` command or dependency in this repository.
`flow-indicator` already reads Claude Code, Codex, and OpenCode sources through
its native harnesses; do not route those through this bridge unless you need a
canonical `Turn` snapshot. Use this bridge for ChatGPT, Claude consumer
exports, Copilot CLI, Cursor, and VS Code chat, or for a deliberately sealed
canonical snapshot.

`flow-indicator` does have a `generic` JSONL adapter, but it does not consume
`Turn` objects directly. The supported integration boundary is a small,
explicit conversion from canonical ingest JSONL to the generic shape. This
keeps vendor parsing here and makes the semantic loss at the boundary visible.

Recommended handoff:

```sh
mkdir -p out
./bin/corpus-scan ingest --adapter claude --root "$CLAUDE_ROOT" \
  --since 2026-08-01T00:00:00+00:00 --until 2026-08-18T00:00:00+00:00 \
  --out out/turns.jsonl --hash

jq -c '
  {
    stream_id: .provenance.session_id,
    turn_id: .provenance.turn_id,
    seq: (.provenance.line + 1),
    timestamp: .ts,
    speaker: (if .role == "user" then "user"
              elif .role == "assistant" then "assistant"
              else "tool" end),
    text: .text,
    sidechain: (.flags.sidechain // false),
    actions: [
      (.files // {} | to_entries[] as $file |
       range(0; ($file.value | tonumber)) |
       {verb: "write", targets: [$file.key]})
    ]
  }
' out/turns.jsonl > out/flow.jsonl

flow-indicator replay --adapter generic out/flow.jsonl
```

The `generic` adapter requires `stream_id`, `seq`, `speaker`, and `text`.
`timestamp`, `turn_id`, `sidechain`, and `actions` are optional fields used by
the bridge above. `flow-indicator` reads `actions` as observed source facts;
the example maps only canonical file-write counts to `write` actions. It does
not claim that every tool call is a write, and it intentionally does not map
`tools`, `flags`, token counts, or model names into action vocabulary.

Keep `out/turns.jsonl` and its `--hash` output beside `out/flow.jsonl` as the source
record. The generic stream retains only the fields it understands, so
`out/flow.jsonl` is a derived input and cannot replace the original provenance.

A downstream importer should:

- accept `Turn` JSONL, not source-vendor records, when implementing a native
  importer;
- use `ts` for event time and `provenance.session_id` for session identity;
- treat `role`, `kinds`, `usage`, `chars`, `tools`, `files`, and `flags` as
  observed fields;
- preserve `provenance` and `schema_version` on every derived event;
- sort or aggregate by explicit keys before rendering, rather than relying on
  input order;
- distinguish an absent vendor measurement represented by a zero from an
  observed absence; the generic bridge cannot preserve every one of these
  fields, so keep the canonical JSONL for audits;
- keep any indicator, score, label, or causal interpretation in downstream
  fields, never by overwriting canonical observed fields;
- report records with empty or malformed timestamps instead of assigning them a
  time from file mtime or arrival order.

For a flow view, the natural observed event is a typed prompt followed by its
assistant/tool turns until the next typed prompt. The `Episode` output already
encodes that boundary; use it when the downstream tool needs prompt-centered
flows, and use `Turn` when it needs event-level timing. `Sequence` is suitable
for candidate repair overlays, but must be labelled as a candidate rather than
as a confirmed correction.

Before publishing a downstream artifact, retain the command arguments, the
input hash, adapter name, absolute `since`/`until` window, timezone, and the
downstream schema/version. Do not publish raw text or source paths unless the
recipient has an explicit privacy boundary; prefer `--no-text` and a local
mapping back to provenance.

## Freeze and audit a candidate

First discover a session and candidate with scan commands. Then freeze the
evidence you intend to challenge:

```sh
./bin/corpus-audit freeze SESSION_ID --episode 3 \
  --root "$CLAUDE_ROOT" --adapter claude \
  --target "the exact claim to challenge" \
  --prompt "What observation establishes that claim?" \
  --out fixtures/case.fixture.json
./bin/corpus-audit verify fixtures/case.fixture.json
./bin/corpus-audit replay fixtures/case.fixture.json \
  --out fixtures/case.payload.json
```

`freeze --max-spans N` truncates the evidence to the first N turns; a
truncated fixture proves less, knowingly. `verify` re-reads source spans and
reports whether the fixture still matches; drift exits 1 unless
`--report-only`, which reports and exits 0.
`replay` renders the model-facing payload without source paths. Register the
intervention, condition, draw count, stopping rule, and signal criterion before
the first draw, then run `check` and `preflight`. `record` appends an archived
chain idempotently; `summarize` reports outcome distributions. An unsigned or
incomplete registration is exploratory, not confirmatory.

## Privacy and downstream impact

The input is the sensitive asset. Scan output can contain prompt text, source
paths, ids, file paths, model names, and exact provenance unless the selected
command suppresses them. Keep output under an ignored local directory, use
`--no-text` for structural consumers, and never treat a digest as
anonymization. See [SECURITY.md](../SECURITY.md) before scanning a private
corpus or enabling the experiment-side M3a tools.

The interpretation risks downstream are structural: vendor formats
record reasoning and usage at different scopes; consumer exports may contain
abandoned branches; timestamps may be missing or malformed; and a session can
cross harness releases or calendar days. The canonical records preserve these
distinctions so a consumer can choose a rule and name it.
