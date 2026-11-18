"""Fetch and summarize citation data from the public INSPIRE-HEP API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


API_BASE = "https://inspirehep.net/api"
DEFAULT_AUTHOR_BAI = "Federico.De.Lillo.1"
EXCLUDED_INSPIRE_IDS = frozenset({"2803374"})
RECORD_FIELDS = (
    "authors",
    "citeable",
    "citation_count",
    "control_number",
    "publication_info",
    "texkeys",
    "titles",
)


@dataclass(frozen=True)
class Paper:
    bibtex_keys: tuple[str, ...]
    title: str
    citations: int
    authors: tuple[str, ...]
    inspire_id: str
    is_published: bool = False
    is_citeable: bool = True

    @property
    def author_count(self) -> int:
        return len(self.authors)

    @property
    def is_short_author_list(self) -> bool:
        return self.author_count <= 10

    @property
    def is_long_author_list(self) -> bool:
        return not self.is_short_author_list

    @property
    def inspire_url(self) -> str:
        return f"https://inspirehep.net/literature/{self.inspire_id}"


@dataclass(frozen=True)
class WorkMetrics:
    papers: tuple[Paper, ...]

    @property
    def total_citations(self) -> int:
        return sum(paper.citations for paper in self.papers)

    @property
    def h_index(self) -> int:
        return calculate_h_index(paper.citations for paper in self.papers)

    @property
    def mean_citations_per_work(self) -> float:
        if not self.papers:
            return 0.0
        return self.total_citations / len(self.papers)


@dataclass(frozen=True)
class CategorySummary:
    name: str
    papers: tuple[Paper, ...]
    published: WorkMetrics
    unpublished: WorkMetrics
    short_author_list: WorkMetrics
    long_author_list: WorkMetrics

    @property
    def total_citations(self) -> int:
        return WorkMetrics(self.papers).total_citations

    @property
    def h_index(self) -> int:
        return WorkMetrics(self.papers).h_index

    @property
    def mean_citations_per_work(self) -> float:
        return WorkMetrics(self.papers).mean_citations_per_work


def _summarize_category(name: str, papers: Sequence[Paper]) -> CategorySummary:
    category_papers = tuple(papers)
    return CategorySummary(
        name=name,
        papers=category_papers,
        published=WorkMetrics(
            tuple(paper for paper in category_papers if paper.is_published)
        ),
        unpublished=WorkMetrics(
            tuple(paper for paper in category_papers if not paper.is_published)
        ),
        short_author_list=WorkMetrics(
            tuple(paper for paper in category_papers if paper.is_short_author_list)
        ),
        long_author_list=WorkMetrics(
            tuple(paper for paper in category_papers if paper.is_long_author_list)
        ),
    )


@dataclass(frozen=True)
class CitationReport:
    all_papers: tuple[Paper, ...]
    categories: Mapping[str, CategorySummary]
    published: WorkMetrics
    unpublished: WorkMetrics
    short_author_list: WorkMetrics
    long_author_list: WorkMetrics

    @property
    def total_citations(self) -> int:
        return sum(paper.citations for paper in self.all_papers)

    @property
    def h_index(self) -> int:
        return calculate_h_index(paper.citations for paper in self.all_papers)


MetricGroup = Union[WorkMetrics, CategorySummary]


def _format_metric_line(label: str, metrics: MetricGroup) -> str:
    return (
        f"{label}: {len(metrics.papers)} works | {metrics.total_citations} citations | "
        f"h-index {metrics.h_index} | "
        f"mean {metrics.mean_citations_per_work:.2f} citations/work"
    )


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def render_report_exports(
    report: CitationReport,
    generated_at: datetime | None = None,
) -> tuple[str, str]:
    """Render the report as a LaTeX snippet and a plain-text CV summary."""
    updated = (generated_at or datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M %Z")
    sections: list[tuple[str, tuple[tuple[str, MetricGroup], ...]]] = [
        (
            "Overall",
            (
                ("All", WorkMetrics(report.all_papers)),
                ("Published", report.published),
                ("Unpublished", report.unpublished),
                ("Short-author list (10 or fewer)", report.short_author_list),
                ("Long-author list (more than 10)", report.long_author_list),
            ),
        )
    ]
    for name, summary in report.categories.items():
        if not summary.papers:
            continue
        sections.append(
            (
                name,
                (
                    ("All", summary),
                    ("Published", summary.published),
                    ("Unpublished", summary.unpublished),
                    ("Short-author list (10 or fewer)", summary.short_author_list),
                    ("Long-author list (more than 10)", summary.long_author_list),
                ),
            )
        )

    text_lines = [f"Citation metrics (updated {updated})"]
    tex_lines = [
        r"\section*{Citation metrics}",
        f"% Updated {updated}",
        r"\begin{itemize}",
    ]
    for section, metrics_rows in sections:
        text_lines.append(f"\n{section}")
        tex_lines.extend(
            [
                f"  \\item \\textbf{{{_escape_latex(section)}}}",
                r"  \begin{itemize}",
            ]
        )
        for label, metrics in metrics_rows:
            line = _format_metric_line(label, metrics)
            text_lines.append(f"  {line}")
            tex_lines.append(f"    \\item {_escape_latex(line)}")
        tex_lines.append(r"  \end{itemize}")
    tex_lines.append(r"\end{itemize}")
    return "\n".join(tex_lines) + "\n", "\n".join(text_lines) + "\n"


def write_report_exports(
    report: CitationReport,
    output_dir: Union[str, Path] = ".",
) -> tuple[Path, Path]:
    """Write refreshed LaTeX and plain-text metric summaries."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    tex_content, text_content = render_report_exports(report)
    tex_path = destination / "citation_metrics.tex"
    text_path = destination / "citation_metrics.txt"
    tex_path.write_text(tex_content, encoding="utf-8")
    text_path.write_text(text_content, encoding="utf-8")
    return tex_path, text_path


