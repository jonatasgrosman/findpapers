"""Tests for fetch stage behavior and error handling."""

from findpapers import SearchRunner
from findpapers.models import Paper
from findpapers.searchers import ArxivSearcher, PubmedSearcher


def test_fetch_stage_collects_results_and_keeps_partial_on_error(monkeypatch):
    def mock_arxiv_search(self):
        return [
            Paper(
                title="Paper 1",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            ),
            Paper(
                title="Paper 2",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls=set(),
            ),
        ]

    def mock_pubmed_search(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)
    monkeypatch.setattr(PubmedSearcher, "search", mock_pubmed_search)

    runner = SearchRunner(databases=["arxiv", "pubmed"])
    results = runner.run()

    metrics = runner.get_metrics()
    assert metrics["total_papers"] == 2
    assert metrics["total_papers_from_arxiv"] == 2
    assert metrics["total_papers_from_pubmed"] == 0
    assert len(results) == 2


def test_fetch_stage_keeps_doi_url_from_paper(monkeypatch):
    def mock_arxiv_search(self):
        return [
            Paper(
                title="Paper 1",
                abstract="",
                authors=["A"],
                publication=None,
                publication_date=None,
                urls={"https://example.com"},
                doi="10.1/abc",
            )
        ]

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)

    runner = SearchRunner(databases=["arxiv"])
    results = runner.run()
    assert "https://doi.org/10.1/abc" in results[0].urls
