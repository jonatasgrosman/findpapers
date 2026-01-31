"""Tests for predatory publication flagging."""

from findpapers import SearchRunner
from findpapers.models import Paper, Publication
from findpapers.searchers import ArxivSearcher
from findpapers.utils.predatory_util import POTENTIAL_PREDATORY_JOURNALS_NAMES


def test_predatory_flagging_sets_publication_flag(monkeypatch):
    predatory_name = next(iter(POTENTIAL_PREDATORY_JOURNALS_NAMES))

    def mock_arxiv_search(self):
        return [
            Paper(
                title="Paper A",
                abstract="",
                authors=["A"],
                publication=Publication(title=predatory_name),
                publication_date=None,
                urls=set(),
                doi="10.1/abc",
            ),
            Paper(
                title="Paper B",
                abstract="",
                authors=["A"],
                publication=Publication(title="Legit Journal"),
                publication_date=None,
                urls=set(),
                doi="10.2/xyz",
            ),
        ]

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)

    runner = SearchRunner(databases=["arxiv"])
    runner.run()

    results = runner.get_results()
    metrics = runner.get_metrics()

    assert metrics["count.predatory"] == 1
    flagged = [paper for paper in results if paper.publication.is_potentially_predatory]
    assert len(flagged) == 1
