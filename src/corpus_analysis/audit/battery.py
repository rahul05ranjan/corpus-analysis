"""A prospective battery: the deterministic half of running a registration.

Everything here is pure. It renders the exact bytes a model will receive,
hashes them, checks a registration against the artifacts it named, and computes
the quantities that are mechanically decidable from a scored round. Sending the
payload anywhere is not this module's job and is deliberately not importable
from it — the scan and audit layers hold no client of any kind, and the runner
that does lives outside the package.

Two separations are load-bearing.

**Observation and interpretation.** A raw draw archive holds what the model
returned, byte for byte, and nothing else. A `RoundScore` holds what a reader
concluded about it. Scoring never edits an archive, and the archive is written
before anything reads it.

**Target repair and the explanatory tail.** A round can repair the claim it was
challenged on and introduce fresh unsupported bridges in the same response.
`target_repaired` is therefore judged only on the sentences addressing
the challenged claim, and `new_bridges` is counted over the whole
response. A score that collapses them cannot see the behaviour the battery
exists to measure.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..records import dumps
from . import panel, registration
from .challenge import OUTCOMES, TAXONOMY_VERSION
from .fixtures import Fixture

#: The protocol this module implements. Bumped when the meaning of a scored
#: field changes, which makes previously scored rounds non-comparable.
#:
#: 2: the challenged claim is frozen fixture material rather than model output,
#: so SURVIVE means the model defended an unsupported claim instead of meaning
#: nothing needed repair. Rounds scored under 1 are not comparable to these.
PROTOCOL_VERSION = "2"

#: Outcomes whose definition already settles whether the challenged bridge is
#: gone, so a label that disagrees with them is a contradiction rather than a
#: judgment. NARROW, RETRACT and SEEK each state the claim was changed;
#: SUBSTITUTE states the bridge was removed and another introduced, which is
#: repair of the target with a tail, and is the behaviour under measurement.
REPAIRED_OUTCOMES = frozenset({"NARROW", "RETRACT", "SEEK", "SUBSTITUTE"})

#: Outcomes that leave the challenged claim standing. PERSIST is the ordinary
#: one: the claim is restated without being established.
#:
#: SURVIVE is here too, and it means something this experiment cannot treat as
#: an ordinary outcome. The target is unsupported by construction — frozen into
#: the fixture precisely because the evidence block does not establish it — so a
#: SURVIVE is a non-subject reader asserting that the fixture's premise is
#: wrong. It counts as unrepaired, and `fixture_premise_contested` reports it
#: separately, because a battery that quietly accumulates them is measuring a
#: broken fixture rather than a model.
UNREPAIRED_OUTCOMES = frozenset({"SURVIVE", "PERSIST"})

#: OVERCONTRACT is neither. Abandoning justified assumptions along with the
#: unsupported one may or may not leave the target repaired, and which it is
#: belongs to the reader rather than to this table.

#: Recorded as provenance, gated by nothing. A release tag pins the commit,
#: which pins these bytes.
INSTRUMENT_FILES = (
    "experiments/m3a/bin/m3a-panel",
    "experiments/m3a/bin/m3a-run",
    "experiments/m3a/bin/m3a-score",
    "src/corpus_analysis/audit/battery.py",
    "src/corpus_analysis/audit/challenge.py",
    "src/corpus_analysis/audit/fixtures.py",
    "src/corpus_analysis/audit/panel.py",
    "src/corpus_analysis/audit/registration.py",
)

#: The registered labelling prompt, relative to the repository root. Its bytes
#: are hashed into the registration separately from the instrument files: the
#: template is what three labellers read, and a change to it changes what the
#: labels mean rather than how they are computed.
LABELLING_PROMPT = "experiments/m3a/labelling/prompt-v1.txt"

def render_messages(fixture: Fixture) -> list[dict]:
    """The frozen context every draw starts from, built one way for every caller.

    The runner and the hash that pins the payload both come through here, so a
    registration cannot end up naming bytes that differ from the ones sent.

    This is the context *before* the challenge. When the fixture freezes prior
    turns, the last of them is the claim under measurement, and no model output
    is in here at all — which is the point: every draw is challenged on the same
    sentence rather than on whatever it happened to say first.
    """
    question = str(fixture.config.get("question") or "")
    blocks = "\n\n".join(span.text for span in fixture.evidence)
    return [
        {"role": "system", "content": fixture.prompt},
        {"role": "user", "content": f"{blocks}\n\n{question}"},
        *[t.as_message() for t in fixture.prior_turns],
    ]


def frozen_target(fixture: Fixture) -> str:
    """The claim every k=1 challenge is issued against.

    Read from the fixture, never from a label. The target is a registered
    element: which sentence was challenged is not something a reader gets to
    decide after seeing the answer, and a `target_quote` supplied by a labeller
    and checked against the *correction* lets any phrase in the response stand
    in for the claim that was actually challenged.
    """
    for turn in reversed(fixture.prior_turns):
        if turn.role == "assistant":
            return turn.text
    return ""


def challenge_message(intervention: str, quote: str,
                      template: str = "") -> dict:
    """The user turn that issues the challenge, always naming its target.

    Every round quotes the sentence it is asking about, k=1 included. A bare
    "what observation establishes that claim?" after a multi-sentence answer
    leaves "that claim" for the model to resolve, so the referent becomes part
    of what is being measured instead of part of what was fixed.
    """
    if not quote:
        raise ValueError("a challenge must name the claim it asks about")
    if not template:
        raise ValueError(
            "a challenge against a quoted claim needs the registered "
            "recursive_challenge_template")
    return {"role": "user", "content": template.format(quote=quote)}


def render_round_messages(fixture: Fixture, intervention: str,
                          history: list[tuple[str, str]],
                          template: str = "") -> list[dict]:
    """The exact message list round k sends.

    `history` is the earlier rounds in order, as (response, next_bridge_quote)
    pairs: what the model answered at that round, and the bridge the following
    challenge was issued against. It comes from validated labels, so a round is
    built from quotes already checked against the archive it came from — a
    recursion driven by unvalidated text is a recursion into invented material.
    """
    messages = render_messages(fixture)
    messages.append(challenge_message(intervention, frozen_target(fixture), template))
    for response, next_quote in history:
        messages.append({"role": "assistant", "content": response})
        messages.append(challenge_message(intervention, next_quote, template))
    return messages


def expected_target(fixture: Fixture, prior_label: dict | None) -> str:
    """What round k must have been challenged on, derived rather than asserted.

    k=1 is the frozen claim. Later rounds are the first newly introduced bridge
    of the round before, taken from a label whose quotes have already been
    checked against the archive they came from.
    """
    if prior_label is None:
        return frozen_target(fixture)
    new_bridges = list(prior_label.get("new_bridges") or [])
    return new_bridges[0] if new_bridges else ""


def payload_sha256(fixture: Fixture) -> str:
    """Digest over the frozen context, not over a description of it."""
    return hashlib.sha256(dumps(render_messages(fixture)).encode("utf-8")).hexdigest()


def request_sha256(messages: list[dict]) -> str:
    """Digest over the exact messages one round sent.

    Recorded per round. The registration pins the frozen context; this pins what
    a given round actually asked, which for k>1 includes model output that no
    registration could have named in advance.
    """
    return hashlib.sha256(dumps(messages).encode("utf-8")).hexdigest()


def accepted_registration_digests(reg, root: Path | str) -> tuple[set[str], list[str]]:
    """Digests an archive may carry and still be scored against `reg`.

    Walks the whole supersession chain, because a draw is archived once and the
    registration may be corrected more than once after it. An archive taken
    under v1 must stay scoreable under v3 for exactly as long as v3 asks the
    same question of the same bytes — and stop the moment it does not.

    Every ancestor is compared against `reg` itself, not against the version
    that replaced it. Comparing neighbours would let a chain of individually
    small steps arrive somewhere the original draws are no longer evidence
    about, each hop looking innocent.

    A superseded registration is accepted only after being loaded and shown to
    match. Accepting on the strength of a `supersedes` field alone would make
    the field a way to adopt any archive at all.
    """
    digests: set[str] = set()
    problems: list[str] = []
    current, seen = reg, set()

    while True:
        sup = dict(getattr(current, "supersedes", {}) or {})
        if not sup:
            return digests, problems

        recorded = str(sup.get("sha256") or "")
        label = f"registration {sup.get('version', '?')}"
        if recorded in seen:
            problems.append(f"the supersession chain loops at {label}")
            return digests, problems
        seen.add(recorded)

        path = Path(root) / str(sup.get("path") or "")
        if not path.is_file():
            problems.append(f"the superseded {label} is missing: {sup.get('path')}")
            return digests, problems
        if registration_file_sha256(path) != recorded:
            problems.append(
                f"the superseded {label}'s bytes do not match the digest recorded "
                "for it; the draws it covers cannot be identified")
            return digests, problems

        older = registration.load(path)
        differences = registration.determining_differences(older, reg)
        if differences:
            problems.append(
                f"{label} differs on " + ", ".join(differences) + "; its draws "
                "measured a different experiment and are not evidence about this one")
            return digests, problems

        digests.add(recorded)
        current = older


def registration_file_sha256(path: Path | str) -> str:
    """Digest over the signed registration's bytes.

    Not the payload digest. The payload pins what the model was asked; this pins
    the threshold, the recursion cap, the taxonomy, the stopping rule and the
    signature — every element that decides what the answer means. Two
    registrations with identical payloads and opposite decision rules share a
    payload digest and differ here, so this is the one an archive records.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def instrument_digests(repo_root: Path | str,
                       paths: tuple[str, ...] = ()) -> dict:
    """Digests over the files whose bytes decide what a draw measures.

    Keyed by repo-relative path so a mismatch names the file that moved. A file
    the registration named and the tree no longer has hashes to "", which is a
    mismatch rather than a silent pass.
    """
    root = Path(repo_root)
    return {rel: (hashlib.sha256((root / rel).read_bytes()).hexdigest()
                  if (root / rel).is_file() else "")
            for rel in sorted(paths or INSTRUMENT_FILES)}


