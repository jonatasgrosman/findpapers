"""Tests for predatory publication flagging."""

from findpapers import SearchRunner
from findpapers.models import Paper, Publication
from findpapers.searchers import ArxivSearcher
from findpapers.utils.predatory_util import POTENTIAL_PREDATORY_JOURNALS_NAMES


def test_predatory_flagging_sets_publication_flag(monkeypatch):
    predatory_name = next(iter(POTENTIAL_PREDATORY_JOURNALS_NAMES))

    def mock_arxiv_iter_search(self):
        papers = [
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

        return iter([papers]), 1, len(papers), len(papers)

    monkeypatch.setattr(ArxivSearcher, "iter_search", mock_arxiv_iter_search)

    runner = SearchRunner(databases=["arxiv"])
    search = runner.run()
    metrics = runner.get_metrics()

    assert metrics["total_papers_from_predatory_publication"] == 1
    flagged = [paper for paper in search.papers if paper.publication.is_potentially_predatory]
    assert len(flagged) == 1
