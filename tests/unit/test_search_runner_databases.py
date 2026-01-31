"""Tests for database selection and validation."""

import pytest

from findpapers import SearchRunner


def test_search_runner_raises_for_unknown_database():
    with pytest.raises(ValueError):
        SearchRunner(databases=["unknown"]).run()


def test_search_runner_accepts_multiple_databases():
    runner = SearchRunner(databases=["arxiv", "biorxiv", "ieee", "medrxiv", "pubmed", "scopus"])
    runner.run()
    metrics = runner.get_metrics()
    assert metrics["total_papers_from_arxiv"] == 0
    assert metrics["total_papers_from_biorxiv"] == 0
    assert metrics["total_papers_from_ieee"] == 0
    assert metrics["total_papers_from_medrxiv"] == 0
    assert metrics["total_papers_from_pubmed"] == 0
    assert metrics["total_papers_from_scopus"] == 0


def test_search_runner_defaults_to_all_databases():
    runner = SearchRunner()
    runner.run()
    metrics = runner.get_metrics()

    assert metrics["total_papers_from_arxiv"] == 0
    assert metrics["total_papers_from_biorxiv"] == 0
    assert metrics["total_papers_from_ieee"] == 0
    assert metrics["total_papers_from_medrxiv"] == 0
    assert metrics["total_papers_from_pubmed"] == 0
    assert metrics["total_papers_from_scopus"] == 0