def runtime_sha256(runtime: dict) -> str:
    """Digest over the inference configuration a draw is reproducible under."""
    return hashlib.sha256(dumps(runtime).encode("utf-8")).hexdigest()


#: Sampling parameters sent on every request. A parameter left out is one the
#: server chooses, which makes the draws a sample from a distribution nobody
#: recorded.
SAMPLING = ("temperature", "top_p", "top_k", "min_p",
            "repetition_penalty", "max_tokens", "seed")


def served_model_id(runtime: dict) -> str:
    """The model name the request names, from the identity block that pins it.

    One data path. When this read the top level and the identity block held the
    pinned value, the request went out with `"model": null` — and a server with
    one model loaded answers that perfectly happily, so every draw would have
    been archived without naming what produced it.
    """
    identity = runtime.get("identity") or {}
    return str(identity.get("served_model_id") or runtime.get("served_model_id") or "")


def request_config(runtime: dict) -> dict:
    """The exact inference condition a draw is taken under.

    Defined here rather than in the runner because the scorer has to check it.
    A condition the runner builds and nothing else can reconstruct is a
    condition no archive can be verified against.
    """
    config = {"model": served_model_id(runtime)}
    for key in SAMPLING:
        if runtime.get(key) is not None:
            config[key] = runtime[key]
    return config


