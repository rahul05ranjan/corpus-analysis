# Related-work landscape: provenance sufficiency, repair dynamics, agent traces, and replayable corpus evaluation

**Snapshot:** 2026-08-11  
**Purpose:** related-work and positioning record for the `corpus-analysis` project.
**Epistemic status:** literature/tooling landscape, not a proof of novelty. “Not found” means *not found in the searches represented by this snapshot*, not “does not exist.”

---

## Executive summary

Four established areas bound the project:

1. **Claim–evidence support / attribution.** Existing work asks whether generated claims are attributable to identified evidence, whether retrieved evidence is sufficient, and whether source ownership is correct.
2. **Agent-trace debugging / provenance.** Existing work captures long execution traces, localizes critical failures, models agent provenance, and performs replay or repair.
3. **Self-correction / repair dynamics.** Existing work measures whether models correct errors and, increasingly, whether correction converges, oscillates, or damages previously correct content.
4. **Naturalistic-to-controlled evaluation.** Existing work collects real interaction trajectories, converts production failures into datasets, and reruns fixed inputs under controlled experiments.

The strongest apparent opening is **not any one of those components**. It is their composition around a narrower unit of measurement:

> **When a model is challenged on an unsupported evidence→claim edge, does it repair that edge without creating another unsupported edge, and how many recursive rounds are required before no new unsupported bridge appears?**

The project’s proposed `N_k` metric counts newly introduced unsupported bridges at repair round `k`; local convergence is `N_k = 0`.

In the primary-source search captured here, no evaluated system was found that combines all of the following:

```text
retrospective local transcript corpus
  -> deterministic provenance-addressed records
  -> candidate unsupported evidence→claim expansions
  -> recursive provenance challenge
  -> replacement-bridge counting (N_k)
  -> hash-frozen naturalistic fixture
  -> preregistered prospective repeated draws
  -> explicit discovery/confirmation firewall
```

That is the narrowest defensible differentiation. It does **not** license claims such as “first provenance framework,” “first claim-evidence verifier,” “first self-correction benchmark,” “first agent-trace debugger,” or “first trace-to-dataset system.”

---

# 1. Target lane

The project’s architecture, based on the current plan, is:

```text
raw transcripts
  -> normalized deterministic records
  -> measured corpus observations
  -> candidate evidence/claim sequences
  -> provenance-grounded audit (optional / interpretive)
  -> frozen fixtures
  -> prospective repeated evals
```

The key semantic distinction is:

- **provenance existence:** a claim points to an observation;
- **provenance sufficiency:** the observation actually establishes the claim.

The canonical target failure is **unsupported inferential expansion**:

```text
observation O is real
claim C is plausible
but O does not establish C
```

The recursive challenge protocol asks what observation establishes the claim and can record outcomes such as `SURVIVE`, `NARROW`, `RETRACT`, `SEEK`, `SUBSTITUTE`, and `OVERCONTRACT`.

The project’s unusual measurement target is not merely whether the challenged claim is eventually corrected. It asks whether the *repair itself* introduces a new unsupported evidence→claim bridge.

---

# 2. Related-work map

```text
                         CLAIM ↔ EVIDENCE SUPPORT
                                  |
             AIS ---- FActScore ---- MiniCheck
              |          |              |
             RARR       CoVe          VeriScore
                \       |             /
                 \   SURE-RAG       /
                  \  PaperTrail    /
                   \ Evidence-Ledger
                    \      |
                    ProvenanceGuard (factuality/MCP)
                           |
                           | claim/source support
                           |
       ---------------------------------------------------
       |                                                 |
 AGENT TRACE / PROVENANCE                         REPAIR DYNAMICS
       |                                                 |
   W3C PROV                                      RARR / CoVe
   PROV-AGENT                                    self-correction survey
   ProvenanceGuard (alignment)                   CyberCorrect
   TRAIL                                         Self-Correction Illusion
   AgentRx                                       Guarded Repair
   TrajDebug
   HarnessFix
   Causal Agent Replay
       |                                                 |
       ------------------- TARGET LANE -------------------
                             |
                  naturalistic transcript mining
                             +
                  evidence→claim sufficiency
                             +
                  replacement-bridge counting
                             +
                    recursive repair sequence
                             +
                   hash-frozen fixture promotion
                             +
                  prospective repeated battery
                             |
                   MonitrLLM / Phoenix / Langfuse
                (adjacent on trace→dataset→experiment)
```

There are **two unrelated 2026 papers named ProvenanceGuard** in this landscape:

- **Alvarez et al., arXiv:2606.18037** — source-aware factuality verification for MCP-grounded answers.
- **She, Liang & Kang, arXiv:2607.01236** — provenance-based alignment checks for proposed tool calls.

They should never be cited interchangeably.

---

# 3. Collision matrix

Legend:

- **E** — explicit in the primary-source abstract/docs reviewed.
- **P** — partial / adjacent overlap.
- **—** — not observed as a stated contribution in the reviewed primary source. This is not proof of absence from the full work.
- **?** — not determined.

