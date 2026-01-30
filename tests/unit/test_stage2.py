import pytest

from findpapers import SearchRunner


def test_search_runner_raises_for_unknown_database():
    with pytest.raises(ValueError):
        SearchRunner(databases=["unknown"]).run()


def test_search_runner_accepts_multiple_databases():
    runner = SearchRunner(
        databases=["arxiv", "biorxiv", "ieee", "medrxiv", "pubmed", "scopus"]
    )
    runner.run()
    metrics = runner.get_metrics()
    assert metrics["searchers_total"] == 6
