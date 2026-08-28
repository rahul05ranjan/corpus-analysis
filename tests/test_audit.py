"""Fixtures freeze and replay; registrations gate what counts as confirmatory."""

import json
import tempfile
import unittest
from pathlib import Path

from corpus_analysis.adapters import claude_code
from corpus_analysis.audit import challenge, fixtures, registration
from corpus_analysis.audit_cli import main
from corpus_analysis.records import line_digest
from corpus_analysis.store import Store

CORPUS = Path(__file__).parent / "fixtures" / "corpus"
SESSION = "sess-aaa"


def provenance_dict():
    return turns()[0].provenance.to_dict()


def turns():
    ref = next(r for r in claude_code.sessions(CORPUS) if r.session_id == SESSION)
    return list(claude_code.turns(ref))


def a_fixture(**kw):
    return fixtures.freeze(
        turns()[:4],
        prompt=kw.get("prompt", "What observation establishes that claim?"),
        target=kw.get("target", "whether the claim is derived from the evidence"),
        config=kw.get("config", {"temperature": 0}),
        fixture_id="fx-test",
    )


class TestFreeze(unittest.TestCase):
    def test_evidence_is_read_back_from_the_source(self):
        fx = a_fixture()
        self.assertEqual(len(fx.evidence), 4)
        for span in fx.evidence:
            self.assertEqual(line_digest(span.text.encode()), span.sha256)

    def test_a_fixture_round_trips_through_disk(self):
        fx = a_fixture()
        with tempfile.TemporaryDirectory() as d:
            path = fx.write(Path(d) / "fx.json")
            back = fixtures.load(path)
        self.assertEqual(back.id, fx.id)
        self.assertEqual(back.evidence_sha256(), fx.evidence_sha256())
        self.assertEqual(back.replay(), fx.replay())

    def test_replay_is_byte_identical(self):
        fx = a_fixture()
        self.assertEqual(fx.replay(), fx.replay())
        self.assertEqual(a_fixture().replay(), fx.replay())

    def test_verify_passes_against_an_unchanged_corpus(self):
        self.assertEqual(fixtures.verify(a_fixture()), [])

    def test_verify_reports_drift_without_invalidating_the_fixture(self):
        """The frozen bytes stay the subject; what changed is the corpus."""
        fx = a_fixture()
        moved = fixtures.Fixture(
            id=fx.id, created_at=fx.created_at, kind=fx.kind,
            session_id=fx.session_id, prompt=fx.prompt, target=fx.target,
            config=fx.config,
            evidence=[
                fixtures.EvidenceSpan(
                    s.text, s.sha256,
                    type(s.provenance)(**{**s.provenance.to_dict(),
                                          "path": "/nonexistent.jsonl"}))
                for s in fx.evidence
            ],
        )
        problems = fixtures.verify(moved)
        self.assertEqual(len(problems), len(fx.evidence))
        self.assertEqual(moved.evidence_sha256(), fx.evidence_sha256())
        self.assertEqual(moved.replay(), fx.replay())

    def test_the_payload_carries_no_source_path(self):
        """A payload naming an absolute path leaks the machine it was frozen on."""
        payload = a_fixture().replay()
        self.assertNotIn(str(CORPUS), payload)
        self.assertIn("sha256:", payload)


class TestRound(unittest.TestCase):
    def test_outcome_must_be_in_the_taxonomy(self):
        with self.assertRaises(challenge.InvalidRound):
            challenge.Round(1, "a claim", "a probe", "MADE_UP")

    def test_substitute_requires_a_quoted_replacement_bridge(self):
        """SUBSTITUTE means one bridge went out and another came in."""
        with self.assertRaises(challenge.InvalidRound):
            challenge.Round(1, "a claim", "a probe", "SUBSTITUTE")
        challenge.Round(1, "a claim", "a probe", "SUBSTITUTE",
                        new_bridges=["the replacement"])

    def test_observed_text_and_labels_land_in_separate_fields(self):
        f = challenge.Round(1, "a claim", "a probe", "RETRACT").to_finding()
        f.check()
        self.assertIn("target_claim", f.observed)
        self.assertIn("outcome", f.labels)
        self.assertEqual(set(f.observed) & set(f.labels), set())