| Work | Naturalistic traces | Explicit provenance | Evidence sufficiency | Iterative repair | Repair dynamics | New unsupported-edge metric | Frozen/replay control | Prospective/held-out eval | Existing local corpus | Collision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ProvenanceGuard — factuality (2026) | E | E | E | E | P | — | P | E | — | **Very close** |
| ProvenanceGuard — alignment (2026) | E | E | E | P | — | — | — | E | — | **Very close on provenance-as-support** |
| SURE-RAG (2026) | — | E | **E** | — | — | — | P | E | — | **Very close on sufficiency** |
| Evidence-Ledger Adjudication (2026) | P | E | E | P | — | — | — | E | — | **Very close on claim/evidence routing** |
| PaperTrail (2026) | P | E | E | — | — | — | — | E | — | Close |
| CyberCorrect (2026) | — | — | P | **E** | **E** | P | — | E | — | **Very close on correction dynamics** |
| Self-Correction Illusion (2026) | — | — | P | E | E | P | **E** | E | — | **Very close methodologically** |
| Guarded Repair (2026) | — | P | P | E | **E** | P | P | E | — | Close on repair harm |
| Real-Time Detection & Repair (2026) | **E** | P | P | E | P | — | P | E | — | Close |
| TrajDebug (2026) | **E** | E | P | P | **E** | — | — | E | — | Close |
| AgentRx (2026) | **E** | E | P | — | — | — | — | E | — | Close |
| TRAIL (2025) | **E** | P | P | — | — | — | — | E | — | Close |
| HarnessFix (2026) | **E** | E | P | E | P | — | P | E | — | Close |
| BenchTrace (2026) | **E** | P | P | E | E | — | P | E | — | Close |
| Causal Agent Replay (2026) | P | **E** | P | E | **E** | — | **E** | E | — | Close on replay |
| PROV-AGENT (2025) | **E** | **E** | — | — | — | — | — | E | — | Infrastructure-adjacent |
| MonitrLLM (2026) | **E** | P | — | — | — | — | — | P | P | Close on naturalistic corpus |
| AIS (2023) | — | E | E | — | — | — | — | E | — | Foundational |
| RARR (2022) | — | E | E | **E** | P | — | — | E | — | Foundational |
| FActScore (2023) | — | P | **E** | — | — | — | — | E | — | Foundational |
| CoVe (2023) | — | P | P | **E** | P | — | — | E | — | Foundational |
| MiniCheck (2024) | — | P | **E** | — | — | — | — | E | — | Foundational |
| VeriScore (2024) | — | P | **E** | — | — | — | — | E | — | Foundational |
| Phoenix | **E** | P | P | P | — | — | **E** | **E** | P | Product/infra overlap |
| Langfuse | **E** | P | P | P | — | — | P | **E** | P | Product/infra overlap |
| claude-code-transcripts | **E** | P | — | — | — | — | P | — | **E** | Input-layer overlap |

## Matrix read

No reviewed source states a metric equivalent to:

> **number of new unsupported evidence→claim bridges introduced by the correction itself at each recursive repair round.**

The closest conceptual neighbor is **CyberCorrect’s overshoot**: correction can make a previously better state worse. The proposed `N_k` is narrower and semantic: a repair can fix the challenged proposition while adding another unsupported proposition.

Likewise, replay and trace-to-dataset workflows already exist. The differentiating candidate is the complete chain:

> **naturalistic failure → provenance-addressed fixture → recursive challenge → replacement-bridge measurement → preregistered repeated evaluation.**

---

# 4. Closest prior art, ranked

## 4.1 ProvenanceGuard: Source-Aware Factuality Verification for MCP-Based LLM Agents

**Alvarez, Rajan, Mugel, Orús — 2026 — arXiv:2606.18037**  
Source: https://arxiv.org/abs/2606.18037

### Core question
Can an MCP-grounded answer be factually supported but attributed to the wrong evidence source?

### Method
The system consumes captured MCP traces with stable tool/source IDs and raw outputs, decomposes answers into atomic claims, routes claims to source-specific evidence, checks support, separately checks attribution, and emits per-claim and answer-level verdicts. Blocked answers can be revised and reverified.

### Reported evidence
- 281 medical-domain MCP-agent traces.
- 266-trace adjudicated subset.
- 2,325 LLM-assisted claim labels.
- 361 held-out human-verified labels.
- held-out block F1 reported as 0.802.
- source accuracy reported as 0.858 over 260 source-eligible claims.

### Collision
This is the closest overall collision on:
- captured traces;
- stable provenance;
- atomic claims;
- claim↔evidence support;
- source ownership;
- repair + reverification.

### Remaining distinction
The stated contribution is source-aware factuality and cross-source conflation. The abstract does not state a metric for **new unsupported claims introduced during repair**, recursive challenge depth, or `N_k = 0`.

### Positioning consequence
Do not claim claim-level provenance checking, source-aware verification, or repair-and-reverify as novel. Position the new work around **repair-sequence entailment drift** and naturalistic→fixture experimentalization.

---

## 4.2 CyberCorrect: A Cybernetic Framework for Closed-Loop Self-Correction in Large Language Models

**Wu, Liu, Shu — 2026 — arXiv:2605.17305**  
Source: https://arxiv.org/abs/2605.17305

### Core question
How should iterative LLM correction be evaluated when final accuracy hides unstable trajectories?

### Method
Closed-loop correction with:
- error detector;
- type-directed controller;
- convergence judge.

### Metrics
- convergence rate;
- overshoot rate;
- oscillation rate.

### Reported evidence
- CyberCorrect-Bench: 440 reasoning tasks with annotated error types and correction paths.
- reported final accuracy: 79.8%.
- reported +6.2 percentage points over best compared correction method.
- reported 41% reduction in overshoot.

