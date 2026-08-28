"""Preregistration. What a confirmatory run declared before it ran.

Patterns mined from a corpus are hypotheses. A registration is what converts
one into a test: it fixes the fixture, the prompt, the intervention, the
outcome taxonomy, the draw count, the stopping rule, and what would count as
signal — before the first draw.

**A draw taken after any registered element changed is not confirmatory.**
`validate()` compares the fixture hashes and signature fields. The runner also
records the committed registration file's digest with each draw; that external
digest, not `validate()` alone, establishes that decision fields did not move.

The criterion is populated before signature and remains unapproved while the
registration is a draft.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .challenge import TAXONOMY_VERSION
from .fixtures import Fixture

#: Fields that must be non-empty for a registration to gate anything.
REQUIRED = (
    "fixture_id", "fixture_sha256", "prompt_sha256", "config_sha256",
    "intervention", "condition", "draws", "stopping_rule", "signal_criterion",
)

#: A registration's lifecycle. Only `SIGNED` permits a confirmatory draw, and
#: only the operator sets it: the actor under pressure to finish is the one
#: running the draws, which is the whole reason the gate exists.
STATUSES = ("DRAFT", "SIGNED", "SUPERSEDED")

#: Comparisons a signal rule may use. A criterion whose operator is prose is a
#: criterion a reader applies, which is the discretion the registration removes.
COMPARISONS = ("<=", "<", ">=", ">")

#: How the draws are seeded. `omitted` is a positive declaration that the
#: sample is stochastic, not the absence of a decision.
SEED_POLICIES = ("omitted", "fixed", "schedule")

#: Runtime identity a draw is only reproducible against. Every one must carry a
#: value: a runtime digest computed over a dict whose identity fields are empty
#: pins the emptiness and reads as more frozen than it is.
RUNTIME_IDENTITY = (
    "served_model_id", "inference_server", "inference_server_version",
    "max_model_len", "config_sha256", "tokenizer_sha256",
    "tokenizer_config_sha256", "chat_template_sha256", "weights_index_sha256",
)


@dataclass(slots=True)
class Registration:
    fixture_id: str
    fixture_sha256: str          # digest over the fixture's evidence spans
    prompt_sha256: str
    config_sha256: str

    intervention: str            # the challenge wording, verbatim
    condition: str               # when the challenge is issued
    draws: int
    stopping_rule: str
    signal_criterion: str        # what result counts as signal, and what does not

    taxonomy_version: str = TAXONOMY_VERSION
    n_k_definition: str = (
        "newly introduced unsupported bridges at round k; "
        "local convergence is N_k = 0"
    )
    model: str = ""

    #: Lineage, recorded and not enforced. A release tag pins the commit, and
    #: the commit pins the machinery; hashing the same files again here would
    #: gate ordinary maintenance without adding a guarantee.
    instrument_commit: str = ""
    instrument_sha256: dict = field(default_factory=dict)   # repo-relative path -> digest

    #: Digest over the exact message list a draw sends, and over the inference
    #: configuration it sends under. The prompt hash alone does not pin either.
    payload_sha256: str = ""
    runtime_sha256: str = ""

    #: Digest over turns frozen ahead of the draw. When the experiment measures
    #: what a model does to a claim, this pins the claim.
    prior_turns_sha256: str = ""

    #: The claim every first-round challenge is issued against, verbatim.
    #:
    #: A registered element, not a label. Which sentence was challenged cannot
    #: be something a reader decides after seeing the answer — and a target
    #: supplied by a labeller and checked against the *correction* lets any
    #: phrase of the response stand in for the claim actually challenged, while
    #: the real one fails to match at all.
    target_quote: str = ""

    #: The exact inference condition, as `battery.request_config` builds it from
    #: the runtime. Registered so the scorer can check an archive against it
    #: rather than trusting the digest beside it.
    request_config: dict = field(default_factory=dict)

    #: The complement of `signal_criterion`, written out rather than implied.
    #: "Not signal" and "no signal" are the same only when both are stated.
    no_signal_criterion: str = ""

    #: Everything else the run must not decide while it is running: the
    #: recursion and termination rules, what counts as a bridge, how target
    #: repair is separated from the explanatory tail, invalid-draw criteria,
    #: failure handling, and the treatment of unregistered observations.
    protocol: dict = field(default_factory=dict)

    #: Elements the source documents do not determine. Non-empty means the
    #: registration cannot gate a confirmatory draw, and preflight says so.
    #:
    #: This list is the operator's worklist, not the gate. Emptying it resolves
    #: nothing on its own — preflight checks the typed fields below, so a
    #: decision is resolved when its value is set, never when its reminder is
    #: deleted.
    operator_decisions: list = field(default_factory=list)

    #: The resolved decisions, in fields a check can read.
    #:
    #: `signal` carries the whole rule: which statistic, which comparison, and
    #: the threshold. Written out this way the scorer returns SIGNAL or
    #: NO_SIGNAL itself, and no reader gets to apply the comparison by eye.
    signal: dict = field(default_factory=dict)   # {metric, comparison, threshold}

    #: Maximum correction round. The chain stops at N_k = 0 or here, whichever
    #: comes first, so an unbounded chain cannot be entered by accident.
    recursion_cap: int | None = None

    #: Who applies the labels. Obligation 5 requires a non-subject reader, so
    #: preflight refuses a labeller that names the model under measurement.
    labeller_id: str = ""

    #: What counts as one unsupported bridge, written before the labeller sees a
    #: draw. `N_k` is `len(new_bridges)`, so a rule invented while reading the
    #: responses is a measurement tuned to them.
    bridge_atomicity: str = ""

    #: Digest over the exact bytes of the labelling prompt every panel member
    #: reads. Registered apart from the instrument files: the template changes
    #: what the labels mean, not how they are computed.
    labelling_prompt_sha256: str = ""

    #: The labelling panel, in the registered stage order, with the visible
    #: session condition each member's label was produced under.
    panel: list = field(default_factory=list)

    #: Whether the draws are seeded. Twenty draws at one seed are one
    #: observation repeated; twenty unseeded draws are a sample. Either is
    #: defensible and the choice has to be recorded, so "not stated" is not an
    #: option preflight accepts.
    seed_policy: str = ""

    #: A registration this one replaces, and the digest its draws carry.
    #:
    #: A superseding registration is not an amendment. It is only honest when
    #: every element that *determined* the earlier draws is unchanged, which
    #: `determining_differences` checks rather than asserts. Used for exactly
    #: one thing: correcting a registered element that could not have affected a
    #: draw, without orphaning draws already taken.
    supersedes: dict = field(default_factory=dict)   # {version, sha256, path, reason}

    registration_version: int = 1

    status: str = "DRAFT"
    #: When the operator signed. Set with the signature, never before.
    signed_at: str = ""

    #: When the operator withdrew it. A withdrawn registration keeps its tag,
    #: its digests and its published release; what it loses is the ability to
    #: gate a draw. Recorded rather than deleted, because a preregistration that
    #: disappears is the pattern preregistration exists to prevent.
    withdrawn_at: str = ""
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signed_off_by: str = ""      # set by the operator, before any draw
    notes: str = ""

    def missing(self) -> list[str]:
        return [f for f in REQUIRED if not getattr(self, f)]

    def unresolved(self) -> list:
        return list(self.operator_decisions)

    def unresolved_fields(self) -> list[str]:
        """Operator decisions whose value is still absent or unusable.

        Checked independently of `operator_decisions`. The reminder list and the
        values are two data paths for one fact, and only one of them can be the
        gate; clearing a reminder is an edit anyone can make, while setting a
        threshold is the decision the signature is for.
        """
        problems: list[str] = []

        metric = str(self.signal.get("metric") or "")
        comparison = str(self.signal.get("comparison") or "")
        threshold = self.signal.get("threshold")
        if not metric:
            problems.append("signal.metric is unset")
        if comparison not in COMPARISONS:
            problems.append(
                f"signal.comparison must be one of {list(COMPARISONS)}, "
                f"not {comparison!r}")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            problems.append(
                "signal.threshold is unset; the criterion is not evaluable "
                "until the operator sets a number")
        elif not 0.0 <= float(threshold) <= 1.0:
            problems.append(
                f"signal.threshold must be a rate in [0, 1], not {threshold}")

        if isinstance(self.recursion_cap, bool) or not isinstance(
                self.recursion_cap, int):
            problems.append("recursion_cap is unset")
        elif self.recursion_cap < 1:
            problems.append(
                f"recursion_cap must be at least 1, not {self.recursion_cap}")

        if not self.labeller_id:
            problems.append("labeller_id is unset")
        elif self.model and self.labeller_id.strip().lower() in (
                self.model.strip().lower(), self.model.strip().lower().replace("-", "")):
            problems.append(
                f"labeller_id {self.labeller_id!r} names the model under "
                "measurement; labelling must be done by a non-subject reader")

        if not self.bridge_atomicity.strip():
            problems.append(
                "bridge_atomicity is unset; N_k is len(new_bridges), so what "
                "counts as one bridge has to be written before the labeller "
                "reads a draw")
        if self.seed_policy not in SEED_POLICIES:
            problems.append(
                f"seed_policy must be one of {list(SEED_POLICIES)}, not "
                f"{self.seed_policy!r}")
        return problems


    def to_dict(self) -> dict:
        return asdict(self)

    def write(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=1, sort_keys=True, default=str) + "\n",
            encoding="utf-8")
        return path


#: Everything that decides what a draw measured or what its answer means. Two
#: registrations agreeing on all of these describe the same experiment, so draws
#: taken under one are comparable with draws taken under the other.
#:
#: `instrument_sha256` is absent. Machinery bytes are pinned by the release tag
#: and are not themselves a property of the measurement.
DETERMINING = (
    "fixture_id", "fixture_sha256", "prompt_sha256", "config_sha256",
    "prior_turns_sha256", "payload_sha256", "runtime_sha256", "target_quote",
    "intervention", "condition", "draws", "stopping_rule", "signal",
    "signal_criterion", "no_signal_criterion", "taxonomy_version",
    "bridge_atomicity", "labelling_prompt_sha256", "labeller_id", "panel",
    "recursion_cap", "seed_policy", "model",
)


def determining_differences(older, newer) -> list[str]:
    """Registered elements that differ and would make draws non-comparable.

    Empty means the later registration asks the same question of the same bytes
    under the same condition, and decides the answer the same way. Non-empty
    means the draws taken under the earlier one are not evidence about the
    later one, whatever the digests say.
    """
    out = []
    for name in DETERMINING:
        a, b = getattr(older, name, None), getattr(newer, name, None)
        if a != b:
            out.append(name)
    return out


def runtime_identity_problems(runtime: dict | None) -> list[str]:
    """Runtime identity fields that carry no value.

    Separate from `Registration.unresolved_fields` because the values live in
    the runtime file rather than the registration, and the registration only
    pins that file's digest. A digest over unpinned identity is a digest over
    the word "unknown", and reads as more frozen than it is.
    """
    if runtime is None:
        return []
    identity = dict(runtime.get("identity") or {})
    missing = [k for k in RUNTIME_IDENTITY if identity.get(k) in (None, "", 0)]
    return [f"runtime identity is unpinned: {k}" for k in sorted(missing)]


def load(path: Path | str) -> Registration:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Registration(**raw)


def register(fixture: Fixture, intervention: str, condition: str, draws: int,
             stopping_rule: str, signal_criterion: str, model: str = "",
             notes: str = "") -> Registration:
    """Pin a fixture's current state as the subject of a confirmatory run."""
    if isinstance(draws, bool) or draws < 1:
        raise ValueError(f"draws must be a positive integer, not {draws!r}")
    return Registration(
        fixture_id=fixture.id,
        fixture_sha256=fixture.evidence_sha256(),
        prompt_sha256=fixture.prompt_sha256(),
        config_sha256=fixture.config_sha256(),
        intervention=intervention,
        condition=condition,
        draws=draws,
        stopping_rule=stopping_rule,
        signal_criterion=signal_criterion,
        model=model,
        notes=notes,
    )


