import unittest
from tempfile import TemporaryDirectory

from citation_tracking import (
    CitationTracker,
    Paper,
    build_report,
    calculate_h_index,
    write_report_exports,
)


class CitationTrackingTests(unittest.TestCase):
    def setUp(self):
        self.papers = (
            Paper(("Paper:Short",), "Short paper", 10, ("A", "B"), "1", True),
            Paper(
                ("Paper:Long",),
                "Long paper",
                4,
                tuple(str(i) for i in range(11)),
                "2",
                False,
            ),
            Paper(("Paper:Other",), "Other paper", 1, ("A",), "3", True),
        )

    def test_h_index_uses_sorted_citation_thresholds(self):
        self.assertEqual(calculate_h_index([10, 4, 1]), 2)

    def test_author_list_cutoff_includes_exactly_ten_authors_as_short(self):
        self.assertTrue(self.papers[0].is_short_author_list)
        self.assertFalse(self.papers[0].is_long_author_list)
        self.assertFalse(self.papers[1].is_short_author_list)
        self.assertTrue(self.papers[1].is_long_author_list)
        ten_authors = Paper(
            ("Paper:Ten",),
            "Ten-author paper",
            0,
            tuple(str(i) for i in range(10)),
            "4",
        )
        self.assertTrue(ten_authors.is_short_author_list)
        self.assertFalse(ten_authors.is_long_author_list)

    def test_author_list_metrics_are_automatically_grouped(self):
        report = build_report(
            self.papers,
            {"short + long where contributed": ["Paper:Short", "Paper:Long"]},
        )
        category = report.categories["short + long where contributed"]

        self.assertEqual(report.short_author_list.total_citations, 11)
        self.assertEqual(report.long_author_list.total_citations, 4)
        self.assertEqual(category.short_author_list.total_citations, 10)
        self.assertEqual(category.long_author_list.total_citations, 4)

    def test_categories_summarize_only_listed_keys(self):
        report = build_report(
            self.papers,
            {
                "short + long where contributed": ["Paper:Short", "Paper:Long"],
            },
        )

        self.assertEqual(report.total_citations, 15)
        self.assertEqual(
            report.categories["short + long where contributed"].total_citations,
            14,
        )

    def test_short_and_long_author_categories_are_generated(self):
        report = build_report(self.papers, {})

        short = report.categories["short-author only"]
        long = report.categories["long-author only"]
        self.assertEqual(len(short.papers), 2)
        self.assertEqual(short.total_citations, 11)
        self.assertEqual(short.h_index, 1)
        self.assertEqual(len(long.papers), 1)
        self.assertEqual(long.total_citations, 4)
        self.assertEqual(long.h_index, 1)
        self.assertEqual(len(short.published.papers), 2)
        self.assertEqual(len(long.unpublished.papers), 1)

    def test_generated_author_categories_cannot_be_overridden_manually(self):
        with self.assertRaisesRegex(ValueError, "generated automatically"):
            build_report(self.papers, {"short-author only": []})

    def test_publication_metrics_are_split_overall_and_by_category(self):
        report = build_report(
            self.papers,
            {"short + long where contributed": ["Paper:Short", "Paper:Long"]},
        )
        category = report.categories["short + long where contributed"]

        self.assertEqual(report.published.total_citations, 11)
        self.assertEqual(report.unpublished.total_citations, 4)
        self.assertEqual(report.published.h_index, 1)
        self.assertEqual(report.unpublished.h_index, 1)
        self.assertEqual(category.published.total_citations, 10)
        self.assertEqual(category.unpublished.total_citations, 4)

    def test_inspire_publication_info_sets_publication_status(self):
        published_record = {
            "id": "10",
            "metadata": {
                "citation_count": 3,
                "authors": [],
                "publication_info": [{"journal_title": "Example Journal"}],
            },
        }
        unpublished_record = {
            "id": "11",
            "metadata": {"citation_count": 0, "authors": []},
        }

        published = CitationTracker._parse_paper(published_record)
        unpublished = CitationTracker._parse_paper(unpublished_record)

        self.assertTrue(published.is_published)
        self.assertFalse(unpublished.is_published)

    def test_non_citeable_and_excluded_records_do_not_enter_metrics(self):
        non_citeable = Paper(
            ("Paper:NonCiteable",),
            "Non-citeable record",
            1000,
            ("A",),
            "4",
            is_citeable=False,
        )
        excluded_record = Paper(
            ("DeLillo:2024xhz",),
            "Thesis record",
            1000,
            ("A",),
            "2803374",
        )
        report = build_report(self.papers + (non_citeable, excluded_record), {})

        self.assertEqual(len(report.all_papers), 3)
        self.assertEqual(report.total_citations, 15)
        self.assertNotIn(non_citeable, report.all_papers)
        self.assertNotIn(excluded_record, report.all_papers)

    def test_inspire_citeable_flag_defaults_to_false_when_absent(self):
        record = {
            "id": "12",
            "metadata": {"citation_count": 0, "authors": []},
        }
        self.assertFalse(CitationTracker._parse_paper(record).is_citeable)
        record["metadata"]["citeable"] = True
        self.assertTrue(CitationTracker._parse_paper(record).is_citeable)

    def test_unknown_bibtex_key_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Paper:Missing"):
            build_report(self.papers, {"category": ["Paper:Missing"]})

    def test_exports_write_cv_ready_latex_and_text(self):
        report = build_report(
            self.papers,
            {
                "Empty category": [],
                "Research & methods": ["Paper:Short"],
            },
        )
        with TemporaryDirectory() as output_dir:
            tex_path, text_path = write_report_exports(report, output_dir)
            tex = tex_path.read_text(encoding="utf-8")
            text = text_path.read_text(encoding="utf-8")

        self.assertIn(r"\textbf{Research \& methods}", tex)
        self.assertIn("Short-author list (10 or fewer)", tex)
        self.assertIn("Research & methods", text)
        self.assertNotIn("Empty category", tex)
        self.assertNotIn("Empty category", text)
        self.assertIn("10 citations", text)


if __name__ == "__main__":
    unittest.main()