### Collision
This is the closest prior art on **repair dynamics as a first-class evaluation object**.

### Remaining distinction
CyberCorrect measures task/error correction dynamics. `N_k` measures something more specific: **new unsupported evidence→claim edges created while repairing the target edge**.

### Positioning consequence
Do not say “first convergence metric for LLM correction.” A safer description is **a provenance-specific recursive repair metric**.

---

## 4.3 The Self-Correction Illusion: LLMs Correct Others but Not Themselves

**Chen, Su, Chiang — 2026 — arXiv:2606.05976**  
Source: https://arxiv.org/abs/2606.05976

### Core question
Does correction depend on the role wrapper carrying an otherwise identical erroneous claim?

### Method
The erroneous claim is held **byte-identical and SHA-256 verified**. Only the message role changes: own thought, user, tool, or memory.

### Reported evidence
- 13 model-domain cells;
- 7 model families;
- 3 domains;
- n=30 paired tasks per cell;
- reported correction-rate lift of 23–93 percentage points when the claim is externally wrapped;
- 10/13 cells reported at p<0.001.

### Collision
Not on provenance sufficiency itself, but extremely close methodologically:
- exact-byte freeze;
- one controlled intervention;
- repeated paired measurement;
- correction behavior as dependent variable.

### Positioning consequence
Strong precedent for fixture hashing and for treating apparently superficial harness structure as a causal experimental variable.

---

## 4.4 SURE-RAG: Sufficiency and Uncertainty-Aware Evidence Verification for Selective RAG

**Qiu, Han, Huang — 2026 — arXiv:2605.03534**  
Source: https://arxiv.org/abs/2605.03534

### Core question
Does the retrieved evidence actually justify the candidate answer, rather than merely being relevant?

### Method
Pair-level claim/evidence relations are aggregated into answer-level:
- coverage;
- relation strength;
- disagreement;
- conflict;
- retrieval uncertainty.

The system predicts support/refute/insufficient and can abstain.

### Reported evidence
The paper reports Macro-F1 0.9075 on HotpotQA-RAG v3 under its calibrated protocol and explicitly shows that controlled evidence-sufficiency verification and natural hallucination detection are distinct tasks.

### Collision
Very close to the project’s **provenance existence vs provenance sufficiency** distinction.

### Remaining distinction
RAG verifier rather than transcript-mining + recursive repair framework.

### Positioning consequence
Use “provenance sufficiency” as an operational term, not as a claim that evidence-sufficiency verification is new.

---

## 4.5 Evidence-Ledger Adjudication for Claim-Evidence Traceability

**Chen, Yu, Wang — 2026 — arXiv:2607.26512**  
Source: https://arxiv.org/abs/2607.26512

### Core question
Can each generated claim be paired with an evidence packet and routed according to whether support is sufficient?

### Method
Each claim receives a support relation. Unsupported, contradicted, or mixed-evidence claims are routed back to the author.

### Reported evidence
- 2,335-row blind benchmark from AVeriTeC, CLIMATE-FEVER, and SciFact.
- reported relation accuracy 0.676.
- reported macro-F1 0.601.
- 1,270/1,435 problematic gold claims routed.
- 295/900 supported claims also routed.

### Collision
Very close on auditable claim/evidence ledgers and **route-back on insufficient support**.

### Remaining distinction
Primary unit is relation adjudication and routing, not the epistemics of the repair response itself.

---

## 4.6 PaperTrail: A Claim-Evidence Interface for Grounding Provenance in LLM-based Scholarly Q&A

**Martin-Boyle, Leckey, Brown, Kaur — 2026 — arXiv:2602.21045**  
Source: https://arxiv.org/abs/2602.21045

### Core question
Can fine-grained claim/evidence mappings help researchers detect unsupported claims and omissions that coarse citations hide?

### Method
Decomposes answers and sources into discrete claims/evidence, then maps support, unsupported assertions, and omissions.

### Reported evaluation
Within-subjects study with 26 researchers and two scholarly editing tasks.

### Collision
Strong on claim/evidence decomposition and provenance granularity.

### Remaining distinction
Human verification UI rather than recursive correction-sequence measurement.

---

## 4.7 ProvenanceGuard: Safeguarding LLM Agents from Misalignment through Provenance Analysis

**She, Liang, Kang — 2026 — arXiv:2607.01236**  
Source: https://arxiv.org/abs/2607.01236

### Core question
Is a proposed tool invocation supported by traceable evidence in the agent context and aligned with user intent?

### Method
Provenance-based runtime guardrail that only admits actions judged to be supported/aligned before execution.

### Reported evidence
Evaluated on Agent-SafetyBench and WorkBench across 10 backbone LLMs. The abstract reports large error-rate reductions on misaligned traces relative to LLM-as-a-judge baselines.

### Collision
Conceptually important because it treats **support by traceable context** as a runtime admission property.

### Remaining distinction
Action alignment / tool-call admission, not semantic repair recursion.

---

## 4.8 Real-Time Detection and Repair of LLM Agent Failures

**Dubey — 2026 — arXiv:2608.02464**  
Source: https://arxiv.org/abs/2608.02464

### Core question
How much agent failure detection can be done from cheap observable telemetry rather than an LLM judge?

### Method
- one-class telemetry monitors;
- deterministic verification that recomputes stated totals and required tool coverage;
- rollback and rerun after detection.