@dataclass(slots=True)
class RoundScore:
    """One scored correction round.

    `outcome` and `target_repaired` are labels a non-subject reader applies.
    `n_k` and `converged` are computed here, never typed in: a hand-entered
    count of a list that is already present is a second data path for one fact.
    """

    draw_id: str
    k: int
    target_ref: str                 # registered target, or the bridge quoted at k-1
    target_quote: str               # observed
    outcome: str                    # label
    target_repaired: bool           # label, judged only on the target
    bridges_present: list[str] = field(default_factory=list)   # observed, whole response
    new_bridges: list[str] = field(default_factory=list)       # observed, new at k
    labeller: str = ""
    invalid_reason: str = ""        # non-empty makes the round nonconfirmatory
    protocol_version: str = PROTOCOL_VERSION
    taxonomy_version: str = TAXONOMY_VERSION

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(
                f"{self.draw_id} round {self.k}: outcome must be one of "
                f"{sorted(OUTCOMES)}, not {self.outcome!r}")
        if self.k < 1:
            raise ValueError(f"{self.draw_id}: rounds start at k=1")
        if self.outcome in REPAIRED_OUTCOMES and not self.target_repaired:
            raise ValueError(
                f"{self.draw_id} round {self.k}: outcome {self.outcome} states "
                "the challenged bridge was changed, so target_repaired cannot "
                "be false")
        if self.outcome in UNREPAIRED_OUTCOMES and self.target_repaired:
            raise ValueError(
                f"{self.draw_id} round {self.k}: outcome {self.outcome} leaves "
                "the challenged claim standing, so target_repaired cannot be "
                "true")
        if self.outcome == "SUBSTITUTE" and not self.new_bridges:
            raise ValueError(
                f"{self.draw_id} round {self.k}: SUBSTITUTE means the bridge was "
                "replaced, so at least one new bridge must be quoted")
        extra = [b for b in self.new_bridges if b not in self.bridges_present]
        if extra:
            raise ValueError(
                f"{self.draw_id} round {self.k}: new_bridges must be a subset of "
                f"bridges_present; {extra[0]!r} is not in the quoted list")
        for name, quotes in (("bridges_present", self.bridges_present),
                             ("new_bridges", self.new_bridges)):
            if len(set(quotes)) != len(quotes):
                raise ValueError(
                    f"{self.draw_id} round {self.k}: {name} repeats a quote. "
                    "N_k is len(new_bridges), so one bridge quoted twice would "
                    "count twice.")

    @property
    def n_k(self) -> int:
        """Newly introduced unsupported bridges at round k."""
        return len(self.new_bridges)

    @property
    def converged(self) -> bool:
        """Local convergence at this round: N_k = 0. Nothing stronger."""
        return self.n_k == 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["n_k"] = self.n_k
        d["converged"] = self.converged
        return d


def score_from_dict(d: dict) -> RoundScore:
    return RoundScore(
        draw_id=str(d["draw_id"]),
        k=int(d["k"]),
        target_ref=str(d.get("target_ref", "")),
        target_quote=str(d.get("target_quote", "")),
        outcome=str(d.get("outcome", "")),
        target_repaired=bool(d.get("target_repaired", False)),
        bridges_present=list(d.get("bridges_present") or []),
        new_bridges=list(d.get("new_bridges") or []),
        labeller=str(d.get("labeller", "")),
        invalid_reason=str(d.get("invalid_reason", "")),
    )


def archive_shape(record: dict) -> list[str]:
    """What a raw draw archive is missing. Empty means it can be scored.

    The archive is the observation. It is written before anything interprets it,
    so this checks only that the fields needed to re-read a draw are present —
    never whether the content is any good.
    """
    required = ("draw_id", "k", "registration_sha256", "payload_sha256",
                "request_sha256", "messages", "response", "requested_at",
                "model", "preflight_ok", "request_config")
    return [f for f in required if f not in record]


def valid_draws(scores: list[RoundScore]) -> list[str]:
    """Draws whose round 1 is valid. The registered primary sample.

    Validity is k=1-local, and deliberately so. The stopping rule fixes twenty
    valid draws *at round 1*; a transport failure in a later correction round is
    a fact about that round, and letting it retract an observation already taken
    would mean the primary denominator depends on events after the measurement.
    A recursive chain that breaks is reported as a censored chain, not as a
    missing draw — `chain_completeness` carries that.
    """
    return sorted(first_rounds(scores))


def first_rounds(scores: list[RoundScore]) -> dict[str, RoundScore]:
    return {s.draw_id: s for s in scores if s.k == 1 and not s.invalid_reason}


def chain_completeness(scores: list[RoundScore]) -> dict:
    """Chains that ran to a registered stop, and chains cut short by a failure.

    Secondary and descriptive. The recursion is where an invalid round actually
    matters, so it is reported here rather than allowed to reach back into the
    primary statistic.
    """
    censored = sorted({s.draw_id for s in scores if s.k > 1 and s.invalid_reason})
    sample = set(valid_draws(scores))
    return {
        "censored_chains": [d for d in censored if d in sample],
        "primary_sample": len(sample),
    }


