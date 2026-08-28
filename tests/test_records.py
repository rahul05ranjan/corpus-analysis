"""Record invariants: deterministic serialization, and the observed/label split."""

import hashlib
import unittest

from corpus_analysis.records import (
    Finding,
    Provenance,
    dumps,
    line_digest,
)


class TestDigest(unittest.TestCase):
    def test_excludes_the_line_terminator(self):
        body = b'{"a":1}'
        self.assertEqual(line_digest(body), hashlib.sha256(body).hexdigest())
        self.assertEqual(line_digest(body + b"\n"), line_digest(body))
        self.assertEqual(line_digest(body + b"\r\n"), line_digest(body))


class TestDeterminism(unittest.TestCase):
    def test_key_order_does_not_reach_the_output(self):
        a = dumps({"b": 1, "a": {"z": 1, "y": 2}})
        b = dumps({"a": {"y": 2, "z": 1}, "b": 1})
        self.assertEqual(a, b)

    def test_no_incidental_whitespace(self):
        self.assertEqual(dumps({"a": 1, "b": 2}), '{"a":1,"b":2}')


class TestFinding(unittest.TestCase):
    def prov(self):
        return Provenance("claude", "/tmp/x.jsonl", 0, "0" * 64, "s", "t")

    def test_observed_and_labels_may_not_share_a_key(self):
        f = Finding("f1", observed={"turns": 3}, labels={"turns": "many"},
                    provenance=[self.prov()])
        with self.assertRaises(ValueError):
            f.check()

    def test_disjoint_findings_serialize(self):
        f = Finding("f1", observed={"turns": 3},
                    labels={"failure_type": "unsupported_expansion"},
                    provenance=[self.prov()])
        self.assertIn('"failure_type"', f.to_line())


if __name__ == "__main__":
    unittest.main()