### Reported evidence
- 2,823 committed agent episodes across three frameworks;
- monitor AUROC 0.872;
- deterministic verifier catches 60% of failures, 96% with coverage check, at 0/63 false positives in the stated head-to-head;
- live repair recovers 45% of failures vs 16% resampling control;
- task success reported from 52% to 73%.

### Collision
Very relevant architectural precedent:
- deterministic facts beneath interpretive/behavioral monitoring;
- real traces;
- explicit verification;
- repair/replay.

### Remaining distinction
Online execution failures rather than evidence→claim entailment.

---

## 4.9 TRAJDEBUG: Tracing Error Lifecycle to Identify Critical Failures in Long-Horizon Agent Trajectories

**Qi et al. — 2026 — arXiv:2608.06346**  
Source: https://arxiv.org/abs/2608.06346

### Core question
Which errors in a long failed trajectory remain causally responsible for terminal failure after later steps potentially resolve earlier mistakes?

### Method
Tracks error discovery, resolution status, and terminal impact with multi-granularity history compression and evidence-based identification.

### Benchmark
486 manually annotated failed trajectories from Tau2Bench and SWE-Bench Pro.

### Collision
Important precedent for **error lifecycle rather than one-shot error labeling**.

### Remaining distinction
Critical failure attribution rather than provenance-sufficiency repair.

---

## 4.10 AgentRx: Diagnosing AI Agent Failures from Execution Trajectories

**Barke et al. — 2026 — arXiv:2602.02475**  
Source: https://arxiv.org/abs/2602.02475

### Core question
How can critical failure steps be localized in probabilistic, long-horizon, tool-mediated trajectories?

### Method
Constraint synthesis + stepwise evaluation + auditable validation log with evidence; LLM judge uses the log for critical-step/category localization.

### Benchmark
115 manually annotated failed trajectories spanning structured API workflows, incident management, and open-ended web/file tasks.

### Collision
Evidence-backed diagnostic claims and trace normalization/taxonomy.

### Remaining distinction
Step localization, not claim/evidence repair recursion.

---

## 4.11 TRAIL: Trace Reasoning and Agentic Issue Localization

**Deshpande et al. — 2025 — arXiv:2505.08638**  
Source: https://arxiv.org/abs/2505.08638

### Contribution
- formal taxonomy of agent error types;
- 148 large human-annotated traces;
- trace-debugging evaluation grounded in single- and multi-agent benchmarks.

The paper reports its best evaluated long-context model at 11% on the trace-debugging task.

### Collision
Trace corpus + taxonomy + process-level evaluation.

### Remaining distinction
Trace debugging is the end task; no recursive provenance challenge.

---

## 4.12 From Failed Trajectories to Reliable LLM Agents: Diagnosing and Repairing Harness Flaws (HarnessFix)

**Chen, Wang, Liu, Wang, Wang — 2026 — arXiv:2606.06324**  
Source: https://arxiv.org/abs/2606.06324

### Core question
When an agent fails, which harness layer and which trajectory evidence are responsible?

### Method
Compiles raw traces and harness code into a Harness-aware Trace Intermediate Representation (HTIR), preserving provenance/control flow, then generates scoped repair operators and validates patches.

### Evaluation
SWE-Bench Verified, Terminal-Bench 2.0 Verified, GAIA, AppWorld. The abstract reports 15.2%–50.0% held-out improvement over initial harnesses.

### Collision
Very relevant to normalized trace IR, provenance, and the broader harness-effect research program.

### Remaining distinction
Repairs the harness, not unsupported semantic bridges in model repair responses.

---

## 4.13 BenchTrace: A Benchmark for Testing Reflection Ability and Controlled Evolution in LLM Agents

**Huang et al. — 2026 — arXiv:2605.29225**  
Source: https://arxiv.org/abs/2605.29225

### Core question
Do agents correctly identify prior failures, and does that failure experience prevent recurrence under controlled evaluation?

### Data / metric
- 1,821 annotated episodes across six tasks.
- Reflection Evaluation.
- Evolution Evaluation.
- Failure Avoidance Rate (FAR).

### Collision
Strong precedent for **past failure → targeted controlled evaluation**.

### Remaining distinction
Reflection/evolution and future failure avoidance, not recursive claim-evidence repair.

---

## 4.14 Causal Agent Replay: Counterfactual Attribution for LLM-Agent Failures

**Shah — 2026 — arXiv:2606.08275**  
Source: https://arxiv.org/abs/2606.08275

### Core question
Which step actually caused an agent failure?

### Method
Structural causal model over a run; intervene on a step; re-execute forward under the same stochastic policy; estimate outcome distribution shifts. Includes a Monte-Carlo Shapley estimator.

### Collision
Strong replay/intervention precedent.

### Remaining distinction
Causal step attribution, not provenance-sufficiency repair.

### Positioning consequence
Do not imply replay itself is novel.

---

## 4.15 PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows

**Souza et al. — 2025 — arXiv:2508.02866**  
Source: https://arxiv.org/abs/2508.02866

### Core contribution
Extends W3C PROV for agent-centric metadata such as prompts, responses, and decisions and integrates agent interactions into workflow provenance using MCP.

### Collision
Fine-grained agent provenance representation and capture.

### Remaining distinction
Provenance capture/modeling, not semantic sufficiency or repair dynamics.

---

## 4.16 MonitrLLM: A Community-Centered Evaluation Infrastructure for Large Language Models