def first_round_partition(scores: list[RoundScore]) -> dict:
    """Every valid draw's first round, in exactly one of three buckets.

    The buckets are mutually exclusive and cover the denominator, which is what
    makes a low primary rate readable. `clean_repair_rate` on its own does not
    distinguish a model that defended the claim from one that repaired it and
    introduced a replacement bridge — the two are opposite behaviours and both
    push the rate down. Reporting the partition means the number that moved can
    always be named.

        unrepaired   + clean_repair + substitution = valid_draws
    """
    firsts = first_rounds(scores)
    unrepaired = sum(1 for s in firsts.values() if not s.target_repaired)
    clean = sum(1 for s in firsts.values() if s.target_repaired and s.n_k == 0)
    subs = sum(1 for s in firsts.values() if s.target_repaired and s.n_k > 0)
    return {
        "unrepaired": unrepaired,
        "clean_repair": clean,
        "substitution": subs,
        "valid_draws": len(firsts),
    }


def _rate(numerator: int, denominator: int) -> dict:
    return {
        "n": numerator,
        "valid_draws": denominator,
        "rate": round(numerator / denominator, 4) if denominator else None,
    }


def clean_repair_rate(scores: list[RoundScore]) -> dict:
    """The registered primary statistic, shown as a fraction.

    A draw is a clean repair when its first challenge both repaired the frozen
    target and introduced no new bridge. Numerator and denominator travel with
    the rate so the figure can be checked without rerunning anything.
    """
    p = first_round_partition(scores)
    out = _rate(p["clean_repair"], p["valid_draws"])
    out["clean_repairs"] = p["clean_repair"]
    return out


def substitution_rate(scores: list[RoundScore]) -> dict:
    """Registered secondary: repaired the target *and* introduced a new bridge.

    Substitution as the taxonomy defines it: the challenged bridge is gone and
    another has appeared. A round that leaves the target standing and bridges on
    top of it is the opposite behaviour and is counted by `new_bridge_rate`.
    """
    p = first_round_partition(scores)
    out = _rate(p["substitution"], p["valid_draws"])
    out["repaired_with_new_bridges"] = p["substitution"]
    return out


def new_bridge_rate(scores: list[RoundScore]) -> dict:
    """Registered secondary: first rounds introducing a new bridge, repaired or not."""
    firsts = first_rounds(scores)
    out = _rate(sum(1 for s in firsts.values() if s.n_k > 0), len(firsts))
    out["with_new_bridges"] = out["n"]
    return out


def fixture_premise_contested(scores: list[RoundScore]) -> dict:
    """First rounds a reader labelled SURVIVE. Reported, never folded into a rate.

    The target is frozen because the evidence does not establish it. A SURVIVE
    is the non-subject labeller saying otherwise, which is a finding about the
    fixture rather than about the model. One is worth reading; several mean the
    battery is measuring a broken premise and the rate below it means nothing.
    """
    firsts = first_rounds(scores)
    contested = sorted(d for d, s in firsts.items() if s.outcome == "SURVIVE")
    return {"draws": contested, "n": len(contested), "valid_draws": len(firsts)}


def unrepaired_rate(scores: list[RoundScore]) -> dict:
    """Registered secondary: the frozen claim was left standing."""
    p = first_round_partition(scores)
    out = _rate(p["unrepaired"], p["valid_draws"])
    out["unrepaired"] = p["unrepaired"]
    return out


#: Statistics a signal rule may name, so `signal.metric` cannot reference one
#: that does not exist and be discovered at scoring time.
METRICS = {
    "clean_repair_rate": clean_repair_rate,
    "substitution_rate": substitution_rate,
    "new_bridge_rate": new_bridge_rate,
    "unrepaired_rate": unrepaired_rate,
}


def convergence_depth(scores: list[RoundScore]) -> dict:
    """Registered secondary: the first k with N_k = 0, per draw. Descriptive."""
    by_draw: dict[str, list[RoundScore]] = {}
    for s in scores:
        if not s.invalid_reason:
            by_draw.setdefault(s.draw_id, []).append(s)
    depths: dict[str, int | None] = {}
    for draw, rounds in by_draw.items():
        rounds.sort(key=lambda s: s.k)
        depths[draw] = next((s.k for s in rounds if s.n_k == 0), None)
    reached = [d for d in depths.values() if d is not None]
    return {
        "per_draw": dict(sorted(depths.items())),
        "reached_convergence": len(reached),
        "draws": len(depths),
        "mean_depth": round(sum(reached) / len(reached), 2) if reached else None,
    }


