"""Tests for SearchRunner export helpers."""

from __future__ import annotations

import csv
import json
from datetime import date

from findpapers import SearchRunner
from findpapers.models import Paper, Publication


def _build_paper() -> Paper:
    publication = Publication(
        title="Journal of Tests",
        publisher="UnitTest Press",
        category="Journal",
        subject_areas={"Testing"},
        is_potentially_predatory=False,
    )
    return Paper(
        title="A Test Paper",
        abstract="Abstract",
        authors=["Doe, Jane", "Roe, John"],
        publication=publication,
        publication_date=date(2024, 1, 2),
        urls={"https://example.org"},
        doi="10.1234/example",
        citations=5,
        keywords={"testing", "python"},
        comments="Comment",
        number_of_pages=10,
        pages="1-10",
        databases={"arxiv"},
    )


def test_to_json_exports_schema(tmp_path) -> None:
    runner = SearchRunner()
    search = runner.run()

    output_path = tmp_path / "results.json"
    search.to_json(str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert set(payload.keys()) == {"metadata", "papers", "metrics"}
    assert payload["papers"] == []
    assert isinstance(payload["metrics"], dict)

    metadata = payload["metadata"]
    assert set(metadata.keys()) == {
        "query",
        "databases",
        "limits",
        "timeout",
        "timestamp",
        "version",
        "runtime_seconds",
    }
    assert isinstance(metadata["timestamp"], str)


def test_to_csv_column_order(tmp_path) -> None:
    runner = SearchRunner()
    search = runner.run()
    search.papers = [_build_paper()]

    output_path = tmp_path / "results.csv"
    search.to_csv(str(output_path))

    with output_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)

    assert header == [
        "title",
        "abstract",
        "authors",
        "publication_date",
        "urls",
        "doi",
        "citations",
        "keywords",
        "comments",
        "number_of_pages",
        "pages",
        "databases",
        "publication_title",
        "publication_isbn",
        "publication_issn",
        "publication_publisher",
        "publication_category",
        "publication_cite_score",
        "publication_sjr",
        "publication_snip",
        "publication_subject_areas",
        "publication_is_potentially_predatory",
    ]


def test_to_bibtex_exports_entries(tmp_path) -> None:
    runner = SearchRunner()
    search = runner.run()
    search.papers = [_build_paper()]

    output_path = tmp_path / "results.bib"
    search.to_bibtex(str(output_path))

    content = output_path.read_text(encoding="utf-8")

    assert "@article{" in content
    assert "title = {A Test Paper}" in content
    assert "author = {Doe, Jane and Roe, John}" in content
    assert "year = {2024}" in content
