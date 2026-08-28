# Architecture

What moves, what stays, and the contracts that hold the two layers apart.

## The layer boundary

| Layer | Property | Contents |
|---|---|---|
| `adapters/` | vendor-specific, deterministic | format → `Turn` + `Provenance`, plus a drift probe |
| `scan/` | deterministic, model-free, read-only | enumeration, episodes, behavioural signals, candidate sequences, reports |
| `audit/` | interpretive, optional | challenge taxonomy, fixtures, replay |

**The scanner must remain useful without the auditor.** That is the constraint
that decides where a thing goes: anything requiring a model, a rule, or a human
judgment is audit-layer, and everything it reasons about was produced by the
scan layer first and can be recomputed.

## Provenance

Every record carries `adapter`, `path`, `line`, `sha256`, `session_id`,
`turn_id`. The digest is over the raw source-line bytes with the terminator
excluded, so it reproduces outside this tool:

```sh
python3 -c 'import itertools,sys; n=int(sys.argv[1]); sys.stdout.buffer.write(next(itertools.islice(sys.stdin.buffer,n-1,None)).rstrip(b"\r\n"))' "$((line + 1))" < <path> | sha256sum
```

Hashing the decoded string instead would make the digest depend on this
process's Unicode error handling rather than on the file.

A format whose records have no source line addresses them differently and
documents the departure at the top of its adapter. Both consumer exports are
JSON arrays whose elements run from kilobytes to megabytes, so `line` is the
message's position in the reconstructed thread — the order that makes a session
countable — `turn_id` is the vendor's own message id, which locates it exactly,
and the digest is over that message's canonical serialization rather than over a
line:

```python
sha256(records.dumps(message).encode())
```

`records.dumps` sorts every key at every level, so this reproduces from the
export without this tool, which is the property the line digest was for.

Two properties are separated throughout, and the second is the one the audit
layer exists for:

1. **Provenance existence** — the claim points at an observation.
2. **Provenance sufficiency** — the observation establishes the claim.

The canonical failure is **unsupported inferential expansion**: observation O
becomes claim C, where C is plausible and O does not establish it.

## Contracts and checks

| Contract | Where | Test |
|---|---|---|
| Same corpus → byte-identical output | `records.dumps`, sorted counts | `test_determinism.py` |
| Read-only, no network | no network module in `src/` | review; stdlib-only |
| Fixtures are synthetic | hand-authored identifiers; prose reviewed | `test_boundaries.py` + review |
| Private output cannot land in a commit-ready repository path | shared publication-path guard | `test_boundaries.py` |
| Self-exclusion by default | `scan.sessions.scan` | `test_scan.py` |
| Every report figure is labelled | `labels.Report`, `labels.lint` | `test_labels.py` |
| Observed and interpretive fields stay disjoint | `records.Finding.check` | `test_records.py` |
| Adapters fail loudly on format drift | `adapter.probe` | `test_scan.py` |

## Records

- **Turn** — role, timestamp, model, harness version, effort, content-kind
  counts, character counts, usage, API invariants, tool counts, written files,
  behavioural flags, and provenance.
- **Episode** — a typed prompt and the work that ran under it.
- **Sequence** — consecutive episodes a behavioural signal selected as a
  candidate challenge/repair chain. A candidate, not a finding.
- **Finding** — the inspectable artifact. `observed` and `labels` are separate
  fields and may not share a key; `check()` raises if they do.

## Scope boundary

The package owns deterministic corpus measurement: adapters, canonical records,
session enumeration, provenance, episode segmentation, signals, metrics, and
the audit layer. Fleet supervision, process control, consoles, and cost
estimation are outside this repository.

### The continuation-summary fix

A session that runs out of context is resumed with a summary written into a
`user` record. It is prose with no harness markup, so a not-typed pattern list
passes it and it reads as a typed prompt. Counted as one, it opens an episode
nobody asked for and attributes every turn after a compaction to an instruction
the operator never gave.

The fix is the `isCompactSummary` flag, with a text pattern as the fallback for
releases that do not set it. `test_scan.py` pins both.

### Why a chat export is traversed, not sorted

The log-shaped formats append records as they happen, so file order is history. A
ChatGPT export is not a log: `mapping` holds every node the conversation ever
had — regenerated answers, edited prompts, abandoned descendants — related by
`parent`/`children`, with `current_node` naming the leaf the reader last saw.

The schema decides the traversal. Neither object order nor timestamps declare
the visible branch, while `current_node` does. Emitting `mapping`
in file order or sorting nodes by timestamp can fold abandoned branches into
sequential turns, which inflates turn counts, episode counts, and every ratio
built on them.

The adapter walks parents from `current_node` and counts what it left behind.
When `current_node` is absent the branch is still settled if the tree has one
leaf; otherwise the conversation is reported as `ambiguous_active_branch` and
emits nothing. No timing heuristic decides it, and no repair is applied to a
timestamp that will not convert: it reports `malformed_timestamp` with
an empty `ts` rather than inventing a unit.

### Why an ambiguous branch emits nothing

The two consumer exports both store a conversation as a tree, and they differ in
exactly one field that matters. A ChatGPT export records `current_node`, the
leaf the reader last saw, so the visible thread is recoverable. A Claude export
records no equivalent: messages carry `parent_message_uuid` and nothing else —
no index, no sequence number, no active-branch pointer.

So `claude_export` emits a conversation only when exactly one message is
nobody's parent, and otherwise reports `ambiguous_active_branch` and
emits nothing.

The available alternative is to take the newest tip. That is a timing heuristic:
`chat_messages` is stored in timestamp order, so "last in the array" and "latest
timestamp" are one rule wearing two names, and neither is an ordering key the
schema establishes. It would resolve every branched conversation and would silently
place an abandoned branch into canonical history looking exactly like a thread
someone read. A measurement that cannot tell those apart is worse than a
measurement that is missing, because only one of them announces itself.

Reported, not hidden: the count is a figure in `stats`, so the gap is visible in
the same output that reports what was measured.

### Why lexicons ship empty

Word lists written while looking at the corpus they will be run against are
tuned to that corpus by construction: the phrases that come to mind are the
ones already on the screen. A series built from one measures its author as much
as its subject. Behavioural signals are the defaults for that reason, and
anything lexical is configuration a user supplies knowingly.

### Why self-exclusion is on by default

An instrument pointed at a corpus that contains its own development sessions
will measure them and report the result as a property of the corpus. Sessions
whose working directory is this tool's own are flagged either way;
`--include-self` decides only whether they count.

## Epistemic discipline

This project is partly about detecting semantic overreach, so it does not get
to commit it. Every design claim carries one of four statuses:

- **OBSERVED** — measured, with the measurement stated.
- **DERIVED** — follows from observations under a stated rule.
- **HYPOTHESIS** — worth testing; not established.
- **DESIGN CHOICE** — a preference, argued.

Standing hypotheses, named so nobody promotes them by habit:

- That provenance-sufficiency failures are frequent enough to be worth
  measuring.
- That the challenge taxonomy is adequate.
- That anything here generalises past the single corpus it was built against.

### The discovery/confirmation firewall

Patterns mined from a corpus are hypotheses. Nothing mined from a corpus is
reported as confirmed until it survives prospective draws or a held-out corpus.
Position effects are reported with distance-from-prompt controls because
conversation structure is a competing explanation.

`audit/` therefore separates the two regimes rather than blending them, and a
fixture is preregistered before its first confirmatory draw.
