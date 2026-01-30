from abc import ABC

import pytest

from findpapers import SearchRunner, SearchRunnerNotExecutedError
from findpapers.searchers import SearcherBase


def test_searcher_base_is_abc():
    assert issubclass(SearcherBase, ABC)


def test_search_runner_constructs():
    runner = SearchRunner()
    assert runner is not None


def test_getters_raise_before_run():
    runner = SearchRunner()
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.get_results()
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.get_metrics()


def test_exports_raise_before_run():
    runner = SearchRunner()
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.to_json("/tmp/out.json")
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.to_csv("/tmp/out.csv")
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.to_bibtex("/tmp/out.bib")