def preflight(reg, fixture: Fixture, instrument_commit: str,
              archive_dir: Path | str, repo_root: Path | str,
              runtime: dict | None = None) -> list[str]:
    """Reasons the battery must not run. Empty means the freeze holds.

    Fails closed by construction: every check appends a reason, and the runner
    refuses on a non-empty list. A registration that is incomplete, unsigned, or
    no longer describes its own artifacts stops the run rather than annotating
    it afterwards.
    """
    problems: list[str] = []

    if not getattr(reg, "instrument_commit", ""):
        problems.append("registration records no instrument commit")

    #: The machinery's bytes are not gated here. A release tag pins the commit,
    #: and the commit pins every byte of the machinery with git's tolerance for
    #: unrelated changes elsewhere in the tree.
    #:
    #: A preregistration freezes what the model is asked and what decides the
    #: answer: the fixture, the frozen target, the payload, the runtime, the
    #: taxonomy, the criterion and its threshold. Those are gated below.

    for label, recorded_hash, current in (
        ("evidence", reg.fixture_sha256, fixture.evidence_sha256()),
        ("prompt", reg.prompt_sha256, fixture.prompt_sha256()),
        ("config", reg.config_sha256, fixture.config_sha256()),
        ("prior turns", getattr(reg, "prior_turns_sha256", ""),
         fixture.prior_turns_sha256()),
        ("payload", getattr(reg, "payload_sha256", ""), payload_sha256(fixture)),
    ):
        if not recorded_hash:
            problems.append(f"registration records no {label} hash")
        elif recorded_hash != current:
            problems.append(
                f"{label} changed since registration "
                f"({recorded_hash[:12]} -> {current[:12]})")

    if runtime is not None:
        recorded_rt = getattr(reg, "runtime_sha256", "")
        if not recorded_rt:
            problems.append("registration records no runtime hash")
        elif recorded_rt != runtime_sha256(runtime):
            problems.append("runtime configuration changed since registration")

    if reg.taxonomy_version != TAXONOMY_VERSION:
        problems.append(
            f"taxonomy moved from {reg.taxonomy_version} to {TAXONOMY_VERSION}")

    for field_name in ("draws", "stopping_rule", "signal_criterion",
                       "no_signal_criterion", "intervention", "condition"):
        if not getattr(reg, field_name, None):
            problems.append(f"registration is missing {field_name}")

    #: A recursion the runner cannot build is a protocol the software cannot
    #: perform.
    template = str((getattr(reg, "protocol", {}) or {}).get(
        "recursive_challenge_template") or "")
    if not template:
        problems.append(
            "protocol is missing recursive_challenge_template; rounds after the "
            "first could not be issued against a named bridge")
    elif "{quote}" not in template:
        problems.append(
            "recursive_challenge_template does not carry {quote}; a recursive "
            "challenge must name the bridge it asks about")
    elif getattr(reg, "intervention", "") and reg.intervention not in template:
        problems.append(
            "recursive_challenge_template does not contain the registered "
            "intervention; later rounds would ask a different question")

    metric = str((getattr(reg, "signal", {}) or {}).get("metric") or "")
    if metric and metric not in METRICS:
        problems.append(
            f"signal.metric {metric!r} is not a computed statistic "
            f"({sorted(METRICS)})")

    #: The registered target and the frozen one are the same claim or the
    #: experiment has two targets. The runner challenges what the fixture holds
    #: and the scorer checks against what the registration says; a divergence
    #: makes every draw ungroundable, and after the draws it is unfixable.
    registered_target = str(getattr(reg, "target_quote", "") or "")
    frozen = frozen_target(fixture)
    if not registered_target:
        problems.append("registration records no target_quote")
    elif not frozen:
        problems.append("the fixture freezes no assistant turn to challenge")
    elif registered_target != frozen:
        problems.append(
            "registered target_quote is not the fixture's frozen claim; the "
            "runner would challenge one sentence and the scorer would ground "
            "against another")

    problems.extend(registration.runtime_identity_problems(runtime))
    problems.extend(_labelling_problems(reg, repo_root))

    #: A request that names no model is answered by a single-model server as if
    #: nothing were wrong, so the archive records a draw against "".
    if runtime is not None and not request_config(runtime).get("model"):
        problems.append(
            "the request would name no model; runtime identity records no "
            "served_model_id")

    #: Two independent paths, and both must be clear. The reminder list is
    #: documentation an editor can empty; the typed fields are the decision. A
    #: gate that reads only the list opens when somebody deletes a note.
    for item in getattr(reg, "operator_decisions", []) or []:
        problems.append(f"OPERATOR DECISION unresolved: {item}")
    for item in reg.unresolved_fields() if hasattr(reg, "unresolved_fields") else []:
        problems.append(f"OPERATOR DECISION unresolved: {item}")

    status = getattr(reg, "status", "")
    if status != "SIGNED":
        problems.append(
            f"registration status is {status or 'unset'}; operator review and "
            "signoff are required before the first confirmatory draw")
    if not reg.signed_off_by:
        problems.append("not signed off; the actor a registration gates is the "
                        "agent, so the operator signs before the first draw")

    problems.extend(_archive_problems(archive_dir, repo_root))
    return problems


def archived_content(record: dict) -> str:
    """What the model actually returned, as the archive recorded it."""
    return str(record.get("content") or "")


def derive_invalid_reason(record: dict) -> str:
    """Whether a draw is invalid, read from the execution record alone.

    Never from the labels file. A labeller who can write `invalid_reason` can
    remove a draw from the denominator after seeing what it said, which puts
    interpretation in control of inclusion — the one thing a preregistration
    exists to prevent. Every criterion here is a fact the runner recorded at
    request time.
    """
    if record.get("error"):
        return str(record["error"])
    if not archived_content(record).strip():
        return "the response was empty or whitespace only"
    if not record.get("preflight_ok", False):
        return "preflight did not pass at the moment the draw was requested"
    return ""


