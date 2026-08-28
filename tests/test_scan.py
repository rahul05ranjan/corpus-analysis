"""The vertical slice, over the synthetic fixture corpus.

The fixture is written by hand and contains no session text from any real
corpus. That is a publication constraint, not a convenience: a test fixture is
the easiest place for a private transcript to reach a public repository.
"""

import unittest
from pathlib import Path

from corpus_analysis.adapters import claude_code
from corpus_analysis.adapters.base import SchemaDrift, SessionRef
from corpus_analysis.scan import scan_sessions
from corpus_analysis.scan.episodes import segment
from corpus_analysis.scan.sessions import scan

CORPUS = Path(__file__).parent / "fixtures" / "corpus"
DRIFT = Path(__file__).parent / "fixtures" / "drift" / "claude"
SESSION = "sess-aaa"


def parent_ref() -> SessionRef:
    return next(r for r in claude_code.sessions(CORPUS) if r.session_id == SESSION)


def turns():
    return list(claude_code.turns(parent_ref()))


class TestEnumeration(unittest.TestCase):
    def test_finds_parents_and_attributes_subagents(self):
        refs = claude_code.sessions(CORPUS)
        by_id = {r.session_id: r for r in refs}
        self.assertIn(SESSION, by_id)
        self.assertIn("agent-1", by_id)
        self.assertEqual(by_id["agent-1"].parent, SESSION)

    def test_probe_raises_on_an_unrecognised_format(self):
        drift = next(r for r in claude_code.sessions(DRIFT)
                     if r.session_id == "sess-drift")
        with self.assertRaises(SchemaDrift):
            claude_code.probe(drift)

    def test_probe_accepts_the_known_format(self):
        claude_code.probe(parent_ref())

    def test_scan_path_fails_loudly_on_schema_drift(self):
        with self.assertRaises(SchemaDrift):
            scan(claude_code, DRIFT)


class TestTypedPrompts(unittest.TestCase):
    def typed(self):
        return [t for t in turns() if t.flags["typed"]]

    def test_only_operator_text_counts(self):
        self.assertEqual([t.text for t in self.typed()],
                         ["add a scan command", "adjust the output path"])

    def test_continuation_summary_is_not_a_typed_prompt(self):
        """The bug this scanner was written to not have.

        A continuation summary is prose in a user record with no harness
        markup. Counted as typed, it opens an episode nobody asked for and
        attributes every turn after a compaction to it.
        """
        summaries = [t for t in turns() if t.flags["compact_summary"]]
        self.assertEqual(len(summaries), 1)
        self.assertFalse(summaries[0].flags["typed"])

    def test_command_echo_is_not_a_typed_prompt(self):
        echoes = [t for t in turns() if "<command-name>" in (t.text or "")]
        self.assertEqual(echoes, [])


class TestTurnFields(unittest.TestCase):
    def test_provenance_locates_the_source_line(self):
        first = turns()[0]
        self.assertEqual(first.provenance.line, 0)
        self.assertEqual(len(first.provenance.sha256), 64)
        self.assertTrue(first.provenance.path.endswith("sess-aaa.jsonl"))

    def test_thinking_is_counted_but_its_text_is_absent(self):
        thinking = [t for t in turns() if t.kinds["thinking"]]
        self.assertEqual(len(thinking), 2)
        self.assertEqual(sum(t.chars["thinking"] for t in thinking), 0)
        self.assertTrue(all(t.chars["signature"] for t in thinking))

    def test_behavioural_flags_come_from_the_harness(self):
        flags = {k: sum(t.flags[k] for t in turns())
                 for k in ("interrupted", "denied", "queued", "error", "revert")}
        self.assertEqual(flags, {"interrupted": 1, "denied": 1, "queued": 1,
                                 "error": 1, "revert": 1})

    def test_writes_are_attributed_to_a_path(self):
        files = {p for t in turns() for p in t.files}
        self.assertEqual(files, {"/tmp/proj-a/scan.py"})


class TestEpisodes(unittest.TestCase):
    def episodes(self):
        return segment(SESSION, turns())

    def test_one_episode_per_typed_prompt(self):
        self.assertEqual(len(self.episodes()), 2)

    def test_the_second_episode_absorbs_the_post_compaction_turns(self):
        last = self.episodes()[-1]
        self.assertEqual(last.prompt_chars, len("adjust the output path"))
        self.assertGreaterEqual(last.assistant_turns, 3)

    def test_a_prompt_seconds_after_the_last_answer_is_marked_fast(self):
        self.assertEqual(self.episodes()[1].signals["fast_open"], 1)


class TestSequences(unittest.TestCase):
    def scans(self):
        return list(scan_sessions(claude_code, root=CORPUS, include_self=True))

    def test_a_repair_candidate_is_found_behaviourally(self):
        parent = next(s for s in self.scans() if s.session_id == SESSION)
        self.assertEqual(len(parent.sequences), 1)
        seq = parent.sequences[0]
        self.assertEqual(seq.episodes, [0, 1])
        self.assertEqual(seq.trigger, "edit_churn,fast_reprompt")

    def test_a_candidate_carries_provenance_for_both_ends(self):
        seq = next(s for s in self.scans()
                   if s.session_id == SESSION).sequences[0]
        self.assertEqual(len(seq.provenance), 2)
        self.assertTrue(all(p.sha256 for p in seq.provenance))


class TestSelfExclusion(unittest.TestCase):
    def test_sessions_under_the_tools_own_directory_are_excluded(self):
        metas = scan(claude_code, root=CORPUS, self_path=Path("/tmp/proj-a"))
        excluded = [m for m in metas if m.excluded]
        self.assertTrue(excluded)
        self.assertTrue(all("working directory" in m.reason for m in excluded))

    def test_exclusion_is_off_when_asked_for(self):
        metas = scan(claude_code, root=CORPUS, self_path=Path("/tmp/proj-a"),
                     include_self=True)
        self.assertEqual([m for m in metas if m.excluded], [])


if __name__ == "__main__":
    unittest.main()