**Ojewale, Encarnación, Venkatasubramanian, Metaxa — 2026 — arXiv:2608.02409**  
Source: https://arxiv.org/abs/2608.02409

### Core question
Can full real conversation trajectories be linked to user-defined task intent and outcomes?

### Pilot
- 26 college students;
- 206 evaluation reports with full ChatGPT transcripts;
- mean satisfaction 4.19/5;
- reported task failure rate 23.1%;
- multi-turn conversations reported failing 2.5× as often as single-turn interactions.

### Collision
One of the closest works on **naturalistic full-conversation data as evaluation infrastructure**.

### Remaining distinction
User outcome evaluation, not provenance/repair behavior.

---

# 5. Foundational attribution / factuality lineage

These works make broad novelty claims unavailable.

## AIS — Measuring Attribution in Natural Language Generation Models

**Rashkin et al. — Computational Linguistics 2023**  
Source: https://aclanthology.org/2023.cl-4.2/

Defines **Attributable to Identified Sources (AIS)** and an annotation framework in which generated claims about the external world are verified against an independent provided source.

**Consequence:** support-by-identified-evidence is established prior art.

---

## RARR — Researching and Revising What Language Models Say, Using Language Models

**Gao et al. — 2022 — arXiv:2210.08726**  
Source: https://arxiv.org/abs/2210.08726

Finds attribution for generated text and post-edits unsupported content while trying to preserve the original.

**Consequence:** evidence-backed revision is established.

---

## FActScore

**Min et al. — 2023 — arXiv:2305.14251**  
Source: https://arxiv.org/abs/2305.14251

Breaks long-form text into atomic facts and scores the fraction supported by a reliable source.

**Consequence:** atomic decomposition + support scoring is established.

---

## Chain-of-Verification (CoVe)

**Dhuliawala et al. — 2023 — arXiv:2309.11495**  
Source: https://arxiv.org/abs/2309.11495

Draft → generate verification questions → answer independently → produce revised verified response.

**Consequence:** structured iterative verification/correction is established.

---

## MiniCheck

**Tang, Laban, Durrett — 2024 — arXiv:2404.10774**  
Source: https://arxiv.org/abs/2404.10774

Builds compact claim-grounding fact-checkers and the LLM-AggreFact benchmark.

**Consequence:** support classification should be treated as replaceable machinery, not the novelty center.

---

## VeriScore

**Song, Kim, Iyyer — 2024 — arXiv:2406.19276**  
Source: https://arxiv.org/abs/2406.19276

Separates verifiable from unverifiable claims before checking factuality/support across diverse long-form generation tasks.

**Consequence:** the audit layer should define what claim types are actually auditable.

---

## Critical survey of LLM self-correction

**Kamoi et al. — 2024 — arXiv:2406.01297**  
Source: https://arxiv.org/abs/2406.01297

Separates self-correction settings by feedback source and warns that research questions and evaluation conditions are often underspecified.

**Consequence:** describe the provenance challenge as an explicit feedback intervention; do not casually generalize to “self-correction.”

---

# 6. Additional repair neighbor: Guarded Repair

## Guarded Repair for Harm-Aware Post-hoc Replacement of LLM Mathematical Reasoning

**Xia — 2026 — arXiv:2605.24613**  
Source: https://arxiv.org/abs/2605.24613

### Core question
How can a system repair an incorrect reasoning trace without breaking traces that were already correct?

### Method
Selective repair with deterministic verification guards; answer-changing replacements are admitted only when guards support them.

### Reported evidence
The abstract reports GSM8K initial accuracy of 95.60% and final 96.89%, fixing 17/58 remaining errors with no measured broken-correct cases in the main run. It also reports that unconstrained direct regeneration breaks 47 initially correct answers.

### Relevance
Repair can introduce harm.

### Difference
The harm unit is correctness of the repaired reasoning/output, not new unsupported evidence→claim edges.

---

# 7. Field-level survey

## From Agent Traces to Trust: Evidence Tracing and Execution Provenance in LLM Agents

**Wang et al. — 2026 — arXiv:2606.04990**  
Source: https://arxiv.org/abs/2606.04990

This survey explicitly unifies:
- retrieval grounding;
- claim support;
- tool-use safety;
- memory lineage;
- observability;
- debugging;
- audit;
- recovery.

It identifies open challenges including:
- unified trace schemas;
- claim-level and semantic provenance;
- realistic execution-trace benchmarks;
- recovery-oriented evaluation;
- privacy-aware audit infrastructure.

### Positioning consequence
The `corpus-analysis` project sits squarely in an already-recognized field. Cite this survey as a map, then state the narrower bridge/repair contribution.

---

# 8. Tooling / OSS landscape

## Arize Phoenix

Official docs: https://arize.com/docs/phoenix

Phoenix supports:
- traces/spans for LLM, retrieval, tools, and custom logic;
- code, LLM, and human evaluations;
- datasets built from production traces;
- experiments over fixed inputs;
- span replay;
- repeated experiment runs.

### Collision
Phoenix already covers **trace → dataset → experiment** as a general platform.

### Remaining distinction
`corpus-analysis` is local transcript-first and opinionated around provenance sufficiency / recursive repair, with a deterministic scan layer rather than a general observability backend.

---

## Langfuse

Official docs: https://langfuse.com/docs

Langfuse supports:
- LLM application traces;
- datasets and dataset items;
- experiment runs;
- evaluator functions and run-level evaluators;
- trace-linked scores.

