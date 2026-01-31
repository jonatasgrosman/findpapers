"""Tests for predatory publication flagging."""

from findpapers import SearchRunner
from findpapers.searchers import ArxivSearcher
from findpapers.utils.predatory_util import POTENTIAL_PREDATORY_JOURNALS_NAMES


def test_predatory_flagging_sets_publication_flag(monkeypatch):
    predatory_name = next(iter(POTENTIAL_PREDATORY_JOURNALS_NAMES))

    def mock_arxiv_search(self):
        return [
            {
                "title": "Paper A",
                "doi": "10.1/abc",
                "publication": {"title": predatory_name},
            },
            {
                "title": "Paper B",
                "doi": "10.2/xyz",
                "publication": {"title": "Legit Journal"},
            },
        ]

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)

    runner = SearchRunner(databases=["arxiv"])
    runner.run()

    results = runner.get_results()
    metrics = runner.get_metrics()

    assert metrics["count.predatory"] == 1
    flagged = [item for item in results if item.get("is_potentially_predatory")]
    assert len(flagged) == 1
    assert flagged[0]["publication"]["is_potentially_predatory"] is True
