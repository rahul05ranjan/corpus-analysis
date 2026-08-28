# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-28

### Added

- Three adapters, each with a schema-drift probe and a synthetic fixture:
  Cursor (`cursor`), Copilot CLI (`copilot_cli`), VS Code chat (`vscode_chat`).
  The registry now holds eight. Covered by the adapter conformance suite and
  byte-identical runs over static real-corpus snapshots.
- `scan/temporal.py` — clock/calendar heat tables, monthly series, cadence and
  heaviest-day views, with `tests/test_temporal.py`.
- `docs/ADAPTERS.md` — the eight-adapter source, fixture, drift, and downstream
  boundary reference.
- `docs/USER_GUIDE.md` — command workflows, output shapes, privacy boundaries,
  and the explicit `flow-indicator` generic-JSONL bridge.
- CLI scans invoke each adapter's drift probe before reading session metadata.
- CI builds and installs the wheel, then smoke-tests both installed console
  scripts.

### Changed

- `make determinism` writes its two comparison files under the ignored `out/`
  root instead of shared `/tmp`, and keeps them only on a mismatch. The old
  recipe left corpus text in `/tmp` exactly when the comparison failed.
- `make temporal` takes the zone as `ZONE=`, not `TZ=`: make imports `TZ` from
  the environment, so a host with `TZ` exported silently picked its zone.
- `SchemaDrift` from `corpus-scan` exits 2 with a one-line message instead of
  a traceback.
- `--no-text` is no longer accepted by `episodes`; it was a no-op there
  (`Episode` carries no text field).
- Negative episode, span, and draw counts are rejected as operator errors.
- Markdown table cells are escaped and checked against the labelled header's
  column count.
- Scan, audit and M3a archive writes share one publication-path boundary:
  inside a Git worktree, private output is accepted only under declared ignored
  roots.
- Security documentation now separates the offline installed package from the
  endpoint, browser, Git and archive surface of the M3a experiment tools.
- The M3a human panel member uses a role identifier rather than a personal
  name; the draft registration records its populated, unsigned decisions.
- The M3a fixture is fully hand-authored synthetic material. Generated model
  requests and responses are excluded from the release tree.

## [0.1.0] - 2026-08-12

First public release.

### Scan layer

- Canonical records: `Turn`, `Provenance`, `Episode`, `Sequence`, `Finding`.
  Every record carries the path, line index and sha256 of the source line it
  came from. The README's verifier handles LF, CRLF, and a final record without
  a newline.
- Five adapters, each with a schema-drift probe that raises rather than
  degrading: Claude Code, Codex, OpenCode, and the ChatGPT and Claude consumer
  exports.
- Both consumer exports store a conversation as a tree. ChatGPT records
  `current_node`, so the visible thread is recoverable; Claude records no
  equivalent, so a conversation with more than one tip fails closed and emits
  nothing. Neither file order nor timestamp order reconstructs a thread.
- Text only. Image, audio and real-time components are counted and dropped;
  nothing is transcribed or described in their place.
- Session enumeration with first-timestamp bucketing, episode segmentation,
  behavioural signals, and candidate repair sequences located with no lexicon.
- Self-exclusion of the tool's own sessions, on by default.
- Determinism gate: the same corpus scans to byte-identical output.
- `corpus-scan`: sessions, ingest, episodes, find, extract, stats, report.

### Audit layer

- Fixtures freeze evidence bytes with their provenance and replay
  byte-identically.
- Challenge taxonomy v2: SURVIVE, PERSIST, NARROW, RETRACT, SEEK, SUBSTITUTE,
  OVERCONTRACT. `N_k` counts newly introduced unsupported bridges at round k.
- Preregistration pins the fixture, the frozen target, the payload, the runtime
  identity, the taxonomy, the draw count, the stopping rule and the criterion
  before the first draw. Preflight refuses while any operator decision is open.
- `corpus-audit`: freeze, verify, replay, register, check, preflight, record,
  summarize. (`preflight` shipped in v0.1.0 and was missing from this list;
  corrected 2026-08-17.)

### M3a

- A registered, unsigned, unrun substitution experiment. See
  `experiments/m3a/README.md`.
- Three-labeller panel with a fixed stage order, one rendered packet, 2-of-3
  resolution, preserved disagreement and separate adjudication artifacts.
- Hand-authored archive records exercise the M3a format; generated run
  artifacts are excluded from the release tree.

### Boundaries

- No network module reaches the scan layer.
- Nothing identifying ships: no machine paths, no private repository names, no
  currency figures, no corpus magnitudes.
- Every report figure carries a `counted`, `derived` or `proxy` label.
- The tool ships no word lists.

### Licence

- GPL-3.0-or-later.