### Collision
General trace/dataset/experiment infrastructure.

### Remaining distinction
Same as Phoenix: product platform, not a narrow provenance-repair corpus instrument.

---

## OpenInference / OpenTelemetry

OpenInference: https://github.com/Arize-ai/openinference

Defines OpenTelemetry-oriented semantic conventions and instrumentation for LLM apps, including typed agent/LLM/tool spans.

### Relevance
Potential interoperability target if the project later exports a generic trace representation.

---

## W3C PROV

PROV-O: https://www.w3.org/TR/prov-o/  
PROV Primer: https://www.w3.org/TR/prov-primer/

W3C PROV models provenance using entities, activities, agents, derivation, attribution, usage, and generation relations.

### Relevance
Useful vocabulary and a reason not to invent broad provenance terminology unnecessarily.

---

## `simonw/claude-code-transcripts`

Repository: https://github.com/simonw/claude-code-transcripts

Reads local Claude Code JSON/JSONL sessions from `~/.claude/projects`, including optional agent sessions, and converts them to browsable HTML archives.

### Collision
Direct local Claude Code transcript ingestion.

### Remaining distinction
Rendering/publishing transcripts rather than deterministic corpus measurement, semantic provenance auditing, or fixture/eval promotion.

### Positioning consequence
Do not claim that parsing local Claude Code session JSONL is novel.

---

# 9. What appears genuinely differentiated

This section is a **search-grounded positioning hypothesis**, not a novelty finding.

## 9.1 Replacement-bridge measurement

The strongest candidate contribution is treating correction output as a new object that can contain **new unsupported evidence→claim edges even after the challenged claim is successfully repaired**.

Neighboring metrics include:
- final accuracy;
- convergence rate;
- overshoot;
- oscillation;
- repair rate;
- failure avoidance.

`N_k` asks something different:

> How many new unsupported evidence→claim bridges were introduced at repair round `k`?

---

## 9.2 Recursive provenance challenge as an evaluation object

Most support systems stop at “claim supported / unsupported / insufficient.”

The proposed protocol asks:

1. what observation establishes this claim?
2. if unsupported, narrow/retract/seek;
3. audit the repair for newly introduced unsupported bridges;
4. recurse;
5. stop locally when `N_k = 0`.

No exact equivalent was found in the reviewed primary sources.

---

## 9.3 Naturalistic failure → hash-frozen prospective fixture

The proposed pipeline is unusually explicit:

1. discover a failure in a real transcript corpus;
2. preserve exact source provenance;
3. keep discovery labels provisional;
4. freeze fixture bytes and model-facing config;
5. preregister intervention, taxonomy, draw count, stopping rule, and signal criterion;
6. run fresh repeated draws;
7. route any new patterns surfaced by the run back to discovery rather than counting them as confirmation.

Trace replay and trace-to-dataset conversion have prior art. No exact equivalent of the discovery/confirmation firewall was found in the reviewed primary sources.

---

## 9.4 Deterministic scan / interpretive audit split

The project’s tool contract is also useful differentiation:

- raw corpus normalization is deterministic;
- scan output remains useful with no model attached;
- observed text/provenance and interpretive labels are separate;
- audit claims must reference scan-layer provenance;
- report claims can carry explicit epistemic classes;
- interpretive hypotheses do not silently become scan facts.

This is better described as an architectural/tool contract than as a research novelty claim.

---

# 10. Novelty-safe copy that can ship

## One-sentence README positioning

> A local-first toolkit for turning agent/chat transcript corpora into provenance-addressed evidence, mining candidate evidence→claim failures, and promoting selected naturalistic failures into frozen replay fixtures for prospective evaluation.

## Related-work positioning

> Existing work separately addresses claim-evidence support, evidence sufficiency, agent-trace debugging, provenance capture, self-correction, and trace-to-dataset experimentation. This toolkit connects those layers around a narrower unit: whether a provenance challenge repairs an unsupported evidence→claim edge without introducing a replacement unsupported bridge.

## Metric language

> We record `N_k`, the number of newly introduced unsupported evidence→claim bridges at repair round `k`, and define local convergence as `N_k = 0`.

Use **“we define”**, not “we introduce the first.”

## Naturalistic / confirmatory language

> Naturalistic transcript mining is discovery-only. A candidate failure becomes a confirmatory fixture only after its bytes, prompt/config, intervention, outcome taxonomy, draw count, stopping rule, and signal criterion are frozen before fresh draws.

## Landscape language

> In a primary-source landscape search frozen on 2026-08-11, we found close work on evidence sufficiency, source-aware factuality, agent-trace debugging, correction dynamics, provenance capture, and replay, but did not find an evaluated system combining retrospective transcript mining with recursive replacement-bridge measurement and preregistered fixture replay.

---

# 11. Claims not supported by this landscape

Do not ship these without a deeper systematic review and stronger evidence:

- “first provenance framework for LLM agents”
- “first claim-evidence verifier”
- “first evidence-sufficiency evaluator”
- “first system to audit agent traces”
- “first naturalistic LLM evaluation framework”
- “first trace-to-dataset workflow”
- “first replay system”
- “first self-correction convergence metric”
- “first deterministic verifier for agents”
- “first tool to analyze Claude Code JSONL”
- “first system to turn failures into eval cases”
- “LLMs do not learn from correction”
- “constraint is the only way to achieve grounded repair”
- “unsupported inferential expansion is universal”
- “unsupported inferential expansion is frequent across models”

