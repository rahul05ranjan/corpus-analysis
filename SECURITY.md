# Security

## Packaged commands

corpus-analysis reads agent transcript corpora. A corpus contains whatever was
pasted into a session: credentials, customer data, private source, personal
information. That makes the threat model unusual for a CLI — the sensitive
material is the *input*, and it is already on the user's disk.

The installed package is stdlib-only. Its surfaces differ:

- `corpus-scan` reads transcript stores and writes only an explicit `--out`.
- `corpus-audit` reads transcripts, fixtures, registrations and stores.
  `preflight` also reads the runtime, archive location, registered instrument
  files, panel roster, labelling prompt, and any superseded registration under
  `--repo-root`. `freeze`, `replay`, `register`, and `record` write only the
  path named by their output option.
- Neither command opens a network connection, starts a subprocess, reads a
  credential store, or chooses a hidden output path.
- The shared publication guard accepts repository-local private output only
  under ignored `out/`, `fixtures/`,
  `experiments/m3a/raw/`, `experiments/m3a/label-capture/runs/`,
  and `experiments/m3a/label-capture/labels-private/` roots.
- Canonical scan records retain assistant sizes, not assistant bodies. Audit
  fixtures deliberately re-read and retain complete source records.
- `--no-text` drops typed prompt text from `ingest` and
  `extract` output.

`src/` contains the complete packaged surface. The experiment scripts described
below are not imported by it.

## Automatic read roots

Without `--root`, an adapter reads its default local store:

| Adapter | Default root and read surface |
|---|---|
| `claude` | `~/.claude/projects`; project JSONL and subagent JSONL |
| `codex` | `~/.codex/sessions`; dated and flat rollout JSONL |
| `copilot_cli` | `~/.copilot`; recursive `events.jsonl` |
| `cursor` | `~/.cursor/projects`; recursive agent transcripts |
| `vscode_chat` | `~/.config/Code/User/workspaceStorage`; recursive chat sessions |
| `opencode` | `~/.local/share/opencode/opencode.db`; `session`, `message`, and `part` tables, opened read-only |
| `chatgpt` | `~/corpus/chatgpt`; conversation export shards |
| `claude_export` | `~/corpus/claude`; conversations plus structural counts from memories, projects, and reflections; account files are not opened |

`--root` replaces the selected default. Discovery is recursive where the table
says so.

## Experiment-side exceptions

These commands are opt-in and are not part of the packaged offline boundary:

| Command | External action | Data written or sent |
|---|---|---|
| `make m3a-run` | POST to `LOCAL_LLM_ENDPOINT`, or the loopback default in `runtime.json`; invokes read-only Git queries | Sends the complete frozen message list; writes complete requests and raw responses under `experiments/m3a/raw/` or `--archive` |
| `make m3a-smoke` | GET server identity and POST one synthetic prompt to the same endpoint | Writes no archive; `--show` prints the synthetic reply |
| `m3a-panel packet` | No external action | Reads registration, fixture, prompt template and a raw archive; writes only an explicit `--out`, guarded by the publication boundary |
| `m3a-panel validate/resolve/adjudicate` | No external action | Reads raw responses, labels and adjudications; writes only stdout |
| `make m3a-score` | No external action | Reads registration, fixture, runtime, raw archives, labels and named superseded registrations; writes only stdout |
| `m3a-label-capture.sh` | Opens the registered ChatGPT and Claude browser URLs; the operator pastes the rendered packet into each browser session | The packet sent to each service contains the registered evidence and target plus the archived response being labelled. The script copies labels, transcripts, screenshots, provenance and SHA manifests under its private capture root |

`M3A_LABEL_ROOT` redirects the capture root through the shared publication-path
guard. Repository-local captures are accepted only under the ignored
`label-capture/runs/` and `label-capture/labels-private/` roots. `M3A_ARCHIVE`
selects the archive read while rendering packets. Resuming an incomplete stage
removes that stage's partial captured directory before copying it again;
completed frozen stages are never replaced.

## What counts as a vulnerability

- Any undisclosed path by which corpus content leaves the machine.
- Any write outside a documented or operator-selected destination.
- Corpus content reaching a place the user did not name: a temp file that
  outlives the run, a log, an error message that embeds a transcript line.
- A crafted transcript that causes code execution, path traversal on extract,
  or resource exhaustion that is not bounded.
- A provenance digest that does not match the source bytes it names. Provenance
  is the tool's central claim; a digest that cannot be reproduced externally
  breaks it.
- Identifying content present in the published tree. There is no automated
  scrub check (removed in `9c4225d`); review is the gate, and content that
  passed it is a reportable failure of that review.

## Not vulnerabilities

- The tool reading sensitive material from a corpus you pointed it at. That is
  the function.
- A report revealing something about your own corpus. Output is local, and what
  you do with it is your call.
- Word lists you supply with `--lexicon` matching whatever you wrote in them.
- Network and archive activity performed by an experiment command exactly as
  documented above.

## Reporting

Open a [private security advisory](https://github.com/TGPSKI/corpus-analysis/security/advisories/new)
on GitHub. Do not open a public issue, and do not attach transcript content to
a report — a redacted description of the shape is enough to reproduce anything
in scope here.

| Stage | Target |
|---|---|
| Acknowledgment | 3 business days |
| Initial assessment | 10 business days |
| Fix or documented mitigation | 30 days for anything that moves corpus content |

## Supported versions

Pre-1.0. Only the latest commit on `main` is supported. There are no backports.