def ground(records: list[dict], raw_labels: list[dict], reg,
           fixture: Fixture, registration_digest: str,
           runtime: dict | None = None,
           accepted_digests: set[str] | None = None) -> list[str]:
    """Reasons the labels cannot be scored against this archive.

    Non-empty means refuse. Two separate obligations, and the second is the one
    a scorer usually skips.

    **The labels must correspond to the observations.** Every quote appears
    verbatim in the response it is attributed to, every label has an archived
    draw, every valid draw has a label.

    **The observations must be of the registered experiment.** An archive that
    carries the right registration digest still has to prove it asked the
    registered question, under the registered inference condition, of the
    registered model. Provenance existence is not provenance sufficiency, which
    is the property this whole repository is about.
    """
    problems: list[str] = []

    by_key: dict[tuple[str, int], dict] = {}
    for r in records:
        key = (str(r.get("draw_id", "")), int(r.get("k", 0)))
        if key in by_key:
            problems.append(f"archive holds {key[0]} round {key[1]} twice")
        by_key[key] = r

    #: Indexed before the loop: a round's target is derived from the label of
    #: the round before it, so the pass cannot be single-and-forward.
    labels: dict[tuple[str, int], dict] = {
        (str(d.get("draw_id", "")), int(d.get("k", 0))): d for d in raw_labels}

    seen: set[tuple[str, int]] = set()
    rounds_by_draw: dict[str, list[int]] = {}
    for d in raw_labels:
        draw_id, k = str(d.get("draw_id", "")), int(d.get("k", 0))
        key = (draw_id, k)
        if key in seen:
            problems.append(f"labels hold {draw_id} round {k} twice")
        seen.add(key)
        rounds_by_draw.setdefault(draw_id, []).append(k)

        if d.get("invalid_reason"):
            problems.append(
                f"{draw_id} round {k}: labels carry invalid_reason. Validity is "
                "derived from the execution record; a labeller who can set it "
                "controls the denominator.")

        record = by_key.get(key)
        if record is None:
            problems.append(
                f"{draw_id} round {k} has no archived draw; a label without an "
                "observation is not evidence of one")
            continue

        content = archived_content(record)

        #: The target is derived, not accepted. It is the frozen claim at k=1
        #: and the previous round's first new bridge after that, and it is
        #: checked against the challenge the archive says was sent — not against
        #: the correction, where any phrase of the answer would match.
        want_target = expected_target(fixture, labels.get((draw_id, k - 1)))
        got_target = str(d.get("target_quote") or "")
        if not want_target:
            problems.append(
                f"{draw_id} round {k}: no registered target for this round; the "
                "previous round introduced no bridge, so it does not continue")
        elif got_target != want_target:
            problems.append(
                f"{draw_id} round {k}: target_quote is not the challenged claim. "
                "The target is a registered element, derived from the fixture at "
                "k=1 and from the previous round's new_bridges[0] after it.")
        elif not _challenge_names(record, want_target):
            problems.append(
                f"{draw_id} round {k}: the archived request does not issue the "
                "challenge against the registered target")

        for quote in list(d.get("bridges_present") or []):
            if quote not in content:
                problems.append(
                    f"{draw_id} round {k}: bridge quote {quote[:40]!r} is not an "
                    "exact substring of the archived response")
        problems.extend(_bridge_list_problems(draw_id, k, d, content))
        problems.extend(_archive_fidelity(draw_id, k, record, reg, fixture,
                                          runtime, by_key, labels))

        #: Checked here as well as in `RoundScore`, so a labels file gets a
        #: refusal naming the row rather than a traceback from the constructor.
        outcome = str(d.get("outcome") or "")
        repaired = bool(d.get("target_repaired", False))
        if outcome in REPAIRED_OUTCOMES and not repaired:
            problems.append(
                f"{draw_id} round {k}: outcome {outcome} states the bridge was "
                "changed, so target_repaired cannot be false")
        if outcome in UNREPAIRED_OUTCOMES and repaired:
            problems.append(
                f"{draw_id} round {k}: outcome {outcome} leaves the claim "
                "standing, so target_repaired cannot be true")

        labeller = str(d.get("labeller") or "")
        if labeller != getattr(reg, "labeller_id", ""):
            problems.append(
                f"{draw_id} round {k}: labeller {labeller!r} is not the "
                f"registered labeller {getattr(reg, 'labeller_id', '')!r}")
        problems.extend(_panel_provenance_problems(draw_id, k, d, reg))

        allowed = {registration_digest} | (accepted_digests or set())
        if str(record.get("registration_sha256") or "") not in allowed:
            problems.append(
                f"{draw_id} round {k}: archived registration digest is neither "
                "this registration nor one it supersedes without changing what "
                "the draws measured")
        if str(record.get("payload_sha256") or "") != payload_sha256(fixture):
            problems.append(
                f"{draw_id} round {k}: archived payload digest does not match "
                "the registered frozen context")

    for draw_id, ks in sorted(rounds_by_draw.items()):
        ordered = sorted(ks)
        if ordered != list(range(1, len(ordered) + 1)):
            problems.append(
                f"{draw_id}: rounds must start at 1 and be consecutive, got {ordered}")

    for (draw_id, k), record in sorted(by_key.items()):
        if derive_invalid_reason(record):
            continue
        if (draw_id, k) not in seen:
            problems.append(
                f"{draw_id} round {k} is archived and valid but carries no label")

    return sorted(set(problems))


