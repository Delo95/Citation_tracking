# Citation tracking

A small, dependency-free Python interface for fetching citation information
from the public INSPIRE-HEP API and summarizing works grouped by BibTeX key.

## Get started

1. Open `citation_tracking.ipynb` in Jupyter.
2. Edit the lists in `categories.json`. Each list should contain the exact
   BibTeX entry keys used by INSPIRE, for example `"Bruno:2026rwf"`.
3. Run the notebook cells. It fetches the author's works, prints an overall
   summary and metrics for each category, then writes `citation_metrics.tex`
   and `citation_metrics.txt` in the notebook's current directory.

The configured author BAI, `Federico.De.Lillo.1`, corresponds to the INSPIRE
author record [1835906](https://inspirehep.net/authors/1835906). Change
`author_bai` in the JSON file to use a different author.

## Metrics and category behavior

- Overall metrics use all works returned for the configured author BAI.
- Record `2803374` is always excluded, and records INSPIRE marks non-citeable
  are omitted from metric calculations and exports.
- The `"short-author only"` and `"long-author only"` categories are generated
  automatically from INSPIRE author counts; do not add them to `categories.json`.
- Other configured categories (such as `"short + long where contributed"`)
  contain exact BibTeX-key sets and may overlap; their totals are calculated
  independently.
- Per-work output includes current INSPIRE citation counts and author counts;
  10 or fewer authors is short-author, and more than 10 is long-author. The
  notebook automatically groups and lists all works using the author count
  returned by INSPIRE.
- The h-index for a category is calculated using only works in that category.
- Overall and per-category statistics are also split into published and
  unpublished works. A work is considered published when INSPIRE lists a
  non-empty `publication_info` field; otherwise it is unpublished.
- This fetches a live snapshot; it does not yet save historical snapshots.
- The custom categories remain curated through BibTeX-key lists; author-list
  groups are inferred automatically and do not need to be added to the JSON.
- The LaTeX and text exports contain the overall metrics and every category's
  metrics, including published/unpublished and short-/long-author splits.
  Empty custom categories are omitted from the CV exports. Running the notebook
  again refreshes these files.

The implementation uses only the Python standard library. The INSPIRE API must
be reachable when the notebook runs.

## Python API

```python
from citation_tracking import CitationTracker, write_report_exports

categories = {
    "short + long where contributed": ["Example:MyPaper"],
}

report = CitationTracker().fetch_report(categories)
print(report.total_citations, report.h_index)
print(report.categories["short-author only"].h_index)  # Generated automatically
print(report.published.h_index, report.unpublished.h_index)
print(report.categories["short-author only"].published.total_citations)
print(report.short_author_list.total_citations)
for paper in report.long_author_list.papers:
    print(paper.author_count, paper.title, paper.inspire_url)

tex_path, text_path = write_report_exports(report, ".")
```

Run the focused tests from this directory with:

```bash
python -m unittest discover -s tests
```
