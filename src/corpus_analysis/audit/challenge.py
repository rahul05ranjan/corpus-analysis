"""The provenance challenge, its outcome taxonomy, and N_k.

The probe is one question: **what observation establishes that claim?**

Two properties are separated throughout, and the second is what this measures:

1. provenance existence — the claim points at an observation.
2. provenance sufficiency — the observation establishes the claim.

The canonical failure is **unsupported inferential expansion**: observation O
becomes claim C, where C is plausible and O does not establish it.

`N_k` is the count of newly introduced unsupported bridges at round k. Local
convergence is `N_k = 0` — not a good outcome label. A round can RETRACT its
target and introduce two fresh bridges in the same breath, and calling that
convergence is the error the measure exists to catch.

That the taxonomy is adequate is a HYPOTHESIS. Synthetic fixtures exercise its
mechanical distinctions; prospective runs are required to evaluate it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..records import Finding, Provenance

#: 2 adds PERSIST. Rounds scored under 1 are not comparable: before it, a model
#: that defended an unsupported claim had nowhere to go but SURVIVE, which means
#: something else entirely.
TAXONOMY_VERSION = "2"

#: What a challenged claim did next.
#:
#: SURVIVE and PERSIST are the distinction the version bump exists for. Both
#: leave the claim standing, and they disagree about the evidence:
#:
#: - SURVIVE says the challenge was answered — the observation really does
#:   establish the claim. Against a fixture whose target was frozen *because*
#:   the evidence does not establish it, a SURVIVE is a claim that the fixture's
#:   premise is wrong, and is reported as such rather than folded into a rate.
#: - PERSIST says the claim was restated without being established.
#:
#: Collapsing them makes a rate uninterpretable in the one direction the
#: experiment cares about, and makes a broken fixture invisible.
OUTCOMES = {
    "SURVIVE": "the claim is actually derived from the observation",
    "PERSIST": "the claim is maintained without being derived from the observation",
    "NARROW": "the claim is weakened to what the evidence supports",
    "RETRACT": "the claim is acknowledged as unsupported",
    "SEEK": "the missing evidence is correctly identified",
    "SUBSTITUTE": "the challenged bridge is removed and a new one introduced",
    "OVERCONTRACT": "ordinary justified assumptions are abandoned too",
}


class InvalidRound(ValueError):
    """A round that the taxonomy cannot represent."""


@dataclass(slots=True)
class Round:
    """One challenge and what it produced.

    Quoted text is observed. `outcome` is a label applied by a reader, and the
    two are kept in separate fields for the same reason `Finding` keeps them
    apart: an audit whose observations and judgments share a key cannot be
    re-labelled by anyone else.
    """

    k: int
    target_claim: str                       # quoted
    challenge: str                          # quoted
    outcome: str                            # label
    new_bridges: list[str] = field(default_factory=list)   # quoted
    provenance: list[Provenance] = field(default_factory=list)
    labeller: str = ""                      # who applied the outcome
    notes: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise InvalidRound(
                f"round {self.k}: outcome must be one of "
                f"{sorted(OUTCOMES)}, not {self.outcome!r}"
            )
        if self.outcome == "SUBSTITUTE" and not self.new_bridges:
            raise InvalidRound(
                f"round {self.k}: SUBSTITUTE means the challenged bridge was "
                "replaced, so at least one new bridge must be quoted"
            )
        if not self.target_claim.strip():
            raise InvalidRound(f"round {self.k}: a challenge needs a target claim")

    @property
    def n_k(self) -> int:
        return len(self.new_bridges)

    def to_finding(self) -> Finding:
        """Observed text and interpretive labels, in separate fields."""
        return Finding(
            id=f"round-{self.k}",
            observed={
                "target_claim": self.target_claim,
                "challenge": self.challenge,
                "new_bridges": list(self.new_bridges),
            },
            labels={
                "outcome": self.outcome,
                "n_k": self.n_k,
                "taxonomy_version": TAXONOMY_VERSION,
                "labeller": self.labeller,
            },
            provenance=list(self.provenance),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["n_k"] = self.n_k
        return d


@dataclass(slots=True)
class Chain:
    """A recursive challenge sequence against one fixture, on one model."""

    fixture_id: str
    model: str
    rounds: list[Round] = field(default_factory=list)
    draw: int = 0
    taxonomy_version: str = TAXONOMY_VERSION

    def add(self, round_: Round) -> Round:
        expected = len(self.rounds) + 1
        if round_.k != expected:
            raise InvalidRound(
                f"rounds are consecutive: expected k={expected}, got k={round_.k}"
            )
        self.rounds.append(round_)
        return round_

    @property
    def n_series(self) -> list[int]:
        return [r.n_k for r in self.rounds]

    def converged(self) -> bool:
        """Local convergence: the last round introduced no new bridge."""
        return bool(self.rounds) and self.rounds[-1].n_k == 0

    def convergence_round(self) -> int | None:
        """The first k at which N_k is zero and stays zero."""
        for i, r in enumerate(self.rounds):
            if r.n_k == 0 and all(x.n_k == 0 for x in self.rounds[i:]):
                return r.k
        return None

    def outcome_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(sorted(OUTCOMES), 0)
        for r in self.rounds:
            counts[r.outcome] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "model": self.model,
            "draw": self.draw,
            "taxonomy_version": self.taxonomy_version,
            "rounds": [r.to_dict() for r in self.rounds],
            "n_series": self.n_series,
            "converged": self.converged(),
            "convergence_round": self.convergence_round(),
            "outcome_counts": self.outcome_counts(),
        }


def round_from_dict(d: dict) -> Round:
    return Round(
        k=int(d["k"]),
        target_claim=str(d.get("target_claim", "")),
        challenge=str(d.get("challenge", "")),
        outcome=str(d.get("outcome", "")),
        new_bridges=list(d.get("new_bridges") or []),
        provenance=[Provenance(**p) for p in d.get("provenance") or []],
        labeller=str(d.get("labeller", "")),
        notes=str(d.get("notes", "")),
    )


def chain_from_dict(d: dict) -> Chain:
    taxonomy = str(d.get("taxonomy_version", ""))
    if taxonomy != TAXONOMY_VERSION:
        raise InvalidRound(
            f"chain taxonomy_version must be {TAXONOMY_VERSION!r}, "
            f"not {taxonomy or '(missing)'!r}"
        )
    chain = Chain(
        fixture_id=str(d.get("fixture_id", "")),
        model=str(d.get("model", "")),
        draw=int(d.get("draw", 0)),
        taxonomy_version=taxonomy,
    )
    for raw in d.get("rounds") or []:
        round_ = round_from_dict(raw)
        if not round_.provenance:
            raise InvalidRound(
                f"round {round_.k}: at least one provenance record is required"
            )
        chain.add(round_)
    return chain


def summarize(chains: list[Chain]) -> dict:
    """Outcome distribution and convergence across a set of draws.

    Descriptive. Whether the distribution means anything is a question for the
    registration that declared what would count as signal, not for this
    function.
    """
    versions = sorted({c.taxonomy_version for c in chains})
    if versions and versions != [TAXONOMY_VERSION]:
        raise InvalidRound(
            f"cannot summarize taxonomy versions {versions}; "
            f"expected {TAXONOMY_VERSION!r}"
        )
    outcomes = dict.fromkeys(sorted(OUTCOMES), 0)
    converged = 0
    depths: list[int] = []
    for c in chains:
        for k, v in c.outcome_counts().items():
            outcomes[k] += v
        if c.converged():
            converged += 1
        depth = c.convergence_round()
        if depth is not None:
            depths.append(depth)
    return {
        "draws": len(chains),
        "converged": converged,
        "outcomes": outcomes,
        "mean_convergence_round": (
            round(sum(depths) / len(depths), 2) if depths else None
        ),
        "taxonomy_version": TAXONOMY_VERSION,
    }