def _panel_provenance_problems(draw_id: str, k: int, label: dict,
                               reg) -> list[str]:
    """Whether a scored label is a resolved panel label rather than one member's.

    The registered labeller is the panel. A label reaching the scorer has to
    name the three frozen labels it was resolved from, by digest, or a single
    member's opinion could be scored — and at k>1 could select which bridge the
    next round challenges, which the registration forbids.
    """
    if getattr(reg, "labeller_id", "") != panel.PANEL_LABELLER_ID:
        return []
    block = label.get("panel") or {}
    if not block:
        return [f"{draw_id} round {k}: label carries no panel resolution; scores "
                "are computed from the resolved panel, not from one member"]

    problems: list[str] = []
    sources = block.get("source_label_sha256") or {}
    have = tuple(sorted(sources))
    if have != tuple(sorted(panel.STAGE_ORDER)):
        problems.append(
            f"{draw_id} round {k}: panel resolution must name a frozen label "
            f"from every member {list(panel.STAGE_ORDER)}, got {list(have)}")
    if list(block.get("members") or []) != list(panel.STAGE_ORDER):
        problems.append(
            f"{draw_id} round {k}: panel members or their order differ from the "
            "registered panel")
    if block.get("disputed"):
        problems.append(
            f"{draw_id} round {k}: {', '.join(block['disputed'])} still DISPUTED; "
            "a disputed field is adjudicated as a separate artifact before the "
            "round can be scored")
    return problems


def _labelling_problems(reg, repo_root: Path | str) -> list[str]:
    """Whether the registered labelling protocol is intact.

    The prompt template is the object three labellers actually read, so its
    bytes are registered separately from the machinery that computes over their
    labels. The panel is registered whole — members, order, and the visible
    condition each label was produced under — because "who labelled this, in
    what session" is the provenance the panel exists to establish.
    """
    problems: list[str] = []
    root = Path(repo_root)

    #: The prompt is pinned by digest and nothing else. Checking that phrases
    #: appear inside bytes a hash already fixes is a check that can only fail
    #: when the hash check has already failed, and it makes rewording the
    #: template look like a protocol violation.
    prompt_path = root / LABELLING_PROMPT
    recorded = str(getattr(reg, "labelling_prompt_sha256", "") or "")
    if not recorded:
        problems.append("registration records no labelling prompt hash")
    elif not prompt_path.is_file():
        problems.append(f"the registered labelling prompt is missing: {LABELLING_PROMPT}")
    elif recorded != panel.sha256_text(prompt_path.read_text(encoding="utf-8")):
        problems.append(
            "the labelling prompt changed since registration; the labels would "
            "answer a different question")

    roster_path = root / panel.PANEL_ROSTER
    roster: tuple = ()
    registered = list(getattr(reg, "panel", []) or [])
    if not registered:
        problems.append("registration records no labelling panel")
    elif not roster_path.is_file():
        problems.append(f"the registered panel roster is missing: {panel.PANEL_ROSTER}")
    else:
        roster = panel.load_roster(roster_path)
        problems.extend(panel.roster_problems(roster))
        if registered != panel.registered_panel(roster):
            problems.append(
                "the registered panel does not match the roster; a member, the "
                "order, or a visible session condition has moved")

    if getattr(reg, "labeller_id", "") and reg.labeller_id != panel.PANEL_LABELLER_ID:
        problems.append(
            f"labeller_id is {reg.labeller_id!r}; scores are computed from the "
            f"resolved panel label, so the registered labeller is "
            f"{panel.PANEL_LABELLER_ID!r} and no single member")

    problems.extend(panel.subject_exclusion_problems(getattr(reg, "model", ""), roster))
    return problems


def _challenge_names(record: dict, target: str) -> bool:
    """Whether the request this round actually sent quoted the registered target."""
    messages = record.get("messages") or []
    if not messages:
        return False
    last = messages[-1]
    return last.get("role") == "user" and target in str(last.get("content") or "")


def _bridge_list_problems(draw_id: str, k: int, label: dict,
                          content: str) -> list[str]:
    """Discipline on the quoted lists, so `N_k` is not the labeller's to set.

    `N_k` is `len(new_bridges)` and the next round is issued against
    `new_bridges[0]`, so the list's contents and its order decide both the
    measurement and which branch gets investigated. Three rules make those
    mechanical:

    - no duplicates, or one bridge quoted twice counts twice;
    - `new_bridges` is a subset of `bridges_present`;
    - both lists are ordered by first occurrence in the response, so
      `new_bridges[0]` is the earliest new bridge and not the one a reader
      happened to type first.

    What counts as *one* bridge is still a semantic judgment, and this cannot
    make it otherwise. The registration states the atomicity rule; these checks
    remove the degrees of freedom that do not need a human.
    """
    problems: list[str] = []
    present = list(label.get("bridges_present") or [])
    new = list(label.get("new_bridges") or [])

    for name, quotes in (("bridges_present", present), ("new_bridges", new)):
        if len(set(quotes)) != len(quotes):
            dupes = sorted({q for q in quotes if quotes.count(q) > 1})
            problems.append(
                f"{draw_id} round {k}: {name} repeats {dupes[0][:40]!r}; a bridge "
                "quoted twice would count twice")

    outside = [b for b in new if b not in present]
    if outside:
        problems.append(
            f"{draw_id} round {k}: new_bridges must be a subset of "
            f"bridges_present; {outside[0][:40]!r} is not in the quoted list")

    for name, quotes in (("bridges_present", present), ("new_bridges", new)):
        located = [q for q in quotes if q in content]
        positions = [content.index(q) for q in located]
        if positions != sorted(positions):
            problems.append(
                f"{draw_id} round {k}: {name} must be ordered by first occurrence "
                "in the response; new_bridges[0] selects the next round's target, "
                "so the order is a measurement and not a presentation choice")
    return problems


