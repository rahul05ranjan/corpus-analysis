"""Temporal buckets are arithmetic; rendering is order-independent and labelled.

Fixtures are hand-built dicts in the `Turn.to_dict()` shape, which is also the
shape `ingest` writes — the aggregation sees no other."""

import unittest

from corpus_analysis.labels import lint
from corpus_analysis.records import Turn, blank_turn
from corpus_analysis.scan.temporal import aggregate, temporal_report


def turn(ts: str, role: str = "user", *, typed: bool = True, text: str = "hi",
         adapter: str = "alpha", model: str = "", out: int = 0,
         tools: int = 0, flag: str = "") -> dict:
    t = blank_turn(adapter, "/tmp/x.jsonl", 0, "0" * 64, "s", "t", role)
    t["ts"] = ts
    t["model"] = model
    t["text"] = text
    t["flags"]["typed"] = typed
    t["usage"]["output_tokens"] = out
    t["kinds"]["tool_use"] = tools
    if flag:
        t["flags"][flag] = True
    return Turn(**t).to_dict()


class TestAggregate(unittest.TestCase):
    def test_utc_is_the_default_clock(self):
        agg = aggregate([turn("2026-01-03T07:30:00Z")])
        self.assertEqual(agg.weekday_hour, {(5, 7): 1})   # Saturday 07 UTC
        self.assertEqual(agg.month_weekend, {"2026-01": 1})
        self.assertEqual(agg.month_night, {})

    def test_the_zone_moves_the_bucket_not_the_record(self):
        """07:30Z on a Saturday is Friday 23:30 in Los Angeles: weekday flips,
        weekend leaves, night arrives. Same record, declared zone."""
        agg = aggregate([turn("2026-01-03T07:30:00Z")], tz="America/Los_Angeles")
        self.assertEqual(agg.weekday_hour, {(4, 23): 1})  # Friday 23 local
        self.assertEqual(agg.month_weekend, {})
        self.assertEqual(agg.month_night, {"2026-01": 1})

    def test_night_window_boundaries(self):
        hours = ["21:59", "22:00", "04:59", "05:00"]
        agg = aggregate([turn(f"2026-01-05T{h}:00Z") for h in hours])
        self.assertEqual(agg.month_night["2026-01"], 2)

    def test_no_timestamp_reaches_no_bucket(self):
        agg = aggregate([turn(""), turn("not-a-time")])
        self.assertEqual(agg.turns_without_ts, 2)
        self.assertEqual(agg.prompts, 0)

    def test_months_include_the_gap(self):
        agg = aggregate([turn("2025-11-01T00:00:00Z"),
                         turn("2026-01-01T00:00:00Z")])
        self.assertEqual(agg.months(), ["2025-11", "2025-12", "2026-01"])

    def test_sources_and_friction_are_counted_per_month(self):
        agg = aggregate([
            turn("2026-01-01T00:00:00Z", adapter="alpha"),
            turn("2026-01-02T00:00:00Z", adapter="beta"),
            turn("2026-01-02T01:00:00Z", role="assistant", typed=False,
                 model="m1", out=100, tools=3, flag="error"),
        ])
        self.assertEqual(agg.source_month[("alpha", "2026-01")], 1)
        self.assertEqual(agg.source_month[("beta", "2026-01")], 1)
        self.assertEqual(agg.month_flags[("2026-01", "error")], 1)
        self.assertEqual(agg.month_out_tokens["2026-01"], 100)
        self.assertEqual(agg.month_tools["2026-01"], 3)


class TestRender(unittest.TestCase):
    def fixture(self):
        return [
            turn("2026-01-01T03:00:00Z", text="short"),
            turn("2026-01-01T03:10:00Z", text="a much longer prompt body"),
            turn("2026-02-08T15:00:00Z", adapter="beta"),
            turn("2026-02-08T15:05:00Z", role="assistant", typed=False,
                 model="m1", out=50, flag="revert"),
            turn(""),
        ]

    def test_report_is_lintable_and_places_every_prompt(self):
        text = temporal_report(aggregate(self.fixture()))
        lint(text)  # render() lints; asserting on the artifact anyway
        self.assertIn("typed prompts placed on the clock 3 [counted]", text)
        self.assertIn("turns without a convertible timestamp 1 [counted]", text)
        self.assertIn("| alpha |", text)
        self.assertIn("| beta |", text)

    def test_reading_order_does_not_reach_the_bytes(self):
        turns = self.fixture()
        a = temporal_report(aggregate(turns))
        b = temporal_report(aggregate(list(reversed(turns))))
        self.assertEqual(a, b)

    def test_a_model_under_the_floor_is_omitted(self):
        text = temporal_report(aggregate(self.fixture()))
        self.assertNotIn("| m1 |", text)

    def test_streak_and_heaviest_days(self):
        agg = aggregate([
            turn("2026-01-01T00:00:00Z"),
            turn("2026-01-02T00:00:00Z"),
            turn("2026-01-02T01:00:00Z"),
            turn("2026-01-03T00:00:00Z"),
            turn("2026-01-05T00:00:00Z"),
        ])
        text = temporal_report(agg)
        self.assertIn("longest run of consecutive active days 3 [counted]", text)
        self.assertIn("| 2026-01-02 | 2 | alpha |", text)

    def test_empty_corpus_still_renders(self):
        text = temporal_report(aggregate([]))
        lint(text)
        self.assertIn("nothing to plot", text)


if __name__ == "__main__":
    unittest.main()
