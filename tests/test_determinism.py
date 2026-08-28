"""Same corpus in, byte-identical bytes out.

The gate CI runs: scan twice, compare. A measurement that cannot be reproduced
by the machine that produced it cannot be reproduced by a reader either.
"""

import tempfile
import unittest
from pathlib import Path

from corpus_analysis.cli import main
from corpus_analysis.labels import lint

CORPUS = Path(__file__).parent / "fixtures" / "corpus"


def run_twice(*args: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "a", Path(d) / "b"
        for out in (a, b):
            code = main([*args, "--root", str(CORPUS), "--include-self",
                         "--out", str(out)])
            assert code == 0, f"{args} exited {code}"
        return a.read_text(), b.read_text()


class TestDeterminism(unittest.TestCase):
    def test_ingest(self):
        a, b = run_twice("ingest")
        self.assertEqual(a, b)
        self.assertTrue(a.strip(), "the fixture corpus produced no turns")

    def test_episodes(self):
        a, b = run_twice("episodes")
        self.assertEqual(a, b)

    def test_find(self):
        a, b = run_twice("find")
        self.assertEqual(a, b)

    def test_stats(self):
        a, b = run_twice("stats")
        self.assertEqual(a, b)

    def test_report(self):
        a, b = run_twice("report")
        self.assertEqual(a, b)
        lint(a)


class TestEmptyCorpus(unittest.TestCase):
    """A corpus with nothing in it is measured, not crashed on."""

    def test_every_command_succeeds_on_an_empty_root(self):
        with tempfile.TemporaryDirectory() as d:
            empty, out = Path(d) / "corpus", Path(d) / "out"
            empty.mkdir()
            for cmd in ("sessions", "ingest", "episodes", "find", "stats",
                        "report"):
                code = main([cmd, "--root", str(empty), "--out", str(out)])
                self.assertEqual(code, 0, f"{cmd} failed on an empty corpus")


class TestNoTextMode(unittest.TestCase):
    def test_typed_text_can_be_withheld(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "a"
            main(["ingest", "--root", str(CORPUS), "--include-self",
                  "--no-text", "--out", str(out)])
            body = out.read_text()
        self.assertNotIn("adjust the output path", body)
        self.assertIn('"text":""', body)


class TestOperatorErrors(unittest.TestCase):
    def test_missing_lexicon_is_an_exit_two_error(self):
        with tempfile.TemporaryDirectory() as d:
            code = main(["stats", "--root", str(CORPUS),
                         "--lexicon", str(Path(d) / "missing.json")])
        self.assertEqual(code, 2)

    def test_missing_temporal_input_is_an_exit_two_error(self):
        with tempfile.TemporaryDirectory() as d:
            code = main(["temporal", str(Path(d) / "missing.jsonl")])
        self.assertEqual(code, 2)

    def test_invalid_timezone_is_an_exit_two_error(self):
        with tempfile.TemporaryDirectory() as d:
            code = main(["temporal", "--root", d, "--tz", "Not/A_Zone"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
