"""The labelling panel: one human investigator plus two model labellers.

Semantic labelling is the part of M3a no automated judge is permitted to do, so
the question is not how to remove the judgment but how to make the judgment
auditable. Three labellers produce a structured label each, from the same
rendered packet, in a fixed order, each frozen before the next begins. Panel
resolution is mechanical over those three.

**What the ordering establishes, and what it does not.** The panel is one human
and two models. It is not three human raters, and the two model labellers are
not independent in any statistical or population sense — two sessions of two
commercial products say nothing about a population of judges. What the protocol
establishes is narrower and checkable: each labeller's label-production session
was isolated from the others', because each was frozen and hashed before the
next was launched. That is a claim about provenance, not about statistics.

**Stages, not rounds.** M3a already uses `k` for recursive challenge rounds.
The three labelling operations are stages, and a stage index is never a `k`.

Pure, like the rest of `audit/`. Rendering a packet, validating a label and
resolving a panel need no clock, no network and no filesystem; the capture shell
that copies operator-supplied evidence lives outside the package.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from ..records import dumps
from .challenge import OUTCOMES, TAXONOMY_VERSION

#: Bumped when a member, the ordering, or the resolution rule changes. A panel
#: result produced under one version is not comparable to another.
PANEL_VERSION = "1"

#: How a field is settled when the three labels disagree.
CONSENSUS_RULE = "2-of-3"

#: What a field carries when 2-of-3 cannot settle it. Never dropped, never
#: quietly filled from one labeller.
DISPUTED = "DISPUTED"


@dataclass(frozen=True, slots=True)
class Member:
    """One panel member and the condition its label was produced under.

    Everything recorded here is what the operator could see on screen. No
    backend identifier, no API version, no hidden provider state: a screenshot
    establishes what a UI displayed and nothing behind it, and inventing a
    field that looks like a backend id would be the overreach this experiment
    exists to measure.
    """

    labeller_id: str
    labeller_type: str              # human | model
    provider: str = ""
    model_displayed: str = ""
    reasoning_displayed: str = ""
    session_mode: str = ""
    launch_url: str = ""
    requires_transcript: bool = False
    requires_screenshot: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


#: The roster — who the members are and the visible condition each labels
#: under — lives with the experiment, not in the package.
#:
#: The roster is registered data rather than mechanism, so it belongs beside
#: the fixture.
PANEL_ROSTER = "experiments/m3a/labelling/panel.json"

#: The stage order. Index 0 is frozen before index 1 is launched, and so on.
#: The investigator is first by preregistration: the human label is frozen
#: before either model is launched, so no model output can shape it.
STAGE_ORDER: tuple[str, ...] = ("investigator", "gpt56sol-high", "fable5-high")

#: Which stages must produce session evidence. The investigator reads a packet
#: — there is no session to screenshot.
EVIDENCE_REQUIRED: frozenset[str] = frozenset({"gpt56sol-high", "fable5-high"})


def load_roster(path) -> tuple[Member, ...]:
    """The registered panel roster, read from the experiment."""
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(Member(**m) for m in raw.get("members", []))


def roster_problems(roster: tuple[Member, ...]) -> list[str]:
    """Reasons a roster is not the registered panel."""
    problems: list[str] = []
    ids = tuple(m.labeller_id for m in roster)
    if ids != STAGE_ORDER:
        return [f"panel roster is {list(ids)}, registered order is {list(STAGE_ORDER)}"]
    for member in roster:
        wants = member.labeller_id in EVIDENCE_REQUIRED
        if member.requires_transcript != wants or member.requires_screenshot != wants:
            problems.append(
                f"{member.labeller_id} evidence requirements do not match the "
                "registered protocol")
        if wants and not (member.launch_url and member.session_mode
                          and member.model_displayed and member.reasoning_displayed):
            problems.append(
                f"{member.labeller_id} records no complete visible condition")
    return problems

#: The registered labeller of record. Individual members produce inputs; the
#: panel produces the label a score is computed from, which is why no single
#: member can select a recursive target.
PANEL_LABELLER_ID = "panel"

#: Placeholders the registered template carries. The packet is the template with
#: exactly these substituted — nothing appended, nothing per-labeller.
PLACEHOLDERS = ("<TARGET>", "<EVIDENCE>", "<RESPONSE>")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_packet(template: str, target: str, evidence: str, response: str) -> str:
    """The exact bytes every labeller reads for one draw and round.

    One packet, three labellers. A per-labeller variant would make the three
    labels answers to three different questions, and the disagreement between
    them would be a fact about the prompts.

    Raises on a missing placeholder. A template without `<RESPONSE>` produces a
    packet asking three labellers to label nothing, and the failure would
    surface as unanimous confusion rather than as a broken render.
    """
    missing = [p for p in PLACEHOLDERS if p not in template]
    if missing:
        raise ValueError(
            f"the labelling template is missing {', '.join(missing)}")
    for placeholder, value in (("<TARGET>", target), ("<EVIDENCE>", evidence),
                               ("<RESPONSE>", response)):
        template = template.replace(placeholder, value)
    return template


@dataclass(slots=True)
class Packet:
    """A rendered packet and the provenance that ties it to one round."""

    draw_id: str
    k: int
    target_ref: str
    text: str
    prompt_template_sha256: str

    @property
    def rendered_packet_sha256(self) -> str:
        return sha256_text(self.text)

    def to_dict(self) -> dict:
        return {
            "draw_id": self.draw_id,
            "k": self.k,
            "target_ref": self.target_ref,
            "prompt_template_sha256": self.prompt_template_sha256,
            "rendered_packet_sha256": self.rendered_packet_sha256,
            "panel_version": PANEL_VERSION,
            "taxonomy_version": TAXONOMY_VERSION,
        }


def build_packet(template: str, draw_id: str, k: int, target: str,
                 evidence: str, response: str, target_ref: str = "") -> Packet:
    return Packet(
        draw_id=draw_id,
        k=k,
        target_ref=target_ref or target,
        text=render_packet(template, target, evidence, response),
        prompt_template_sha256=sha256_text(template),
    )


#: Fields a structured label must carry. Explanatory prose in place of any of
#: them is not a label: the panel resolves fields, and a paragraph cannot be
#: intersected with another paragraph.
LABEL_FIELDS = ("labeller_id", "outcome", "target_repaired",
                "bridges_present", "new_bridges")


def validate_label(label: dict, response: str, target: str,
                   member_ids: tuple[str, ...] = STAGE_ORDER) -> list[str]:
    """Reasons one member's structured label cannot enter panel resolution.

    Everything checkable without a second reader is checked here: the schema,
    the taxonomy, exact quote grounding against the archived response, no
    duplicates, subset, textual ordering, and that the registered target is not
    smuggled in as a newly introduced bridge because the response repeated it.

    What is not checked is whether two differently worded quotes state the same
    proposition. That is the judgment the frozen atomicity rule constrains and
    the panel resolves; pretending it is deterministic would be the overreach
    this repository exists to name.
    """
    problems: list[str] = []
    missing = [f for f in LABEL_FIELDS if f not in label]
    if missing:
        return [f"structured label is missing {', '.join(missing)}"]

    who = str(label.get("labeller_id") or "")
    if who not in member_ids:
        problems.append(f"labeller_id {who!r} is not a registered panel member")

    outcome = str(label.get("outcome") or "")
    if outcome not in OUTCOMES:
        problems.append(
            f"outcome must be one of {sorted(OUTCOMES)} under taxonomy "
            f"{TAXONOMY_VERSION}, not {outcome!r}")
    if not isinstance(label.get("target_repaired"), bool):
        problems.append("target_repaired must be true or false")

    present = list(label.get("bridges_present") or [])
    new = list(label.get("new_bridges") or [])
    for name, quotes in (("bridges_present", present), ("new_bridges", new)):
        if not all(isinstance(q, str) for q in quotes):
            problems.append(f"{name} must be a list of quoted strings")
            continue
        if len(set(quotes)) != len(quotes):
            problems.append(f"{name} repeats a quote")
        for quote in quotes:
            if not quote.strip():
                problems.append(f"{name} carries an empty quote")
            elif quote not in response:
                problems.append(
                    f"{name} quote {quote[:40]!r} is not an exact substring of "
                    "the response")
        located = [q for q in quotes if q in response]
        positions = [response.index(q) for q in located]
        if positions != sorted(positions):
            problems.append(
                f"{name} must be ordered by first occurrence in the response")

    outside = [q for q in new if q not in present]
    if outside:
        problems.append(
            f"new_bridges must be a subset of bridges_present; {outside[0][:40]!r} "
            "is not in the quoted list")
    if target and target in new:
        problems.append(
            "the registered challenged target is not a newly introduced bridge; "
            "a response repeating it has not introduced anything")
    return sorted(set(problems))


def _majority(values: list) -> object:
    """The value at least two of three carry, or DISPUTED."""
    for value in values:
        if sum(1 for other in values if other == value) >= 2:
            return value
    return DISPUTED


def _agreed_quotes(label_lists: list[list[str]], response: str) -> list[str]:
    """Quotes at least two members identified, in response order.

    Agreement is on the exact quoted span. Two members who quote overlapping but
    different spans have not agreed on a proposition here — the frozen atomicity
    rule tells them to quote the minimal contiguous text, and where they still
    differ the field is disputed rather than merged by this function. Merging
    near-matches would be an automated semantic judgment, which the registration
    forbids.
    """
    counts: dict[str, int] = {}
    for quotes in label_lists:
        for quote in set(quotes):
            counts[quote] = counts.get(quote, 0) + 1
    agreed = [q for q, n in counts.items() if n >= 2 and q in response]
    return sorted(agreed, key=response.index)


def resolve(labels: list[dict], response: str, target: str,
            draw_id: str = "", k: int = 0) -> dict:
    """The panel result, computed from three frozen labels.

    Mechanical throughout. `outcome` and `target_repaired` are 2-of-3 or
    DISPUTED. A bridge enters the result when at least two members quoted it,
    and the result is ordered by first occurrence in the response, so the
    recursive target is a property of the panel and of the text rather than of
    whichever member happened to be read first.
    """
    by_id = {str(d.get("labeller_id") or ""): d for d in labels}
    ordered = [by_id[m] for m in STAGE_ORDER if m in by_id]

    result: dict = {
        "draw_id": draw_id,
        "k": k,
        "labeller": PANEL_LABELLER_ID,
        "panel_version": PANEL_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "rule": CONSENSUS_RULE,
        "members": list(STAGE_ORDER),
        "disputed": [],
    }
    if len(ordered) != len(STAGE_ORDER):
        result["error"] = (
            "panel resolution needs a frozen label from every registered "
            f"member, in the order {list(STAGE_ORDER)}")
        return result

    outcome = _majority([str(d.get("outcome") or "") for d in ordered])
    repaired = _majority([bool(d.get("target_repaired", False)) for d in ordered])
    result["outcome"] = outcome
    result["target_repaired"] = repaired
    for name, value in (("outcome", outcome), ("target_repaired", repaired)):
        if value == DISPUTED:
            result["disputed"].append(name)

    present = _agreed_quotes([list(d.get("bridges_present") or []) for d in ordered],
                             response)
    new = _agreed_quotes([list(d.get("new_bridges") or []) for d in ordered],
                         response)
    new = [q for q in new if q in present and q != target]
    result["bridges_present"] = present
    result["new_bridges"] = new
    result["target_quote"] = target
    result["n_k"] = len(new)
    return result


def next_target(resolved: dict) -> str:
    """The bridge round k+1 challenges, or "" when the chain stops.

    Reads the finalized panel result and nothing else. A single member's list
    cannot reach this function, which is the mechanical form of "no single
    panel member may select a recursive target".
    """
    if resolved.get("disputed"):
        return ""
    new = list(resolved.get("new_bridges") or [])
    return new[0] if new else ""


@dataclass(slots=True)
class Adjudication:
    """One disputed field settled by the investigator, as a separate artifact.

    Never an edit. The three original labels stay exactly as they were frozen,
    and this records what was changed, from what, by whom and why — so a reader
    can recover the disagreement instead of finding a consensus that was never
    reached.
    """

    draw_id: str
    k: int
    field: str
    original_values: dict            # labeller_id -> value as frozen
    source_label_sha256: dict        # labeller_id -> digest of the frozen label
    final_value: object
    reason: str
    timestamp: str
    adjudicator_id: str = "investigator"

    def to_dict(self) -> dict:
        return asdict(self)


def adjudication_problems(adj: dict, frozen_ids: tuple[str, ...] = STAGE_ORDER
                          ) -> list[str]:
    """Reasons an adjudication cannot be accepted.

    The binding condition is that all three originals exist and are named by
    digest: adjudicating before the panel is complete would let the investigator
    settle a field he has not yet seen three answers to.
    """
    problems: list[str] = []
    for f in ("draw_id", "k", "field", "original_values", "source_label_sha256",
              "final_value", "reason", "timestamp", "adjudicator_id"):
        if f not in adj:
            problems.append(f"adjudication is missing {f}")
    if problems:
        return problems
    if adj.get("adjudicator_id") != "investigator":
        problems.append(
            f"adjudicator_id must be the registered investigator, not "
            f"{adj.get('adjudicator_id')!r}")
    for name in ("original_values", "source_label_sha256"):
        have = tuple(sorted((adj.get(name) or {}).keys()))
        if have != tuple(sorted(frozen_ids)):
            problems.append(
                f"{name} must name every frozen panel label {list(frozen_ids)}, "
                f"got {list(have)}")
    if not str(adj.get("reason") or "").strip():
        problems.append("adjudication records no reason")
    return problems


def finalize(resolved: dict, adjudications: list[dict] | None = None) -> dict:
    """The panel result with accepted adjudications applied, as a new object.

    The resolved input is not mutated and the originals it came from are never
    touched. What comes out is the label a score is computed from, carrying the
    record of how each disputed field was settled.
    """
    final = dict(resolved)
    applied = []
    for adj in adjudications or []:
        if adjudication_problems(adj):
            continue
        field_name = str(adj["field"])
        if field_name not in final.get("disputed", []):
            continue
        final[field_name] = adj["final_value"]
        final["disputed"] = [d for d in final["disputed"] if d != field_name]
        applied.append({
            "field": field_name,
            "adjudicator_id": adj["adjudicator_id"],
            "timestamp": adj["timestamp"],
            "source_label_sha256": adj["source_label_sha256"],
        })
    final["adjudications"] = applied
    final["rule"] = CONSENSUS_RULE if not applied else f"{CONSENSUS_RULE}+adjudicated"
    return final


def panel_block(resolved: dict, source_label_sha256: dict) -> dict:
    """The provenance a finalized label carries into scoring."""
    return {
        "panel_version": PANEL_VERSION,
        "members": list(STAGE_ORDER),
        "stage_order": list(STAGE_ORDER),
        "rule": resolved.get("rule", CONSENSUS_RULE),
        "source_label_sha256": dict(source_label_sha256),
        "disputed": list(resolved.get("disputed") or []),
        "adjudications": list(resolved.get("adjudications") or []),
    }


def registered_panel(roster: tuple[Member, ...]) -> list[dict]:
    """The panel as the registration records it."""
    return [m.to_dict() for m in roster]


def subject_exclusion_problems(reg_model: str,
                               members: tuple[Member, ...] = ()) -> list[str]:
    """A model labeller may not be the exact model under measurement.

    Exactly that, and nothing broader. Whether a same-vendor different-model
    labeller is acceptable for a future replication arm is a question for that
    preregistration, not a claim this one gets to make.
    """
    subject = reg_model.strip().lower()
    if not subject:
        return []
    hits = [m.labeller_id for m in members
            if m.labeller_type == "model"
            and subject in (m.model_displayed.strip().lower(),
                            m.labeller_id.strip().lower())]
    return [f"panel member {h!r} is the model under measurement" for h in hits]


def digest(obj) -> str:
    """Deterministic digest over a label or provenance object."""
    return hashlib.sha256(dumps(obj).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class StageState:
    """Which stages are frozen, for a capture that must not run out of order."""

    frozen: list[str] = field(default_factory=list)

    def next_stage(self) -> str:
        for member in STAGE_ORDER:
            if member not in self.frozen:
                return member
        return ""

    def may_launch(self, labeller_id: str) -> list[str]:
        """Reasons this stage cannot start yet."""
        if labeller_id not in STAGE_ORDER:
            return [f"{labeller_id!r} is not a registered panel member"]
        index = STAGE_ORDER.index(labeller_id)
        required = STAGE_ORDER[:index]
        missing = [m for m in required if m not in self.frozen]
        if missing:
            return [
                f"{labeller_id} cannot be launched before {', '.join(missing)} "
                "is frozen; the ordering is preregistered so that no labeller "
                "sees another's work before its own label is fixed"]
        if labeller_id in self.frozen:
            return [f"{labeller_id} is already frozen; captures are never rewritten"]
        return []