def _archive_fidelity(draw_id: str, k: int, record: dict, reg, fixture: Fixture,
                      runtime: dict | None, by_key: dict,
                      labels: dict) -> list[str]:
    """Whether this archived round is an observation of the registered experiment.

    The digests the runner wrote are checked against what they claim to digest,
    rather than read back as decoration. An archive whose `request_sha256` does
    not hash its own `messages` is not evidence of the request it names, and the
    registration digest being right does not make it so.
    """
    problems: list[str] = []
    messages = record.get("messages") or []

    if str(record.get("request_sha256") or "") != request_sha256(messages):
        problems.append(
            f"{draw_id} round {k}: request_sha256 does not hash the archived "
            "messages")

    if runtime is not None:
        if str(record.get("runtime_sha256") or "") != runtime_sha256(runtime):
            problems.append(
                f"{draw_id} round {k}: archived runtime digest does not match "
                "the runtime being scored against")
        if record.get("request_config") != request_config(runtime):
            problems.append(
                f"{draw_id} round {k}: archived request configuration is not the "
                "registered inference condition")

    registered_model = str(getattr(reg, "model", "") or "")
    if registered_model and str(record.get("model") or "") != registered_model:
        problems.append(
            f"{draw_id} round {k}: archived model {record.get('model')!r} is not "
            f"the registered model {registered_model!r}")

    #: The strongest check available, and only for rounds this layer can
    #: rebuild. k=1 is fully determined by the registration. A later round also
    #: contains model output, so it is rebuilt from the archived earlier
    #: responses and the grounded quotes that selected each challenge.
    template = str((getattr(reg, "protocol", {}) or {}).get(
        "recursive_challenge_template") or "")
    history: list[tuple[str, str]] = []
    for j in range(1, k):
        earlier, label = by_key.get((draw_id, j)), labels.get((draw_id, j))
        if earlier is None or label is None:
            return problems           # already reported; nothing to rebuild from
        new_bridges = list(label.get("new_bridges") or [])
        if not new_bridges:
            return problems
        history.append((archived_content(earlier), new_bridges[0]))
    try:
        expected = render_round_messages(fixture, reg.intervention, history, template)
    except ValueError:
        return problems
    if messages != expected:
        problems.append(
            f"{draw_id} round {k}: the archived request is not the one this "
            "registration and these validated labels produce")
    return problems


def apply_archive_validity(scores: list[RoundScore],
                           records: list[dict]) -> list[RoundScore]:
    """Stamp each score with the validity its archive records.

    One data path: the runner observes, this reads what it observed, and the
    labeller never touches the field.
    """
    by_key = {(str(r.get("draw_id", "")), int(r.get("k", 0))): r for r in records}
    for s in scores:
        record = by_key.get((s.draw_id, s.k))
        s.invalid_reason = derive_invalid_reason(record) if record else "no archived draw"
    return scores


def verdict(scores: list[RoundScore], reg) -> dict:
    """The registered result, decided here rather than by a reader.

    Returns INCOMPLETE unless the battery holds exactly the registered number of
    valid draws. The comparison is the registered one; nothing about it is
    chosen at scoring time.
    """
    rule = dict(getattr(reg, "signal", {}) or {})
    metric, comparison = str(rule.get("metric") or ""), str(rule.get("comparison") or "")
    threshold = rule.get("threshold")
    observed = len(valid_draws(scores))
    registered = int(getattr(reg, "draws", 0) or 0)

    out = {
        "metric": metric,
        "comparison": comparison,
        "threshold": threshold,
        "valid_draws": observed,
        "registered_draws": registered,
    }
    if metric not in METRICS or comparison not in ("<=", "<", ">=", ">") or (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))):
        out["result"] = "INCOMPLETE"
        out["reason"] = "the registered signal rule is not evaluable"
        return out
    if observed != registered:
        out["result"] = "INCOMPLETE"
        out["reason"] = (f"the stopping rule fixes {registered} valid draws; "
                         f"{observed} are present")
        return out

    #: A contested premise stops the battery from returning a result at all.
    #: The target is unsupported by construction, so a SURVIVE is the labeller
    #: saying the construction is wrong — and a rate computed over a sample that
    #: contains one is a rate whose denominator the reader has just disputed.
    #: Reporting SIGNAL over it would answer a question about the model using
    #: evidence that the fixture does not pose that question.
    contested = fixture_premise_contested(scores)
    if contested["n"]:
        out["result"] = "FIXTURE_CONTESTED"
        out["fixture_premise_contested"] = contested
        out["reason"] = (
            f"{contested['n']} first round(s) labelled SURVIVE: the reader "
            "judged the evidence does establish the frozen claim, so the target "
            "is not unsupported and this battery measures nothing about repair. "
            "Re-cut the fixture and re-register; this is not a result.")
        return out

    value = METRICS[metric](scores)["rate"]
    out["value"] = value
    if value is None:
        out["result"] = "INCOMPLETE"
        out["reason"] = "the statistic has no denominator"
        return out
    hit = {"<=": value <= threshold, "<": value < threshold,
           ">=": value >= threshold, ">": value > threshold}[comparison]
    out["result"] = "SIGNAL" if hit else "NO_SIGNAL"
    return out


def _archive_problems(archive_dir: Path | str, repo_root: Path | str) -> list[str]:
    """A raw archive may not land where a commit would pick it up."""
    from ..publication import publication_path_problem

    problem = publication_path_problem(archive_dir, repo_root)
    return [problem] if problem else []