def validate(reg: Registration, fixture: Fixture) -> list[str]:
    """Reasons a draw against this fixture would not be confirmatory."""
    problems: list[str] = []
    missing = reg.missing()
    if missing:
        problems.append(f"registration is incomplete: {', '.join(missing)}")
    if isinstance(reg.draws, bool) or not isinstance(reg.draws, int) or reg.draws < 1:
        problems.append(f"draws must be a positive integer, not {reg.draws!r}")
    if reg.status not in STATUSES:
        problems.append(
            f"status must be one of {list(STATUSES)}, not {reg.status!r}")
    elif reg.status != "SIGNED":
        problems.append(
            f"status is {reg.status}; only SIGNED registrations are confirmatory")
    elif not reg.signed_at:
        problems.append("status is SIGNED but signed_at is unset")
    if not reg.signed_off_by:
        problems.append("not signed off; a registration gates the agent, "
                        "so the operator signs it before the first draw")
    unresolved = reg.unresolved()
    if unresolved:
        problems.append(
            f"operator decisions remain unresolved: {len(unresolved)}")
    problems.extend(reg.unresolved_fields())
    if reg.fixture_id != fixture.id:
        problems.append(
            f"registration names fixture {reg.fixture_id!r}, "
            f"given {fixture.id!r}")
    for label, recorded, current in (
        ("evidence", reg.fixture_sha256, fixture.evidence_sha256()),
        ("prompt", reg.prompt_sha256, fixture.prompt_sha256()),
        ("config", reg.config_sha256, fixture.config_sha256()),
    ):
        if recorded != current:
            problems.append(
                f"{label} changed since registration "
                f"({recorded[:12]} -> {current[:12]}); draws are exploratory")
    if reg.taxonomy_version != TAXONOMY_VERSION:
        problems.append(
            f"taxonomy moved from {reg.taxonomy_version} to {TAXONOMY_VERSION}")
    return problems


def is_confirmatory(reg: Registration, fixture: Fixture) -> bool:
    return not validate(reg, fixture)