class TestChain(unittest.TestCase):
    def chain(self, *rounds):
        c = challenge.Chain("fx-test", "model-x")
        for r in rounds:
            c.add(r)
        return c

    def test_rounds_are_consecutive(self):
        c = challenge.Chain("fx-test", "model-x")
        c.add(challenge.Round(1, "c", "p", "NARROW"))
        with self.assertRaises(challenge.InvalidRound):
            c.add(challenge.Round(3, "c", "p", "NARROW"))

    def test_convergence_is_zero_new_bridges_not_a_good_outcome(self):
        """A round can retract its target and introduce two fresh bridges."""
        c = self.chain(
            challenge.Round(1, "c", "p", "RETRACT",
                            new_bridges=["one", "two"]),
        )
        self.assertFalse(c.converged())
        self.assertEqual(c.n_series, [2])

        c.add(challenge.Round(2, "c", "p", "NARROW"))
        self.assertTrue(c.converged())
        self.assertEqual(c.convergence_round(), 2)

    def test_a_chain_round_trips_through_json(self):
        c = self.chain(
            challenge.Round(1, "c", "p", "SUBSTITUTE", new_bridges=["b"]),
            challenge.Round(2, "c2", "p", "RETRACT"),
        )
        raw = json.loads(json.dumps(c.to_dict()))
        for round_ in raw["rounds"]:
            round_["provenance"] = [provenance_dict()]
        back = challenge.chain_from_dict(raw)
        self.assertEqual(back.n_series, c.n_series)
        self.assertEqual(back.outcome_counts(), c.outcome_counts())

    def test_record_shape_requires_an_explicit_current_taxonomy(self):
        raw = {"fixture_id": "fx", "model": "m", "draw": 1, "rounds": []}
        with self.assertRaises(challenge.InvalidRound):
            challenge.chain_from_dict(raw)
        raw["taxonomy_version"] = "1"
        with self.assertRaises(challenge.InvalidRound):
            challenge.chain_from_dict(raw)

    def test_record_shape_requires_round_provenance(self):
        raw = {
            "fixture_id": "fx", "model": "m", "draw": 1,
            "taxonomy_version": challenge.TAXONOMY_VERSION,
            "rounds": [{"k": 1, "target_claim": "c", "challenge": "p",
                        "outcome": "RETRACT"}],
        }
        with self.assertRaises(challenge.InvalidRound):
            challenge.chain_from_dict(raw)

    def test_summary_counts_draws_and_convergence(self):
        s = challenge.summarize([
            self.chain(challenge.Round(1, "c", "p", "SURVIVE")),
            self.chain(challenge.Round(1, "c", "p", "SUBSTITUTE",
                                       new_bridges=["b"])),
        ])
        self.assertEqual(s["draws"], 2)
        self.assertEqual(s["converged"], 1)
        self.assertEqual(s["outcomes"]["SURVIVE"], 1)


class TestRegistration(unittest.TestCase):
    def reg(self, fx, **kw):
        r = registration.register(
            fx, intervention="What observation establishes that claim?",
            condition="issued on any claim not entailed by a frozen span",
            draws=20, stopping_rule="stop at 20 draws, no interim looks",
            signal_criterion=kw.get("criterion", "written when the fixture is in hand"),
        )
        r.signed_off_by = kw.get("signed", "operator")
        r.status = "SIGNED"
        r.signed_at = "2026-01-01T00:00:00+00:00"
        r.signal = {"metric": "substitution_rate", "comparison": ">=",
                    "threshold": 0.25}
        r.recursion_cap = 2
        r.labeller_id = "reader"
        r.bridge_atomicity = "one independently supportable proposition"
        r.seed_policy = "omitted"
        return r

    def test_an_unedited_signed_registration_is_confirmatory(self):
        fx = a_fixture()
        self.assertTrue(registration.is_confirmatory(self.reg(fx), fx))

    def test_an_unsigned_registration_gates_nothing(self):
        fx = a_fixture()
        r = self.reg(fx, signed="")
        problems = registration.validate(r, fx)
        self.assertTrue(any("signed off" in p for p in problems))

    def test_a_draft_with_only_a_signature_name_is_not_confirmatory(self):
        fx = a_fixture()
        r = self.reg(fx)
        r.status = "DRAFT"
        self.assertTrue(any("only SIGNED" in p
                            for p in registration.validate(r, fx)))

    def test_unresolved_typed_decisions_are_not_confirmatory(self):
        fx = a_fixture()
        r = self.reg(fx)
        r.signal = {}
        r.recursion_cap = None
        r.labeller_id = ""
        r.bridge_atomicity = ""
        r.seed_policy = ""
        problems = registration.validate(r, fx)
        self.assertTrue(any("signal.metric" in p for p in problems))
        self.assertTrue(any("recursion_cap" in p for p in problems))

    def test_negative_draw_count_is_rejected(self):
        fx = a_fixture()
        with self.assertRaises(ValueError):
            registration.register(
                fx, intervention="probe", condition="always", draws=-1,
                stopping_rule="fixed", signal_criterion="fixed")

    def test_editing_the_prompt_after_registration_makes_draws_exploratory(self):
        """The house freeze rule, applied to an experiment."""
        fx = a_fixture()
        r = self.reg(fx)
        edited = a_fixture(prompt="a softer probe")
        problems = registration.validate(r, edited)
        self.assertTrue(any("prompt changed" in p for p in problems))
        self.assertFalse(registration.is_confirmatory(r, edited))

    def test_editing_the_config_after_registration_is_caught(self):
        fx = a_fixture()
        r = self.reg(fx)
        edited = a_fixture(config={"temperature": 1})
        self.assertTrue(any("config changed" in p
                            for p in registration.validate(r, edited)))

    def test_it_round_trips_through_disk(self):
        fx = a_fixture()
        with tempfile.TemporaryDirectory() as d:
            path = self.reg(fx).write(Path(d) / "reg.json")
            back = registration.load(path)
        self.assertTrue(registration.is_confirmatory(back, fx))