def calculate_h_index(citation_counts: Iterable[int]) -> int:
    """Return h for a set of citation counts."""
    ordered_counts = sorted(citation_counts, reverse=True)
    return sum(1 for rank, citations in enumerate(ordered_counts, start=1) if citations >= rank)


def build_report(
    all_papers: Sequence[Paper],
    categories: Mapping[str, Sequence[str]],
) -> CitationReport:
    """Build metrics for manual categories and automatic author-count categories."""
    all_papers_tuple = tuple(
        paper
        for paper in all_papers
        if paper.is_citeable and paper.inspire_id not in EXCLUDED_INSPIRE_IDS
    )
    papers_by_key: dict[str, Paper] = {}
    for paper in all_papers_tuple:
        for key in paper.bibtex_keys:
            existing = papers_by_key.get(key)
            if existing is not None and existing.inspire_id != paper.inspire_id:
                raise ValueError(f"BibTeX key {key!r} matches multiple INSPIRE records.")
            papers_by_key[key] = paper

    summaries: dict[str, CategorySummary] = {
        "short-author only": _summarize_category(
            "short-author only",
            [paper for paper in all_papers_tuple if paper.is_short_author_list],
        ),
        "long-author only": _summarize_category(
            "long-author only",
            [paper for paper in all_papers_tuple if paper.is_long_author_list],
        ),
    }
    for category, keys in categories.items():
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Category names must be non-empty strings.")
        if category in ("short-author only", "long-author only"):
            raise ValueError(
                f"Category {category!r} is generated automatically from author counts "
                "and must not be listed in the categories mapping."
            )
        if isinstance(keys, (str, bytes)):
            raise TypeError(f"BibTeX keys for category {category!r} must be a sequence of keys.")

        normalized_keys = [key.strip() if isinstance(key, str) else key for key in keys]
        if any(not isinstance(key, str) or not key for key in normalized_keys):
            raise ValueError(f"BibTeX keys for category {category!r} must be non-empty strings.")
        if len(set(normalized_keys)) != len(normalized_keys):
            raise ValueError(f"Category {category!r} contains duplicate BibTeX keys.")

        missing_keys = [key for key in normalized_keys if key not in papers_by_key]
        if missing_keys:
            formatted = ", ".join(repr(key) for key in missing_keys)
            raise ValueError(
                f"BibTeX key(s) not found among this INSPIRE author's works: {formatted}"
            )

        category_papers_list: list[Paper] = []
        seen_inspire_ids: set[str] = set()
        for key in normalized_keys:
            paper = papers_by_key[key]
            if paper.inspire_id in seen_inspire_ids:
                raise ValueError(
                    f"Multiple BibTeX keys in category {category!r} refer to "
                    f"INSPIRE record {paper.inspire_id}."
                )
            category_papers_list.append(paper)
            seen_inspire_ids.add(paper.inspire_id)
        summaries[category] = _summarize_category(category, category_papers_list)

    return CitationReport(
        all_papers=all_papers_tuple,
        categories=summaries,
        published=WorkMetrics(
            tuple(paper for paper in all_papers_tuple if paper.is_published)
        ),
        unpublished=WorkMetrics(
            tuple(paper for paper in all_papers_tuple if not paper.is_published)
        ),
        short_author_list=WorkMetrics(
            tuple(paper for paper in all_papers_tuple if paper.is_short_author_list)
        ),
        long_author_list=WorkMetrics(
            tuple(paper for paper in all_papers_tuple if paper.is_long_author_list)
        ),
    )


