"""Tests for SearchRunner run state and metrics types."""

from findpapers import SearchRunner


def test_run_sets_executed_state():
    runner = SearchRunner()
    search = runner.run()
    assert search.papers == []
    assert isinstance(runner.get_metrics(), dict)


def test_metrics_numeric_only():
    runner = SearchRunner()
    runner.run()
    metrics = runner.get_metrics()
    assert all(isinstance(value, (int, float)) for value in metrics.values())
