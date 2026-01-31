"""Tests for enrichment stage behavior."""

import time

from findpapers import SearchRunner
from findpapers.models import Paper
from findpapers.searchers import ArxivSearcher
from findpapers.utils import enrichment_util


def test_enrich_skipped_when_disabled(monkeypatch):
    def mock_arxiv_search(self):
        return [
            Paper(
                title="A",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            )
        ]

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)

    runner = SearchRunner(databases=["arxiv"], enrich=False)
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["count.enriched"] == 0
    assert metrics["errors.enrich"] == 0


def test_enrich_sequential_timeout(monkeypatch):
    def mock_arxiv_search(self):
        return [
            Paper(
                title="A",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            )
        ]

    def slow_enrich(self, paper, timeout=None):
        time.sleep(0.02)
        return True

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)
    monkeypatch.setattr(SearchRunner, "_enrich_paper", slow_enrich)

    runner = SearchRunner(databases=["arxiv"], enrich=True, timeout=0.0)
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["count.enriched"] == 0
    assert metrics["errors.enrich"] >= 1


def test_enrich_parallel_errors(monkeypatch):
    def mock_arxiv_search(self):
        return [
            Paper(
                title="A",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            ),
            Paper(
                title="B",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            ),
        ]

    def failing_enrich(self, paper, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)
    monkeypatch.setattr(SearchRunner, "_enrich_paper", failing_enrich)

    runner = SearchRunner(databases=["arxiv"], enrich=True, max_workers=2, timeout=1.0)
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["errors.enrich"] == 2
    assert metrics["count.enriched"] == 0


def test_enrich_paper_default_paths(monkeypatch):
    def mock_enrich(urls, timeout=None):
        return enrichment_util.build_paper_from_metadata(
            {"citation_title": "New"},
            "https://example.com",
        )

    runner = SearchRunner()
    paper = Paper(
        title="A",
        abstract="",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls={"https://example.com"},
    )

    monkeypatch.setattr(enrichment_util, "enrich_from_sources", lambda *args, **kwargs: None)
    assert runner._enrich_paper(paper) is False
    monkeypatch.setattr(enrichment_util, "enrich_from_sources", mock_enrich)
    assert runner._enrich_paper(paper) is True
    assert paper.title == "New"
