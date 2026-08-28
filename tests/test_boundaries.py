"""The boundaries that make this tool safe to point at a private corpus.

Each check here exercises the code or inspects a committed artifact. Greps over
the source were removed: they missed real cases while reading as coverage.
"""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Committed fixtures are scrubbed too. A fixture freezes source bytes from
#: whatever corpus it was built against, which makes `tests/fixtures/` the
#: shortest path from a private transcript to a public commit.
FIXTURES = ROOT / "tests" / "fixtures"


def ignored(relative: str) -> bool:
    """Whether git would ignore this path. Skips where git cannot answer."""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", relative],
                           capture_output=True, text=True)
    except (FileNotFoundError, OSError) as e:
        raise unittest.SkipTest(f"no git on this platform: {e}") from e
    if r.returncode > 1:
        raise unittest.SkipTest("not a git working tree")
    return r.returncode == 0


class TestPrivateCorpusBoundary(unittest.TestCase):
    """Two adapters read private consumer exports. Neither ships any of one.

    Five checks, deliberately few. A parser for a private format needs its
    fixtures to be provably hand-authored, its output provably unstageable, and
    its diagnostics provably free of source values; anything beyond that is a
    security framework nobody asked for.
    """

    #: Directories holding a synthetic export fixture, one per consumer format.
    EXPORT_FIXTURES = ("chatgpt", "claude_export")

    #: Every identifier in a synthetic export. A real export from either vendor
    #: addresses conversations, messages, and files with uuids, so a pasted
    #: record fails on its first identifier rather than on a reviewer noticing.
    SYNTHETIC_ID = re.compile(
        r"^(conv|node|msg|account|file|doc|proj|refl|user|toolu)-[a-z0-9-]+$")
    UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    #: Keys whose value is an identifier in one export or the other.
    ID_KEYS = frozenset({
        "uuid", "id", "conversation_id", "parent_message_uuid", "current_node",
        "tool_use_id", "file_uuid", "account_uuid",
    })

    def exports(self) -> list[Path]:
        return sorted(p for name in self.EXPORT_FIXTURES
                      for p in (FIXTURES / name).rglob("*.json"))

    def ids_in(self, node) -> list[str]:
        """Every identifier-valued string in a parsed export, at any depth."""
        found: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key in self.ID_KEYS and isinstance(value, str) and value:
                    found.append(value)
                found.extend(self.ids_in(value))
            # A mapping keyed by node id, as one of the two formats uses.
            for key in node:
                if isinstance(key, str) and key.startswith("node-"):
                    found.append(key)
        elif isinstance(node, list):
            for value in node:
                found.extend(self.ids_in(value))
        return found

    def test_the_export_fixtures_are_synthetic(self):
        self.assertTrue(self.exports(), "no export fixture to check")
        for path in self.exports():
            body = path.read_text()
            self.assertIsNone(self.UUID.search(body),
                              f"{path} carries a uuid; a real export is all uuids")
            for value in self.ids_in(json.loads(body)):
                self.assertRegex(value, self.SYNTHETIC_ID, f"in {path}")

    def test_the_release_experiment_fixture_is_inspectably_synthetic(self):
        path = ROOT / "experiments" / "m3a" / "fixture.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["kind"], "manual")
        self.assertEqual(fixture["created_at"], "2026-08-28T00:00:00+00:00")
        self.assertLess(len(fixture["prompt"]), 1000)
        spans = [*fixture["evidence"], *fixture["prior_turns"]]
        for span in spans:
            provenance = span["provenance"]
            self.assertEqual(provenance["adapter"], "manual")
            self.assertEqual(provenance["path"], "synthetic-fixture")
            self.assertEqual(
                span["sha256"],
                hashlib.sha256(span["text"].encode("utf-8")).hexdigest())

    def test_generated_experiment_artifacts_are_not_tracked(self):
        try:
            result = subprocess.run(
                ["git", "-C", str(ROOT), "ls-files"],
                capture_output=True, text=True, check=True)
        except (FileNotFoundError, OSError, subprocess.CalledProcessError) as e:
            raise unittest.SkipTest(f"cannot inspect tracked files: {e}") from e
        forbidden = (
            "experiments/m3a/pilot/",
            "experiments/m3a/pilot-private/",
            "experiments/m3a/raw/",
            "experiments/m3a/label-capture/runs/",
            "experiments/m3a/label-capture/labels-private/",
        )
        leaked = [path for path in result.stdout.splitlines()
                  if path.startswith(forbidden)]
        self.assertEqual(leaked, [])

    def test_diagnostics_echo_no_source_value(self):
        """An unknown discriminator may itself be private text.

        The Claude export adapter therefore counts unknown shapes without
        naming them, and every key it reports is a category this repository
        chose rather than one the corpus supplied.
        """
        from corpus_analysis.adapters import claude_export

        root = FIXTURES / "claude_export"
        for ref in claude_export.sessions(root):
            list(claude_export.turns(ref))
        category = re.compile(r"^[a-z][a-z0-9_]*$")
        report = claude_export.diagnostics()
        self.assertTrue(report["errors"], "no diagnostics to check")
        for group, counts in report.items():
            for key in counts:
                self.assertRegex(key, category, f"in {group}")

    def test_scan_output_paths_are_ignored(self):
        for candidate in ("out/turns.ndjson", "out/turns.jsonl", "scan.ndjson"):
            with self.subTest(path=candidate):
                self.assertTrue(ignored(candidate), f"{candidate} is not ignored")

    def test_output_under_a_tracked_directory_is_refused(self):
        """A warning arrives after the bytes are on disk. This arrives before."""
        from corpus_analysis.cli import _refuse_tracked_out

        for candidate in ("tests/fixtures/leak.ndjson", "docs/leak.ndjson",
                          "examples/leak.ndjson", ".github/leak.ndjson",
                          "experiments/leak.ndjson", "leak.ndjson"):
            with self.subTest(path=candidate), self.assertRaises(ValueError):
                _refuse_tracked_out(ROOT / candidate)
        _refuse_tracked_out(ROOT / "out" / "turns.ndjson")
        _refuse_tracked_out(ROOT / "fixtures" / "case.fixture.json")

    def test_audit_output_uses_the_same_publication_boundary(self):
        from corpus_analysis.publication import refuse_publication_path

        for candidate in ("fixture.json", "experiments/m3a/new-fixture.json",
                          "src/private-output.ndjson", ".", "docs"):
            with self.subTest(path=candidate), self.assertRaises(ValueError):
                refuse_publication_path(ROOT / candidate)
        refuse_publication_path(ROOT / "experiments" / "m3a" / "raw" / "d001.json")
        refuse_publication_path(
            ROOT / "experiments" / "m3a" / "label-capture" / "runs" / "d001")


class TestLexiconsShipEmpty(unittest.TestCase):
    def test_no_word_list_ships(self):
        from corpus_analysis.scan.lexicon import DEFAULT, load

        self.assertEqual(DEFAULT, {})
        self.assertEqual(load(None), {})


if __name__ == "__main__":
    unittest.main()