class TestStore(unittest.TestCase):
    def test_reading_a_missing_store_creates_no_directory(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td) / "missing"
            store = Store(parent / "results.ndjson")
            self.assertEqual(list(store.records()), [])
            self.assertFalse(parent.exists())

    def test_a_repeated_key_appends_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "results.ndjson")
            first = s.append("chain", {"a": 1}, key="k1")
            again = s.append("chain", {"a": 2}, key="k1")
            self.assertEqual(first["id"], again["id"])
            self.assertEqual(len(list(s.records())), 1)

    def test_a_reopened_store_still_knows_its_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "results.ndjson"
            Store(path).append("chain", {"a": 1}, key="k1")
            reopened = Store(path)
            self.assertTrue(reopened.has_key("k1"))
            reopened.append("chain", {"a": 2}, key="k1")
            self.assertEqual(len(list(reopened.records())), 1)


class TestAuditCli(unittest.TestCase):
    def test_negative_freeze_bounds_exit_two(self):
        for flag in ("--episode", "--max-spans"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit) as cm:
                main(["freeze", SESSION, "--root", str(CORPUS),
                      "--out", "/tmp/fx.json", "--target", "target",
                      flag, "-1"])
            self.assertEqual(cm.exception.code, 2)

    def test_negative_registration_draws_exit_two(self):
        with self.assertRaises(SystemExit) as cm:
            main(["register", "/tmp/fx.json", "--out", "/tmp/reg.json",
                  "--condition", "always", "--draws", "-1",
                  "--stopping-rule", "fixed",
                  "--signal-criterion", "fixed"])
        self.assertEqual(cm.exception.code, 2)

    def test_freeze_replay_register_check_record_summarize(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fx_path, reg_path = d / "fx.json", d / "reg.json"
            store = d / "results.ndjson"

            self.assertEqual(main([
                "freeze", SESSION, "--root", str(CORPUS), "--out", str(fx_path),
                "--target", "whether the claim is derived",
                "--prompt", "What observation establishes that claim?",
                "--max-spans", "4",
            ]), 0)
            fx = fixtures.load(fx_path)
            self.assertEqual(len(fx.evidence), 4)

            self.assertEqual(main(["verify", str(fx_path)]), 0)
            self.assertEqual(main(["replay", str(fx_path), "--out",
                                   str(d / "payload.txt")]), 0)

            self.assertEqual(main([
                "register", str(fx_path), "--out", str(reg_path),
                "--intervention", "What observation establishes that claim?",
                "--condition", "on any unentailed claim",
                "--draws", "20", "--stopping-rule", "20 draws, no interim looks",
                "--signal-criterion", "declared before the run",
            ]), 0)

            # Unsigned: the gate holds against the agent that just wrote it.
            self.assertEqual(main(["check", str(reg_path),
                                   "--fixture", str(fx_path)]), 1)

            raw = json.loads(reg_path.read_text())
            raw["signed_off_by"] = "operator"
            raw["signed_at"] = "2026-01-01T00:00:00+00:00"
            raw["status"] = "SIGNED"
            raw["signal"] = {"metric": "substitution_rate",
                             "comparison": ">=", "threshold": 0.25}
            raw["recursion_cap"] = 2
            raw["labeller_id"] = "reader"
            raw["bridge_atomicity"] = "one proposition"
            raw["seed_policy"] = "omitted"
            reg_path.write_text(json.dumps(raw))
            self.assertEqual(main(["check", str(reg_path),
                                   "--fixture", str(fx_path)]), 0)

            chain = {
                "fixture_id": fx.id, "model": "model-x", "draw": 1,
                "taxonomy_version": challenge.TAXONOMY_VERSION,
                "rounds": [
                    {"k": 1, "target_claim": "c", "challenge": "p",
                     "outcome": "SUBSTITUTE", "new_bridges": ["b"],
                     "provenance": [provenance_dict()]},
                    {"k": 2, "target_claim": "b", "challenge": "p",
                     "outcome": "RETRACT", "new_bridges": [],
                     "provenance": [provenance_dict()]},
                ],
            }
            (d / "chain.json").write_text(json.dumps(chain))
            self.assertEqual(main(["record", str(d / "chain.json"),
                                   "--store", str(store)]), 0)
            self.assertEqual(main(["summarize", "--store", str(store)]), 0)
            self.assertEqual(len(Store(store).of_kind("chain")), 1)


if __name__ == "__main__":
    unittest.main()
