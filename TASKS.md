# Tasks

Phase order and state. A phase ends when its gate is green; the next one does
not start before that. Updated 2026-08-17.

Gate for every phase: `make check` passes, and the phase's own acceptance line
below is demonstrably true.

## P0 — skeleton and boundary ✅

- [x] Repository frame: license, governance, CI, rulesets, issue templates
- [x] `records.py` — Turn, Provenance, Episode, Sequence, Finding
- [x] `labels.py` — counted/derived/proxy, and the gate that enforces them
- [x] Boundary tests: offline tripwire, scrub greps, empty lexicon
- [x] `ARCHITECTURE.md` — the layer boundary and the extraction table

Acceptance: gates green on an empty corpus and on a one-session corpus.

## P1 — vertical slice ✅

- [x] Claude Code adapter, with a schema-drift probe
- [x] Session enumeration, first-timestamp bucketing, subagent attribution
- [x] Self-exclusion, on by default
- [x] Episode segmentation, including the continuation-summary fix
- [x] Behavioural signals: interrupt, denial, queued, error, revert, write churn,
      fast re-prompt
- [x] Candidate repair sequences, located with no lexicon
- [x] `corpus-scan` — sessions, ingest, episodes, find, extract, stats, report
- [x] JSONL out with per-line provenance, verifiable with `sed | sha256sum`
- [x] Determinism gate: scan twice, compare bytes

Acceptance: a real session scanned, one repair sequence located behaviourally,
provenance reproducible outside the tool.

## P2 — breadth ✅

- [x] Codex adapter (`rollout-*.jsonl`), with its own drift probe
- [x] OpenCode adapter (SQLite, read-only URI), with its own drift probe
- [x] Adapter conformance: one test body run against every registered adapter
- [x] Daily series, attributed by each turn's own timestamp — not the session's
      start, which puts a long session's whole history on the day it opened
- [x] Distance-from-prompt as a first-class measurement, with the structural
      control built in rather than bolted on
- [x] Self-normalization: a corpus scored against its own baseline window,
      never against another corpus's absolute rate
- [x] Report: harness releases, daily series, per-model split, and the position
      measurement with its control

Acceptance: met. All three formats scan to one record shape; the report prints
the daily series and the position control with every figure labelled.

Two cross-vendor facts the breadth work surfaced, both now load-bearing:

- **Aggregation cannot be assistant-scoped.** One format nests usage and
  reasoning inside the assistant message; another records each as its own
  event. Summing only assistant turns reported zero tokens and zero reasoning
  for the second, which reads as a model that never thought.
- **A zero can mean "not recorded".** `reasoning_output_tokens` is counted by
  one format and absent from another; `thinking_chars` is the reverse. Neither
  zero is evidence of absent reasoning, and `records.TOKEN_KEYS` says so where
  the keys are defined.

## P3 — audit layer ✅

Machinery only. Confirmatory draws are gated separately, below.

- [x] Challenge taxonomy v2: SURVIVE, PERSIST, NARROW, RETRACT, SEEK,
      SUBSTITUTE, OVERCONTRACT
- [x] `N_k` — newly introduced unsupported bridges at round k; local
      convergence is `N_k = 0`
- [x] Fixture freeze: input bytes + sha256, prompt, model-facing config,
      measurement target, provenance
- [x] Replay runner: a frozen fixture replays byte-identically
- [x] Preregistration file: fixture hash, prompt hash, intervention wording,
      outcome taxonomy version, draw count, stopping rule, and what counts as
      signal — validated against the fixture before any draw
- [x] Append-only result store, idempotent on key
- [x] `corpus-audit` — freeze, verify, replay, register, check, preflight,
      record, summarize

Acceptance: met. A fixture freezes, replays byte-identically, verifies against
its sources, and a registration reports whether a draw would be confirmatory.

Two properties the implementation forced, both now tested:

- **A replay payload carries no source path.** The first version labelled each
  span with its absolute path, which leaks the machine a fixture was frozen on
  to whatever reads the payload and makes a copied fixture render differently.
  Spans are labelled by index and digest; `verify()` keeps the provenance.
- **Convergence is `N_k = 0`, not a good outcome label.** A round can RETRACT
  its target and introduce two fresh bridges in the same breath. `Chain`
  computes convergence from the bridge count alone.

## P4 — publication ✅

- [x] Publication review covers the whole tracked tree and fixtures; identifying
      content and corpus measurements do not ship
- [x] README claims audit: observed-only, no vendor claim, no novelty claim
- [x] Determinism verified per adapter on real corpora over fixed windows
- [x] Published at v0.1.0 under GPL-3.0-or-later; CI green on Linux, macOS and
      Windows