The current evidence is enough to justify testing those directions, not asserting them.

---

# 12. Suggested confirmatory comparisons

If the project yields a publishable result, useful baselines include:

### Claim-support baselines
- compact verifier such as MiniCheck;
- direct LLM-as-judge support classification;
- source-blind vs provenance-aware verification where multiple sources exist.

### Repair baselines
- generic “reconsider/check your answer” prompt;
- Chain-of-Verification-style verification;
- evidence-bearing provenance challenge;
- mechanically constrained repair format.

### Sequence metrics
Report conventional and project-specific outputs:
- target repair rate;
- final support rate;
- convergence depth;
- `P(N_1 = 0)`;
- distribution of `N_k`;
- total unsupported bridges introduced before convergence;
- `SUBSTITUTE` rate;
- `OVERCONTRACT` rate;
- tokens / latency / rounds to convergence.

### Controls worth borrowing
- exact byte/hash freeze from Self-Correction Illusion;
- held-out/prospective split from factuality and evidence-ledger work;
- per-round dynamics from CyberCorrect;
- real-trace ecological validity from TRAIL / AgentRx / TrajDebug / MonitrLLM;
- deterministic verification wherever possible from Real-Time Detection and Repair;
- explicit repair-harm accounting from Guarded Repair.

---

# 13. Research questions exposed by the landscape

1. **Does successful target repair hide substitution?**  
   How often does a model correctly narrow/retract the challenged claim while introducing a new unsupported explanation?

2. **What controls `N_k`?**  
   Model family, response freedom, evidence type, prompt wording, role wrapper, task family, context length?

3. **Does mechanical response constraint reduce replacement bridges?**  
   This is a prospective hypothesis, not a conclusion from discovery material.

4. **Does message role change provenance repair?**  
   The Self-Correction Illusion makes this a strong candidate factor.

5. **How stable is human labeling of unsupported bridges?**  
   Inter-rater agreement and adjudication may be necessary if `N_k` becomes a public metric.

6. **Which bridge classes are mechanically decidable?**  
   Exact-string strengthening, numeric entailment, source identity, quantifiers, and schema constraints may admit deterministic checks.

7. **What is the correct replay unit?**  
   Full conversation, bounded evidence block, claim/evidence packet, or minimal counterexample?

8. **Does `N_k = 0` correlate with task success?**  
   It is only a local epistemic fixed point unless external outcomes support a broader claim.

9. **How much does naturalistic discovery bias fixture selection?**  
   User idiolect, task mix, model exposure, and sampling window remain possible selection effects.

10. **Does recursive provenance repair generalize across model families?**  
    One naturalistic sequence establishes existence only.

---

# 14. Search protocol

## Date
2026-08-11.

## Source policy
Technical claims in this snapshot were checked against primary sources:
- arXiv abstracts/pages;
- ACL Anthology;
- official W3C specifications;
- official project documentation / first-party repositories.

## Query families
The search used combinations of:
- LLM claim evidence provenance support
- evidence sufficiency verification
- source-aware factuality
- agent trace provenance
- execution trajectory debugging
- self-correction convergence / overshoot / oscillation
- repair introducing new errors / unsupported claims
- naturalistic conversation transcript evaluation
- captured agent traces / replay / fixed inputs
- local Claude Code JSONL transcript analysis
- trace-to-dataset experiments

An exact-phrase search for **“unsupported inferential expansion”** did not surface a directly matching LLM research contribution in the captured search.

## Limitations
This is broad landscape work, not a systematic review. Several of the closest papers are from 2026 and the field is moving on a days-to-weeks timescale. Before making a formal novelty claim:
1. rerun the search;
2. inspect citations/references of the closest 5–10 works;
3. search Semantic Scholar / Google Scholar citation graphs if available;
4. inspect newly posted arXiv work;
5. check conference proceedings if submission timing matters.

---

# 15. Ranked reading list

1. **ProvenanceGuard (Alvarez et al.)** — closest overall claim/source collision.
2. **CyberCorrect** — closest repair-dynamics collision.
3. **The Self-Correction Illusion** — strongest exact-freeze experimental precedent.
4. **SURE-RAG** — explicit evidence-sufficiency framing.
5. **Evidence-Ledger Adjudication** — claim/evidence routing and route-back.
6. **Real-Time Detection and Repair** — deterministic verification + real traces + repair.
7. **ProvenanceGuard (She et al.)** — provenance as support/admission for actions.
8. **TrajDebug** — error lifecycle across long trajectories.
9. **AgentRx** — evidence-backed trace diagnosis.
10. **BenchTrace** — failure history converted into controlled evaluation.
11. **HarnessFix** — normalized trace IR, provenance, scoped repair.
12. **Causal Agent Replay** — replay as intervention / attribution.
13. **MonitrLLM** — naturalistic full-conversation evaluation infrastructure.
14. **PaperTrail** — granular claim/evidence provenance UI.
15. **From Agent Traces to Trust** — field map / terminology.
16. **AIS / RARR / FActScore / MiniCheck / VeriScore / CoVe** — attribution/factuality lineage.
17. **TRAIL** — trace-debugging benchmark lineage.
18. **PROV-AGENT / W3C PROV** — provenance representation lineage.
19. **Guarded Repair** — harm-aware correction.

---

# 16. References

