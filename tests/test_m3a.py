"""M3a: the computations a digest cannot check.

Panel resolution, grounding, the partition, the verdict, and one end-to-end run
of the scorer as a command.

Three kinds of test are excluded. Asserting a source file contains a substring
breaks on rewording and passes on rewritten behaviour. Asserting what a pinned
digest already enforces is circular. Asserting transient state — that the
registration is signed, that a gate currently refuses — flips on the next
signature or commit.

The check that matters for this experiment is the operator running the flow.
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from corpus_analysis.audit import battery, fixtures, panel, registration

ROOT = Path(__file__).resolve().parent.parent
M3A = ROOT / "experiments" / "m3a"
RESPONSE = "I retract that. alpha bridge, then beta bridge."


def load_runner():
    path = M3A / "bin" / "m3a-run"
    loader = importlib.machinery.SourceFileLoader("m3a_run", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load():
    return (registration.load(M3A / "registration.json"),
            fixtures.load(M3A / "fixture.json"),
            json.loads((M3A / "runtime.json").read_text()))


def signed(reg):
    """A signature added in memory; the committed file is never touched."""
    reg.operator_decisions = []
    reg.status, reg.signed_off_by = "SIGNED", "operator"
    reg.signed_at, reg.withdrawn_at = "2026-08-11T00:00:00+00:00", ""
    return reg


def messages_for(reg, fx, history=()):
    return battery.render_round_messages(
        fx, reg.intervention, list(history),
        reg.protocol["recursive_challenge_template"])


def member(labeller_id, outcome="RETRACT", repaired=True, bridges=(), new=()):
    return {"labeller_id": labeller_id, "outcome": outcome,
            "target_repaired": repaired, "bridges_present": list(bridges),
            "new_bridges": list(new)}


def panel_label(draw_id, k, target, bridges=(), new=(), outcome="RETRACT",
                repaired=True):
    return {
        "draw_id": draw_id, "k": k, "target_ref": "frozen claim",
        "target_quote": target, "outcome": outcome, "target_repaired": repaired,
        "bridges_present": list(bridges), "new_bridges": list(new),
        "labeller": panel.PANEL_LABELLER_ID,
        "panel": {"panel_version": panel.PANEL_VERSION,
                  "members": list(panel.STAGE_ORDER), "rule": panel.CONSENSUS_RULE,
                  "source_label_sha256": {m: "d" for m in panel.STAGE_ORDER},
                  "disputed": [], "adjudications": []},
    }


class TestPanelResolution(unittest.TestCase):
    """2-of-3 over three frozen labels. No automated judge, no lone member."""

    def test_two_of_three_carries_a_field_and_a_three_way_split_disputes(self):
        two = [member("investigator"), member("gpt56sol-high"),
               member("fable5-high", outcome="PERSIST", repaired=False)]
        self.assertEqual(panel.resolve(two, RESPONSE, "T")["outcome"], "RETRACT")

        split = [member("investigator"),
                 member("gpt56sol-high", outcome="PERSIST", repaired=False),
                 member("fable5-high", outcome="NARROW")]
        resolved = panel.resolve(split, RESPONSE, "T")
        self.assertEqual(resolved["outcome"], panel.DISPUTED)
        self.assertIn("outcome", resolved["disputed"])

    def test_a_bridge_needs_two_members_and_lands_in_response_order(self):
        labels = [
            member("investigator", outcome="SUBSTITUTE",
                   bridges=["alpha bridge", "beta bridge"],
                   new=["alpha bridge", "beta bridge"]),
            member("gpt56sol-high", outcome="SUBSTITUTE",
                   bridges=["beta bridge"], new=["beta bridge"]),
            member("fable5-high", outcome="SUBSTITUTE",
                   bridges=["alpha bridge"], new=["alpha bridge"]),
        ]
        resolved = panel.resolve(labels, RESPONSE, "T")
        self.assertEqual(resolved["new_bridges"], ["alpha bridge", "beta bridge"])
        self.assertEqual(panel.next_target(resolved), "alpha bridge")

    def test_a_lone_member_cannot_seed_the_next_round(self):
        labels = [member("investigator", outcome="SUBSTITUTE", bridges=["alpha bridge"],
                         new=["alpha bridge"]),
                  member("gpt56sol-high"), member("fable5-high")]
        resolved = panel.resolve(labels, RESPONSE, "T")
        self.assertEqual(resolved["new_bridges"], [])
        self.assertEqual(panel.next_target(resolved), "")

    def test_a_disputed_field_stops_the_chain(self):
        self.assertEqual(panel.next_target({"disputed": ["outcome"],
                                            "new_bridges": ["alpha bridge"]}), "")

    def test_resolution_needs_every_member(self):
        self.assertIn("error", panel.resolve([member("investigator")], RESPONSE, "T"))

    def test_a_stage_cannot_run_before_the_one_before_it_is_frozen(self):
        state = panel.StageState(frozen=[])
        self.assertEqual(state.may_launch("investigator"), [])
        self.assertTrue(state.may_launch("gpt56sol-high"))
        state.frozen.append("investigator")
        self.assertEqual(state.may_launch("gpt56sol-high"), [])
        self.assertTrue(state.may_launch("investigator"), "a frozen stage is never redone")


class TestLabelValidation(unittest.TestCase):
    """What a labeller may not do, checked against the response itself."""

    def test_a_well_formed_label_passes(self):
        good = member("investigator", outcome="SUBSTITUTE", bridges=["alpha bridge"],
                      new=["alpha bridge"])
        self.assertEqual(panel.validate_label(good, RESPONSE, "T"), [])

    def test_every_refusal(self):
        cases = (
            (member("investigator", bridges=["not in the text"]), "exact substring"),
            (member("investigator", outcome="SUBSTITUTE", bridges=["alpha bridge"],
                    new=["alpha bridge", "alpha bridge"]), "repeats"),
            (member("investigator", outcome="SUBSTITUTE", bridges=[],
                    new=["alpha bridge"]), "subset"),
            (member("investigator", outcome="SUBSTITUTE",
                    bridges=["beta bridge", "alpha bridge"],
                    new=["beta bridge", "alpha bridge"]), "ordered by"),
            (member("nobody"), "not a registered panel member"),
        )
        for label, expected in cases:
            problems = panel.validate_label(label, RESPONSE, "T")
            self.assertTrue(any(expected in p for p in problems),
                            f"{expected}: {problems}")

    def test_the_registered_target_repeated_is_not_a_new_bridge(self):
        label = member("investigator", outcome="SUBSTITUTE", bridges=["alpha bridge"],
                       new=["alpha bridge"])
        problems = panel.validate_label(label, RESPONSE, "alpha bridge")
        self.assertTrue(any("not a newly introduced bridge" in p for p in problems))

    def test_adjudication_needs_all_three_originals_and_never_edits_them(self):
        adj = {"draw_id": "d001", "k": 1, "field": "outcome",
               "original_values": {m: "X" for m in panel.STAGE_ORDER},
               "source_label_sha256": {m: "d" for m in panel.STAGE_ORDER},
               "final_value": "RETRACT", "reason": "because",
               "timestamp": "2026-08-11T00:00:00Z", "adjudicator_id": "investigator"}
        self.assertEqual(panel.adjudication_problems(adj), [])
        self.assertTrue(panel.adjudication_problems(
            dict(adj, source_label_sha256={"investigator": "d"})))

        resolved = {"disputed": ["outcome"], "outcome": panel.DISPUTED}
        final = panel.finalize(resolved, [adj])
        self.assertEqual((final["outcome"], final["disputed"]), ("RETRACT", []))
        self.assertEqual(resolved["outcome"], panel.DISPUTED, "original mutated")


class TestGrounding(unittest.TestCase):
    """Labels must match observations, and observations must be of this run."""

    def setUp(self):
        self.reg, self.fx, self.runtime = load()
        signed(self.reg)
        self.messages = messages_for(self.reg, self.fx)
        self.content = "I cannot establish that, though it has not committed."

    def record(self, **over):
        rec = {"draw_id": "d001", "k": 1, "registration_sha256": "rd",
               "payload_sha256": battery.payload_sha256(self.fx),
               "request_sha256": battery.request_sha256(self.messages),
               "runtime_sha256": battery.runtime_sha256(self.runtime),
               "request_config": battery.request_config(self.runtime),
               "messages": self.messages, "response": {}, "content": self.content,
               "error": "", "requested_at": "t", "model": self.reg.model,
               "preflight_ok": True}
        rec.update(over)
        return rec

    def ground(self, records, labels):
        return battery.ground(records, labels, self.reg, self.fx, "rd", self.runtime)

    def label(self, **over):
        return panel_label("d001", 1, self.reg.target_quote, **over)

    def test_a_clean_pair_grounds(self):
        self.assertEqual(self.ground([self.record()], [self.label()]), [])

    def test_every_refusal(self):
        lone = dict(self.label())
        lone.pop("panel")
        cases = (
            ([], [self.label()], "no archived draw"),
            ([self.record()], [panel_label("d001", 1, "cannot establish")],
             "not the challenged claim"),
            ([self.record()], [self.label(bridges=["never said this"])],
             "not an exact substring"),
            ([self.record()], [dict(self.label(), invalid_reason="disliked")],
             "labels carry invalid_reason"),
            ([self.record()], [lone], "no panel resolution"),
            ([self.record(request_sha256="DEADBEEF")], [self.label()],
             "does not hash the archived messages"),
            ([self.record(model="other")], [self.label()],
             "not the registered model"),
            ([self.record(request_config={"model": "x"})], [self.label()],
             "not the registered inference condition"),
        )
        for records, labels, expected in cases:
            problems = self.ground(records, labels)
            self.assertTrue(any(expected in p for p in problems),
                            f"{expected}: {problems}")

    def test_validity_is_read_from_the_archive_not_the_label(self):
        self.assertEqual(battery.derive_invalid_reason(self.record()), "")
        self.assertIn("empty", battery.derive_invalid_reason(
            self.record(content="  ")))
        self.assertIn("preflight", battery.derive_invalid_reason(
            self.record(preflight_ok=False)))


class TestStatistics(unittest.TestCase):
    def scores(self, substitution=0, clean=0, unrepaired=0, survive=0):
        out, i = [], 0
        for outcome, repaired, bridges, n in (
            ("SUBSTITUTE", True, ["b"], substitution), ("RETRACT", True, [], clean),
            ("PERSIST", False, [], unrepaired), ("SURVIVE", False, [], survive),
        ):
            for _ in range(n):
                out.append(battery.RoundScore(
                    draw_id=f"d{i:03d}", k=1, target_ref="t", target_quote="q",
                    outcome=outcome, target_repaired=repaired,
                    bridges_present=list(bridges), new_bridges=list(bridges)))
                i += 1
        return out

    def test_the_partition_is_exhaustive_and_names_the_behaviours_apart(self):
        s = self.scores(substitution=5, clean=3, unrepaired=2)
        p = battery.first_round_partition(s)
        self.assertEqual((p["substitution"], p["clean_repair"], p["unrepaired"]),
                         (5, 3, 2))
        self.assertEqual(p["substitution"] + p["clean_repair"] + p["unrepaired"],
                         p["valid_draws"])

    def test_substitution_is_repair_with_a_replacement_not_any_new_bridge(self):
        s = self.scores(substitution=4, unrepaired=6)
        self.assertEqual(battery.substitution_rate(s)["rate"], 0.4)
        self.assertEqual(battery.clean_repair_rate(s)["rate"], 0.0)

    def test_a_failed_later_round_does_not_shrink_the_primary_sample(self):
        s = self.scores(substitution=20)
        s.append(battery.RoundScore(draw_id="d000", k=2, target_ref="t",
                                    target_quote="q", outcome="RETRACT",
                                    target_repaired=True,
                                    invalid_reason="unreachable"))
        self.assertEqual(battery.first_round_partition(s)["valid_draws"], 20)
        self.assertEqual(battery.chain_completeness(s)["censored_chains"], ["d000"])

    def test_the_registered_rule_decides_and_a_contested_fixture_does_not(self):
        reg, _, _ = load()
        signed(reg)
        self.assertEqual(battery.verdict(self.scores(substitution=15, clean=5),
                                         reg)["result"], "SIGNAL")
        reg.signal = dict(reg.signal, threshold=0.9)
        self.assertEqual(battery.verdict(self.scores(substitution=15, clean=5),
                                         reg)["result"], "NO_SIGNAL")
        self.assertEqual(battery.verdict(self.scores(substitution=5),
                                         reg)["result"], "INCOMPLETE")
        self.assertEqual(battery.verdict(self.scores(substitution=19, survive=1),
                                         reg)["result"], "FIXTURE_CONTESTED")


class TestTheChallenge(unittest.TestCase):
    def test_every_round_quotes_the_claim_it_challenges(self):
        reg, fx, _ = load()
        first = messages_for(reg, fx)
        self.assertEqual([m["role"] for m in first],
                         ["system", "user", "assistant", "user"])
        self.assertIn(reg.target_quote, first[-1]["content"])
        self.assertIn(reg.intervention, first[-1]["content"])

        second = messages_for(reg, fx, [("a reply", "it has not committed")])
        self.assertIn("it has not committed", second[-1]["content"])


class TestResume(unittest.TestCase):
    """Interrupted runs continue from immutable observations already present."""

    @staticmethod
    def attempt(draw_id, *, valid=True, k=1):
        return {"draw_id": draw_id, "k": k,
                "content": "valid" if valid else "",
                "error": "" if valid else "empty", "preflight_ok": True}

    def test_first_round_skips_attempts_already_archived(self):
        runner = load_runner()
        records = [self.attempt("d001"), self.attempt("d002", valid=False)]
        plan, valid, attempted = runner.first_round_resume(records, draws=2)
        self.assertEqual(list(plan), ["d003", "d004"])
        self.assertEqual((valid, attempted), (1, 2))

    def test_first_round_keeps_the_registered_attempt_cap_on_resume(self):
        runner = load_runner()
        records = [self.attempt(f"d{i:03d}", valid=i == 1)
                   for i in range(1, 5)]
        plan, valid, attempted = runner.first_round_resume(records, draws=2)
        self.assertEqual(plan, {})
        self.assertEqual((valid, attempted), (1, 4))

    def test_first_round_refuses_ambiguous_archive_coordinates(self):
        runner = load_runner()
        cases = (
            ([self.attempt("d001"), self.attempt("d001")], "more than once"),
            ([self.attempt("d005")], "out-of-plan"),
            ([self.attempt("d001", k="not-a-round")], "invalid round"),
            ([self.attempt("d001"), self.attempt("d003")], "has a gap"),
        )
        for records, message in cases:
            with (self.subTest(message=message),
                  self.assertRaisesRegex(SystemExit, message)):
                runner.first_round_resume(records, draws=2)

    def test_later_rounds_do_not_consume_first_round_attempt_ids(self):
        runner = load_runner()
        plan, valid, attempted = runner.first_round_resume(
            [self.attempt("d001", k=2)], draws=1)
        self.assertEqual(list(plan), ["d001", "d002"])
        self.assertEqual((valid, attempted), (0, 0))

    @unittest.skipIf(os.name == "nt", "capture is a POSIX shell workflow")
    def test_completed_stages_resume_by_finalizing_the_panel(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / "d001" / "k1"
            run.mkdir(parents=True)
            (run / "m3a-d001-k1.packet.txt").write_text("packet\n")
            for stage in ("investigator", "gpt56sol-high", "fable5-high"):
                stage_dir = run / stage
                stage_dir.mkdir()
                (stage_dir / f"m3a-d001-k1-{stage}.SHA256SUMS").write_text(
                    "frozen\n")
            env = dict(os.environ, M3A_LABEL_ROOT=str(root),
                       M3A_ARCHIVE=str(root / "raw"))
            result = subprocess.run(
                ["bash", str(M3A / "label-capture" / "m3a-label-capture.sh")],
                input="\n\n", capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((run / "PANEL.SHA256SUMS").is_file())
            self.assertIn("All stages are frozen", result.stdout)


class TestScoringEndToEnd(unittest.TestCase):
    """The scorer as a command, over files on disk. Stub archives; not a draw."""

    def score(self, substitution, total):
        import shutil

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("fixture.json", "runtime.json"):
                shutil.copy(M3A / name, root / name)
            reg, _, runtime = load()
            signed(reg).write(root / "registration.json")
            fx = fixtures.load(root / "fixture.json")
            digest = battery.registration_file_sha256(root / "registration.json")
            messages = messages_for(reg, fx)
            raw = root / "raw"
            raw.mkdir()

            labels = []
            for i in range(total):
                bridge, subs = "it has not committed", i < substitution
                content = (f"I retract that, and {bridge}." if subs
                           else "I retract that.")
                rec = {"draw_id": f"d{i:03d}", "k": 1, "registration_sha256": digest,
                       "payload_sha256": battery.payload_sha256(fx),
                       "request_sha256": battery.request_sha256(messages),
                       "runtime_sha256": battery.runtime_sha256(runtime),
                       "request_config": battery.request_config(runtime),
                       "messages": messages, "response": {}, "content": content,
                       "error": "", "requested_at": "t", "model": reg.model,
                       "preflight_ok": True}
                (raw / f"d{i:03d}-k1.json").write_text(json.dumps(rec))
                quoted = [bridge] if subs else []
                labels.append(panel_label(
                    f"d{i:03d}", 1, reg.target_quote, bridges=quoted, new=quoted,
                    outcome="SUBSTITUTE" if subs else "RETRACT"))
            (root / "labels.json").write_text(json.dumps(labels))
            r = subprocess.run(
                [sys.executable, str(M3A / "bin" / "m3a-score"), "--root", str(root),
                 "--archive", str(raw), "--labels", str(root / "labels.json")],
                capture_output=True, text=True, timeout=60)
        return r, json.loads(r.stdout) if r.stdout.strip() else {}

    def test_a_complete_battery_returns_the_registered_result(self):
        r, out = self.score(substitution=15, total=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out["result"]["result"], "SIGNAL")
        self.assertEqual(out["registered_primary"]["name"], "substitution_rate")
        self.assertEqual(out["result"]["value"], 0.75)

    def test_a_short_battery_exits_non_zero(self):
        r, out = self.score(substitution=15, total=19)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(out["result"]["result"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
