"""Daily attribution, the position control, and self-normalization."""

import unittest
from types import SimpleNamespace

from corpus_analysis.records import Turn, blank_turn
from corpus_analysis.scan.metrics import (
    daily,
    distances,
    position,
    self_normalized,
    version_mix,
)


def turn(ts: str, role: str = "assistant", *, typed: bool = False,
         out: int = 0, thinking: bool = False, version: str = "1.0",
         model: str = "m") -> Turn:
    t = blank_turn("claude", "/tmp/x.jsonl", 0, "0" * 64, "s", "t", role)
    t["ts"] = ts
    t["version"] = version
    t["model"] = model
    t["usage"]["output_tokens"] = out
    t["flags"]["typed"] = typed
    if thinking:
        t["kinds"]["thinking"] = 1
    return Turn(**t)


def scan(turns, excluded: bool = False, session_id: str = "s"):
    return SimpleNamespace(
        turns=turns,
        session_id=session_id,
        meta=SimpleNamespace(excluded=excluded),
    )


class TestDaily(unittest.TestCase):
    def test_a_session_crossing_midnight_lands_on_both_days(self):
        """Attribution is per turn. A session's start date is not the work's."""
        s = scan([
            turn("2026-01-01T23:50:00Z", out=10),
            turn("2026-01-02T00:10:00Z", out=20),
            turn("2026-01-02T00:20:00Z", out=30),
        ])
        days = daily([s])
        self.assertEqual(list(days), ["2026-01-01", "2026-01-02"])
        self.assertEqual(days["2026-01-01"].out_tokens, 10)
        self.assertEqual(days["2026-01-02"].out_tokens, 50)

    def test_excluded_sessions_do_not_reach_a_day(self):
        self.assertEqual(daily([scan([turn("2026-01-01T00:00:00Z")], excluded=True)]),
                         {})

    def test_a_turn_with_no_timestamp_is_skipped_not_guessed(self):
        self.assertEqual(daily([scan([turn("")])]), {})

    def test_release_is_taken_from_the_turn(self):
        s = scan([turn("2026-01-01T00:00:00Z", version="1.0"),
                  turn("2026-01-01T01:00:00Z", version="1.1"),
                  turn("2026-01-01T02:00:00Z", version="1.1")])
        self.assertEqual(version_mix([s]), {"1.1": 2, "1.0": 1})


class TestDistance(unittest.TestCase):
    def test_distance_counts_turns_since_the_last_typed_prompt(self):
        turns = [
            turn("2026-01-01T00:00:00Z", "user", typed=True),
            turn("2026-01-01T00:00:01Z"),
            turn("2026-01-01T00:00:02Z"),
            turn("2026-01-01T00:00:03Z", "user", typed=True),
            turn("2026-01-01T00:00:04Z"),
        ]
        self.assertEqual([d for d, _ in distances(turns)], [1, 2, 1])

    def test_turns_before_the_first_prompt_have_no_distance(self):
        turns = [turn("2026-01-01T00:00:00Z"),
                 turn("2026-01-01T00:00:01Z", "user", typed=True),
                 turn("2026-01-01T00:00:02Z")]
        self.assertEqual([d for d, _ in distances(turns)], [1])


class TestPositionControl(unittest.TestCase):
    def build(self):
        """Reasoning near a prompt, none far from it, and no change in depth.

        The naive ratio should look like slackening; the control should show
        conversation shape producing it.
        """
        turns = [turn("2026-01-01T00:00:00Z", "user", typed=True)]
        for i in range(1, 4):
            turns.append(turn(f"2026-01-01T00:0{i}:00Z", out=100, thinking=True))
        for i in range(4, 16):
            turns.append(turn(f"2026-01-01T00:{i:02d}:00Z", out=100))
        return scan(turns)

    def test_the_control_is_returned_with_the_ratio(self):
        p = position([self.build()])
        self.assertIsNotNone(p.ratio_median)
        self.assertIsNotNone(p.think_near)
        self.assertIsNotNone(p.think_far)
        self.assertIsNotNone(p.mean_distance_first)
        self.assertIsNotNone(p.mean_distance_last)

    def test_reasoning_clusters_near_fresh_instruction(self):
        p = position([self.build()])
        self.assertGreater(p.think_near, p.think_far)

    def test_late_thirds_sit_farther_from_a_prompt(self):
        p = position([self.build()])
        self.assertGreater(p.mean_distance_last, p.mean_distance_first)

    def test_a_short_session_is_not_measured(self):
        p = position([scan([turn("2026-01-01T00:00:00Z", out=10)] * 4)])
        self.assertEqual(p.sessions_measured, 0)


class TestSelfNormalization(unittest.TestCase):
    def test_no_score_until_the_baseline_has_something_in_it(self):
        self.assertEqual(self_normalized([1.0, 1.0, 1.0])[:3], [None, None, None])

    def test_an_outlier_scores_against_the_corpus_own_history(self):
        scores = self_normalized([1.0, 1.1, 0.9, 1.0, 5.0])
        self.assertIsNotNone(scores[-1])
        self.assertGreater(scores[-1], 3)

    def test_a_steady_series_scores_near_zero(self):
        scores = self_normalized([1.0, 1.1, 0.9, 1.0, 1.05])
        self.assertLess(abs(scores[-1]), 3)


if __name__ == "__main__":
    unittest.main()
