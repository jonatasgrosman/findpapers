"""Tests for filtering and deduplication behavior."""

from findpapers import SearchRunner
from findpapers.models import Paper, Publication
from findpapers.searchers import ArxivSearcher


def test_filter_and_dedupe_merge_rules(monkeypatch):
    def mock_arxiv_iter_search(self):
        papers = [
            Paper(
                title="Short",
                abstract="",
                authors=["A"],
                publication=Publication(title="Journal", category="Journal"),
                publication_date=None,
                urls=set(),
                doi="10.1/abc",
                citations=5,
                keywords={"a"},
            ),
            Paper(
                title="A much longer title",
                abstract="",
                authors=["A"],
                publication=Publication(title="Journal", category="Journal"),
                publication_date=None,
                urls=set(),
                doi="10.1/abc",
                citations=7,
                keywords={"b"},
            ),
            Paper(
                title="Conference paper",
                abstract="",
                authors=["A"],
                publication=Publication(title="Conference", category="Conference Proceedings"),
                publication_date=None,
                urls=set(),
                doi="10.2/xyz",
            ),
        ]

        return iter([papers]), 1, len(papers), len(papers)

    monkeypatch.setattr(ArxivSearcher, "iter_search", mock_arxiv_iter_search)

    runner = SearchRunner(databases=["arxiv"], publication_types=["Journal"])
    results = runner.run()
    metrics = runner.get_metrics()

    assert metrics["total_papers"] == 1

    merged = results[0]
    assert merged.title == "A much longer title"
    assert merged.citations == 7
    assert merged.keywords == {"a", "b"}
