"""Tests for enrichment runner behavior."""

import time

import pytest

from findpapers import EnrichmentRunner, SearchRunnerNotExecutedError
from findpapers.models import Paper
from findpapers.utils import enrichment_util


def test_enrich_empty_list():
    runner = EnrichmentRunner([])
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["enriched_papers"] == 0


def test_enrichment_runner_requires_run():
    runner = EnrichmentRunner([])
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.get_metrics()


def test_enrich_sequential_timeout(monkeypatch):
    def slow_enrich(self, paper, timeout=None):
        time.sleep(0.02)
        return True

    monkeypatch.setattr(EnrichmentRunner, "_enrich_paper", slow_enrich)

    runner = EnrichmentRunner(
        [
            Paper(
                title="A",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            )
        ],
        timeout=0.0,
    )
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["enriched_papers"] == 0


def test_enrich_parallel_errors(monkeypatch):
    def failing_enrich(self, paper, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(EnrichmentRunner, "_enrich_paper", failing_enrich)

    runner = EnrichmentRunner(
        [
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
        ],
        max_workers=2,
        timeout=1.0,
    )
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["enriched_papers"] == 0


def test_enrich_paper_default_paths(monkeypatch):
    def mock_enrich(urls, timeout=None):
        return enrichment_util.build_paper_from_metadata(
            {"citation_title": "New"},
            "https://example.com",
        )

    paper = Paper(
        title="A",
        abstract="",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls={"https://example.com"},
    )
    runner = EnrichmentRunner([paper])

    monkeypatch.setattr(enrichment_util, "enrich_from_sources", lambda *args, **kwargs: None)
    assert runner._enrich_paper(paper) is False
    monkeypatch.setattr(enrichment_util, "enrich_from_sources", mock_enrich)
    assert runner._enrich_paper(paper) is True
    assert paper.title == "New"
