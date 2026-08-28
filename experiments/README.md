# experiments

Prospective batteries built on the audit layer. One directory each.

| id | question | status |
|---|---|---|
| [m3a](m3a/README.md) | does a provenance challenge repair an unsupported claim while introducing a replacement? | registered, unsigned, unrun |

Nothing here is a finding. A registration that has not been signed and run
establishes nothing, and the machinery working is not a result.

## Why this exists

A pattern found in a corpus is a hypothesis. Reading more of the corpus does not
convert it into anything else: the same records that suggested it cannot also
test it, and a threshold chosen after the answers are visible is not a
threshold.

An experiment here is the conversion. It freezes a naturalistic failure into
bytes a model can be asked about again, fixes what would count as signal before
the first draw, and puts both in public where they cannot be revised once the
answers are known.

The scanner finds candidates. The audit layer freezes them. Neither takes the
draws.

## What an experiment directory holds

```
<id>/
  README.md          the question, what is frozen, what is still open
  registration.json  the preregistration: hashes, criterion, protocol
  fixture.json       frozen evidence bytes, the prompt, the challenged claim
  runtime.json       the inference condition and the runtime's identity
  bin/               a runner that refuses, a scorer, panel tooling
  labelling/         the prompt every labeller reads, and the panel roster
```

## The shape every experiment follows

**Freeze.** A fixture holds the evidence bytes with the provenance of every
span, the prompt, and the model-facing config. Bytes, not pointers — the
rationale is in the top-level [README](../README.md).

**Register.** Before the first draw, the registration pins the fixture, the
intervention, the taxonomy, the draw count, the stopping rule, and the statistic
and threshold that decide the answer. `preflight` refuses while any operator
decision is open, and there is no bypass flag.

**Sign.** The operator signs. The actor under pressure to finish is the one
running the draws, so the criterion is not theirs to write afterwards. A
registration should be signed over machinery that has been used, not machinery
that passes tests.

**Draw.** One request per attempt under one fixed inference condition. Every
draw is archived before anything reads it, with the digests that let a reader
re-derive what was asked.

**Label.** Semantic judgment is applied by registered readers who are not the
subject. M3a uses one human and two isolated model sessions; no automated judge
creates a label or consensus.

**Score.** The scorer grounds every label against the archive it claims to
describe, then returns the registered result mechanically. It refuses rather
than reporting a number it cannot establish.

## Rules that hold across all of them

- **A draw taken after any registered element changed is nonconfirmatory.**
  Changing one requires a new registration, not an amendment.
- **No registration adopts draws that predate it.** A registration written after
  its data is not a preregistration.
- **Discovery material confirms nothing.** The chain that motivated an
  experiment supplies its taxonomy and is not evidence for it.
- **A pattern noticed while running or scoring is discovery-only.** Promoting
  one requires a new registration.
- **Invalid draws are archived with their reason**, excluded from the
  denominator, and replaced under the same condition.
- **The machinery is not the measurement.** Its bytes are pinned by the release
  tag; the registration pins what the model is asked and what decides the
  answer.

## Adding one

1. Freeze a fixture with `corpus-audit freeze`, and verify it replays
   byte-identically.
2. Write `registration.json`. Leave every decision the sources do not determine
   in `operator_decisions`, and leave its typed field empty. Preflight reads the
   typed fields, so clearing the list resolves nothing.
3. Exercise the whole path by hand before asking for a signature — the runner,
   the labelling flow, the scorer.
4. Get the signature. Then draw.

Read [m3a](m3a/README.md) for a worked instance.