class CitationTracker:
    """Load an author's works and compute citation metrics from INSPIRE-HEP."""

    def __init__(
        self,
        author_bai: str = DEFAULT_AUTHOR_BAI,
        timeout: float = 30.0,
    ) -> None:
        if not author_bai.strip():
            raise ValueError("author_bai must be a non-empty INSPIRE BAI.")
        self.author_bai = author_bai.strip()
        self.timeout = timeout

    def fetch_author_papers(self) -> tuple[Paper, ...]:
        """Fetch all works attributed to this INSPIRE author BAI."""
        query = urlencode(
            {
                "q": f"a {self.author_bai}",
                "size": 1000,
                "fields": ",".join(RECORD_FIELDS),
            }
        )
        next_url = f"{API_BASE}/literature/?{query}"
        papers_by_id: dict[str, Paper] = {}

        while next_url:
            payload = self._get_json(next_url)
            hits = payload.get("hits", {}).get("hits")
            if not isinstance(hits, list):
                raise ValueError("Unexpected INSPIRE response: 'hits.hits' is not a list.")

            for record in hits:
                paper = self._parse_paper(record)
                papers_by_id[paper.inspire_id] = paper

            next_url = payload.get("links", {}).get("next", "")
            if next_url and not isinstance(next_url, str):
                raise ValueError("Unexpected INSPIRE response: pagination link is not a string.")

        return tuple(papers_by_id.values())

    def fetch_report(
        self,
        categories: Mapping[str, Sequence[str]],
    ) -> CitationReport:
        """Fetch the author's works and compute overall and category metrics."""
        return build_report(self.fetch_author_papers(), categories)

    def _get_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "citation-tracking/0.1 (personal research tool)",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"INSPIRE API request failed for {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"INSPIRE API returned invalid JSON for {url}.") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected INSPIRE response from {url}: expected a JSON object.")
        return payload

    @staticmethod
    def _parse_paper(record: Any) -> Paper:
        if not isinstance(record, dict):
            raise ValueError("Unexpected INSPIRE response: a literature record is not an object.")
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Unexpected INSPIRE response: literature metadata is missing.")

        inspire_id = record.get("id") or metadata.get("control_number")
        citations = metadata.get("citation_count")
        if inspire_id is None or not isinstance(citations, int) or isinstance(citations, bool):
            raise ValueError("INSPIRE record is missing its ID or citation count.")
        citeable = metadata.get("citeable", False)
        if not isinstance(citeable, bool):
            raise ValueError("Unexpected INSPIRE response: citeable is not a boolean.")

        titles = metadata.get("titles", [])
        title = next(
            (
                item["title"]
                for item in titles
                if isinstance(item, dict) and isinstance(item.get("title"), str)
            ),
            "",
        )
        authors_data = metadata.get("authors", [])
        if not isinstance(authors_data, list):
            raise ValueError("Unexpected INSPIRE response: authors is not a list.")

        keys_data = metadata.get("texkeys", [])
        if not isinstance(keys_data, list):
            raise ValueError("Unexpected INSPIRE response: texkeys is not a list.")
        publication_info = metadata.get("publication_info", [])
        if not isinstance(publication_info, list):
            raise ValueError("Unexpected INSPIRE response: publication_info is not a list.")

        return Paper(
            bibtex_keys=tuple(key for key in keys_data if isinstance(key, str)),
            title=title,
            citations=citations,
            authors=tuple(
                author["full_name"]
                for author in authors_data
                if isinstance(author, dict) and isinstance(author.get("full_name"), str)
            ),
            inspire_id=str(inspire_id),
            is_published=bool(publication_info),
            is_citeable=citeable,
        )