Acceptance: met. The repository is public, the boundary checks run in CI on
three platforms, and no corpus content is in the git state.

**Use a fixed window when checking determinism against a live corpus.** A
relative window (`--since 1d`) resolves against the clock, so two runs seconds
apart can straddle a session boundary, and a corpus being written to during the
run will differ for the honest reason. `make determinism` over a static corpus,
or `--since`/`--until` with absolute dates, is the check that means something.

## P5 — ChatGPT export adapter ✅

A private chat corpus reaching the existing pipeline, with no new analysis
subsystem behind it.

- [x] `adapters/chatgpt.py` — `<export>/conversations-*.json`, with a drift probe
- [x] Branch reconstruction from `current_node`, single-leaf fallback,
      `ambiguous_active_branch` where neither settles it
- [x] Text-only: image, audio, and real-time audio/video counted and dropped;
      no decoder, no recognizer, no substitute text
- [x] Shard index of byte spans, so one conversation is re-read by seek rather
      than by re-parsing a shard that holds a hundred
- [x] Deduplication on the export's own `conversation_id`, first shard wins
- [x] Adapter diagnostics on `stats`: content types, media skipped, parse
      failures by structural category
- [x] Private output refuses commit-ready paths inside a Git worktree and
      permits only declared ignored output roots
- [x] Synthetic fixture export and the privacy tripwire over it

Acceptance: met. A private export scanned end to end with byte-identical
outputs and no corpus content in the git state. Re-demonstrable with
`make determinism` over a fixed window.

Four format rules pinned by the adapter tests:

- **File order is not history.** A reader that emits `mapping` in file
  order emits abandoned branches as sequential turns.
- **Timestamp order is not history either.** Timestamps do not identify the
  active branch, so a timestamp sort has the same defect.
- **A transcript can be audio.** `audio_transcription` parts carry readable
  text the export itself identifies as a transcription of a voice input.
  Treating them as prose puts spoken words into a corpus of typed ones; they
  are counted as audio and dropped.
- **A timestamp that will not convert is reported, not repaired.** The record
  carries an empty `ts` and a `malformed_timestamp` count.

## P6 — Claude consumer-export adapter ✅

A second private chat corpus reaching the pipeline. Coexists with `claude`
(Claude Code); neither adapter was renamed.

- [x] `adapters/claude_export.py` — `<export>/conversations.json`, with a drift probe
- [x] Thread reconstruction from `parent_message_uuid`; fails closed on multiple
      tips, on a cycle, and on an unreachable component
- [x] `content[]` as the text source, not the flattened `text` field
- [x] Text-only: uploads bucketed to image/audio/other and counted, never read;
      attachment bodies never counted as typed input
- [x] Memories, projects, and reflections counted structurally, never emitted;
      account files never opened
- [x] Duplicate conversations resolved only on identical serialization;
      a genuine conflict fails closed
- [x] Diagnostics that echo no source value
- [x] `array_spans`/`read_span` shared with the ChatGPT adapter
- [x] Synthetic fixture export, drift fixture, and tripwire coverage

Acceptance: met. A private export scanned byte-identically across two runs;
ambiguous branches failed closed and zero corpus content entered the git state.

Four format rules pinned by the adapter tests:

- **Model identity is not recorded.** `Turn.model` stays empty rather
  than inferring a provider or model.
- **An ambiguous branch emits nothing.** Multiple tips have no recorded active
  pointer, so selecting one would invent history.
- **A flattened convenience field is not the record.** `text` disagrees with the
  message's own blocks in the synthetic fixture, so blocks are canonical.
- **Withheld reasoning is distinct from absent reasoning.** A
  `thinking_hidden` block is counted separately and contributes no text.

## P7 — second breadth pass: three adapters, temporal, docs 🔶

- [x] `adapters/cursor.py` — agent transcript JSONL under `~/.cursor/projects`;
      primary and subagent transcripts as separate sessions; identity includes
      the source digest because a transcript id can be rewritten
- [x] `adapters/copilot_cli.py` — per-session `events.jsonl` under
      `~/.copilot`; global stores not merged; unknown event types raise drift
- [x] `adapters/vscode_chat.py` — `chatSessions/*.json` and storage-journal
      sessions under workspace storage; journal state used only when exactly
      one session-state value is present
- [x] All three registered, with drift probes, synthetic fixtures, and the
      adapter conformance suite run against the full eight-adapter registry
- [x] `scan/temporal.py` and the `temporal` command — clock/calendar tables
      over a corpus or previously written ingest JSONL, timezone explicit,
      every figure labelled; `tests/test_temporal.py`