## Closest 2026 research
- Alvarez, A., Rajan, S., Mugel, S., & Orús, R. **ProvenanceGuard: Source-Aware Factuality Verification for MCP-Based LLM Agents.** arXiv:2606.18037. https://arxiv.org/abs/2606.18037
- She, Y., Liang, Y., & Kang, E. **Safeguarding LLM Agents from Misalignment through Provenance Analysis.** arXiv:2607.01236. https://arxiv.org/abs/2607.01236
- Wu, Y., Liu, Y., & Shu, Y. **CyberCorrect: A Cybernetic Framework for Closed-Loop Self-Correction in Large Language Models.** arXiv:2605.17305. https://arxiv.org/abs/2605.17305
- Chen, K.-Y., Su, F.-Y., & Chiang, J.-H. **The Self-Correction Illusion: LLMs Correct Others but Not Themselves.** arXiv:2606.05976. https://arxiv.org/abs/2606.05976
- Qiu, J., Han, Z., & Huang, C. **SURE-RAG: Sufficiency and Uncertainty-Aware Evidence Verification for Selective Retrieval-Augmented Generation.** arXiv:2605.03534. https://arxiv.org/abs/2605.03534
- Chen, G., Yu, Y., & Wang, W. **Evidence-Ledger Adjudication for Claim-Evidence Traceability.** arXiv:2607.26512. https://arxiv.org/abs/2607.26512
- Martin-Boyle, A., Leckey, C. A. C., Brown, M. C., & Kaur, H. **PaperTrail: A Claim-Evidence Interface for Grounding Provenance in LLM-based Scholarly Q&A.** arXiv:2602.21045. https://arxiv.org/abs/2602.21045
- Dubey, S. **Real-Time Detection and Repair of LLM Agent Failures.** arXiv:2608.02464. https://arxiv.org/abs/2608.02464
- Qi, Y. et al. **TRAJDEBUG: Tracing Error Lifecycle to Identify Critical Failures in Long-Horizon Agent Trajectories.** arXiv:2608.06346. https://arxiv.org/abs/2608.06346
- Barke, S. et al. **AgentRx: Diagnosing AI Agent Failures from Execution Trajectories.** arXiv:2602.02475. https://arxiv.org/abs/2602.02475
- Chen, M. et al. **From Failed Trajectories to Reliable LLM Agents: Diagnosing and Repairing Harness Flaws.** arXiv:2606.06324. https://arxiv.org/abs/2606.06324
- Huang, J. et al. **BenchTrace: A Benchmark for Testing Reflection Ability and Controlled Evolution in LLM Agents.** arXiv:2605.29225. https://arxiv.org/abs/2605.29225
- Shah, J. **Causal Agent Replay: Counterfactual Attribution for LLM-Agent Failures.** arXiv:2606.08275. https://arxiv.org/abs/2606.08275
- Ojewale, V., Encarnación, R., Venkatasubramanian, S., & Metaxa, D. **MonitrLLM: A Community-Centered Evaluation Infrastructure for Large Language Models.** arXiv:2608.02409. https://arxiv.org/abs/2608.02409
- Xia, H. **Guarded Repair for Harm-Aware Post-hoc Replacement of LLM Mathematical Reasoning.** arXiv:2605.24613. https://arxiv.org/abs/2605.24613
- Wang, Y. et al. **From Agent Traces to Trust: Evidence Tracing and Execution Provenance in LLM Agents.** arXiv:2606.04990. https://arxiv.org/abs/2606.04990

## Trace / provenance lineage
- Deshpande, D. et al. **TRAIL: Trace Reasoning and Agentic Issue Localization.** arXiv:2505.08638. https://arxiv.org/abs/2505.08638
- Souza, R. et al. **PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows.** arXiv:2508.02866. https://arxiv.org/abs/2508.02866

## Attribution / factuality / verification lineage
- Rashkin, H. et al. **Measuring Attribution in Natural Language Generation Models.** Computational Linguistics 49(4), 2023. https://aclanthology.org/2023.cl-4.2/
- Gao, L. et al. **RARR: Researching and Revising What Language Models Say, Using Language Models.** arXiv:2210.08726. https://arxiv.org/abs/2210.08726
- Min, S. et al. **FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation.** arXiv:2305.14251. https://arxiv.org/abs/2305.14251
- Dhuliawala, S. et al. **Chain-of-Verification Reduces Hallucination in Large Language Models.** arXiv:2309.11495. https://arxiv.org/abs/2309.11495
- Tang, L., Laban, P., & Durrett, G. **MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents.** arXiv:2404.10774. https://arxiv.org/abs/2404.10774
- Song, Y., Kim, Y., & Iyyer, M. **VERISCORE: Evaluating the factuality of verifiable claims in long-form text generation.** arXiv:2406.19276. https://arxiv.org/abs/2406.19276
- Kamoi, R. et al. **When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs.** arXiv:2406.01297. https://arxiv.org/abs/2406.01297

## Standards / tooling
- W3C. **PROV-O: The PROV Ontology.** https://www.w3.org/TR/prov-o/
- W3C. **PROV Model Primer.** https://www.w3.org/TR/prov-primer/
- Arize. **Phoenix documentation.** https://arize.com/docs/phoenix
- Langfuse. **Documentation.** https://langfuse.com/docs
- Arize AI. **OpenInference.** https://github.com/Arize-ai/openinference
- Willison, S. **claude-code-transcripts.** https://github.com/simonw/claude-code-transcripts
