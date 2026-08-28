"""A report line without a label fails here. That is the contract §3.5 names."""

import unittest

from corpus_analysis.labels import (
    COUNTED,
    DERIVED,
    PROXY,
    Column,
    Figure,
    Report,
    UnlabeledFigure,
    lint,
)


class TestFigure(unittest.TestCase):
    def test_label_must_be_one_of_three(self):
        with self.assertRaises(UnlabeledFigure):
            Figure("x", 1, "measured")

    def test_derived_must_cite_its_rule(self):
        with self.assertRaises(UnlabeledFigure):
            Figure("share", 0.5, DERIVED)
        Figure("share", 0.5, DERIVED, "a / b")  # cited: accepted

    def test_proxy_must_name_its_assumption(self):
        with self.assertRaises(UnlabeledFigure):
            Figure("depth", 12, PROXY)
        Figure("depth", 12, PROXY, "signature length tracks reasoning")


class TestReport(unittest.TestCase):
    def test_prose_may_not_carry_a_bare_number(self):
        r = Report("t")
        with self.assertRaises(UnlabeledFigure):
            r.prose("The corpus holds 12 sessions.")

    def test_prose_may_carry_dates_and_section_refs(self):
        Report("t").prose("Recorded 2026-01-01, per §3.5.")

    def test_a_column_cannot_be_constructed_without_a_label(self):
        with self.assertRaises(UnlabeledFigure):
            Column("day", "measured")
        with self.assertRaises(UnlabeledFigure):
            Column("share", DERIVED)  # no rule cited

    def test_the_linter_catches_a_table_no_builder_produced(self):
        """Hand-written markdown is the only route to an unlabeled column."""
        with self.assertRaises(UnlabeledFigure):
            lint("| day | turns |\n|---|---|\n| a | 3 |\n")

    def test_a_labelled_table_licenses_its_rows(self):
        text = (Report("t")
                .table([Column("day", COUNTED), Column("turns", COUNTED)],
                       [["2026-01-01", 3]])
                .render())
        lint(text)
        self.assertIn("turns [counted]", text)

    def test_vendor_text_cannot_inject_an_unlabelled_markdown_cell(self):
        text = (Report("t")
                .table([Column("vendor", COUNTED), Column("turns", COUNTED)],
                       [[r"value\| 999", 3]])
                .render())
        self.assertIn("&#124; 999", text)
        self.assertNotIn(r"\| 999 |", text)

    def test_linter_rejects_a_row_with_more_cells_than_the_header(self):
        with self.assertRaises(UnlabeledFigure):
            lint("| a [counted] | b [counted] |\n|---|---|\n| x | y | 999 |\n")

    def test_rendered_report_passes_its_own_gate(self):
        text = (Report("t")
                .prose("No numbers here.")
                .figures(Figure("sessions", 4, COUNTED),
                         Figure("share", 0.5, DERIVED, "a / b"))
                .render())
        lint(text)
        self.assertIn("[derived: a / b]", text)


if __name__ == "__main__":
    unittest.main()