- [x] `docs/ADAPTERS.md` and `docs/USER_GUIDE.md` — the adapter matrix, output
      contracts, and the `flow-indicator` generic-JSONL bridge
- [x] One publication-path boundary shared by scan, audit and M3a archive
      writes
- [x] Real-corpus determinism demonstrated for `cursor`,
      `copilot_cli`, and `vscode_chat` on
      2026-08-28 against static snapshots; each pair of ingest outputs was
      byte-identical
- [x] Wire `probe()` into the CLI scan path before session metadata is read;
      wrong-format sessions raise `SchemaDrift` instead of becoming quiet
      zero-turn records.

Acceptance: open until the determinism line above is demonstrated on real
corpora. Conformance and fixtures are checked by `make check`; its exit status,
not a pinned test count, is the gate.

## M3a — first prospective battery: registered, unsigned, not run 🔒

An epistemic checkpoint, not a feature phase. `experiments/m3a/registration.json`
is DRAFT and carries no signature. **Zero confirmatory draws exist.**

M3a is a substitution experiment. Given a frozen unsupported evidence→claim
bridge, does a direct provenance challenge repair the target while introducing a
replacement unsupported bridge?

    primary   substitution_rate >= T        target_repaired AND N_1 >= 1
    secondary clean_repair_rate, unrepaired_rate, new_bridge_rate, N_k depth

Clean repair and unrepaired are the other two cells of the same partition.
Recursive `N_k` measures what happens to a replacement bridge after
substitution; it is secondary and never enters the k=1 primary denominator.

- [x] Fixture 1: one conductor evidence block for a finished read-only
      investigation, scrubbed, with the unsupported claim frozen as a
      one-sentence prior assistant turn
- [x] Registration freezing the evidence, frozen target, payload, prompt,
      challenge wording, recursion and termination rules, taxonomy v2, N_k,
      bridge definitions, draw count, stopping rule, invalid-draw criteria, and
      the signal and no-signal criteria
- [x] `audit/battery.py` and `audit/panel.py` — payload rendering and hashing,
      grounding, the registered statistics, panel resolution, preflight. Pure;
      the runner that reaches an endpoint lives outside the package
- [x] Three-labeller panel: one human investigator plus two model labellers,
      fixed stage order, one rendered packet, 2-of-3 resolution, DISPUTED
      preserved, adjudication as a separate artifact
- [x] Runtime identity pinned by digest; transport verified on a synthetic
      prompt against a live endpoint
- [x] Resume behavior covered by `TestResume`: round-one counters
      and attempt ids reconstruct from the immutable archive, malformed
      coordinates refuse, and a three-stage capture missing only its panel
      manifest finalizes
- [ ] **Validate the labelling flow end to end, by hand, before signing.**
      Packet rendering; the three stages; interrupt and resume; closed stdin;
      SHA manifests per stage and per panel; recursive rounds covering
      convergence, substitution, disagreement and adjudication.
- [ ] Operator signature approving the populated threshold, recursion cap,
      seed policy and runtime identity. Signed over machinery that has been
      used, not machinery that only passes tests.
- [ ] Confirmatory draws under the signed registration. No registration adopts
      draws that predate it.

No pilot draws are published. Hand-authored records exercise the archive format
in tests; generated requests and responses are excluded from the release tree.

## Gated on something other than engineering

- **Confirmatory draws** (the local battery, then a second model family).
  Requires a model endpoint and the operator's sign-off on the registration
  file *before* the first draw. Draws taken after any edit to a registered
  element are not confirmatory. The criterion is written when the fixture is in
  hand; a threshold invented earlier is a number with nothing under it.
- **Share mode** — structural series only, no text, no paths, no project names.
  Gated on a second user: a second corpus is required to specify the aggregation
  contract.
- **Related-work claims** — gated on reading the landscape, not on publishing.
  A README that claims no novelty needs no novelty check, so this blocks
  language and never a release. A landscape snapshot now exists at
  `docs/RELATED_WORK_LANDSCAPE.md`; it states its own limit ("not found" means
  not found in the searches it represents) and instructs against claiming
  novelty for replay or for transcript parsing. The README still makes no
  novelty claim.

## Anti-scope

Excluded designs:

- A position-test p-value read as evidence of finish-line behaviour. The null
  it rejects is one nobody holds, and one structural control dissolves it.
- Lexicon-derived series used as cross-user metrics.
- Conjunction arithmetic over correlated events, and any scalar-correlation
  dependence model. Only assumption-free bounds hold.
- Demand or adoption claims derived from a string appearing in a search result.
- Any claim about a specific vendor's model behaviour. This tool is the
  instrument for investigating one; it asserts none.
