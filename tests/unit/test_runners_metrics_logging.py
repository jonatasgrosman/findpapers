"""Tests for Stage 8: Metrics, logging & verbose output."""

import logging

from findpapers import SearchRunner
from findpapers.runners.download_runner import DownloadRunner
from findpapers.runners.enrichment_runner import EnrichmentRunner


class TestSearchRunnerMetrics:
    """Test SearchRunner metrics and logging."""

    def test_metrics_include_runtime_and_counts(self):
        """Verify metrics include runtime and count-related keys."""
        runner = SearchRunner()
        runner.run()
        metrics = runner.get_metrics()

        expected_keys = {
            "total_papers",
            "runtime_in_seconds",
            "total_papers_from_predatory_publication",
        }

        assert all(key in metrics for key in expected_keys), (
            f"Missing metric keys. Expected: {expected_keys}, Got: {set(metrics.keys())}"
        )

    def test_metrics_are_numeric_only(self):
        """Verify all metrics are numeric (int or float)."""
        runner = SearchRunner()
        runner.run()
        metrics = runner.get_metrics()

        for key, value in metrics.items():
            assert isinstance(value, (int, float)), (
                f"Metric '{key}' has non-numeric value: {value} ({type(value).__name__})"
            )

    def test_per_searcher_metrics_present(self):
        """Verify per-searcher metrics are recorded."""
        runner = SearchRunner(databases=["arxiv", "biorxiv"])
        runner.run()
        metrics = runner.get_metrics()

        assert "total_papers_from_arxiv" in metrics
        assert "total_papers_from_biorxiv" in metrics
        assert isinstance(metrics["total_papers_from_arxiv"], (int, float))
        assert isinstance(metrics["total_papers_from_biorxiv"], (int, float))

    def test_verbose_logs_configuration(self, caplog):
        """Verify verbose mode logs configuration."""
        runner = SearchRunner(databases=["arxiv"])
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "SearchRunner Configuration" in log_text
        assert "arxiv" in log_text.lower()

    def test_verbose_logs_per_stage_summary(self, caplog):
        """Verify verbose mode logs per-stage summary."""
        runner = SearchRunner()
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "Fetch complete" in log_text or "papers" in log_text.lower()

    def test_verbose_logs_final_summary(self, caplog):
        """Verify verbose mode logs final summary."""
        runner = SearchRunner()
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "Final Summary" in log_text or "Total papers" in log_text

    def test_non_verbose_no_extra_logs(self, caplog):
        """Verify non-verbose mode doesn't emit extra logs."""
        runner = SearchRunner()
        with caplog.at_level(logging.INFO):
            runner.run(verbose=False)

        log_text = caplog.text
        # Should not contain "SearchRunner Configuration" unless explicitly logged
        assert "SearchRunner Configuration" not in log_text


class TestEnrichmentRunnerMetrics:
    """Test EnrichmentRunner metrics and logging."""

    def test_enrichment_metrics_include_timing(self):
        """Verify enrichment metrics include runtime."""
        runner = EnrichmentRunner([])
        runner.run()
        metrics = runner.get_metrics()

        expected_keys = {
            "total_papers",
            "runtime_in_seconds",
            "enriched_papers",
        }

        assert all(key in metrics for key in expected_keys)

    def test_enrichment_metrics_numeric_only(self):
        """Verify all enrichment metrics are numeric."""
        runner = EnrichmentRunner([])
        runner.run()
        metrics = runner.get_metrics()

        for key, value in metrics.items():
            assert isinstance(value, (int, float))

    def test_enrichment_verbose_logs_configuration(self, caplog):
        """Verify enrichment verbose mode logs configuration."""
        runner = EnrichmentRunner([])
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "EnrichmentRunner Configuration" in log_text

    def test_enrichment_verbose_logs_summary(self, caplog):
        """Verify enrichment verbose mode logs summary."""
        runner = EnrichmentRunner([])
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "Enrichment Summary" in log_text


class TestDownloadRunnerMetrics:
    """Test DownloadRunner metrics and logging."""

    def test_download_metrics_include_timing(self, tmp_path):
        """Verify download metrics include runtime."""
        runner = DownloadRunner([], str(tmp_path))
        runner.run()
        metrics = runner.get_metrics()

        expected_keys = {
            "total_papers",
            "runtime_in_seconds",
            "downloaded_papers",
        }

        assert all(key in metrics for key in expected_keys)

    def test_download_metrics_numeric_only(self, tmp_path):
        """Verify all download metrics are numeric."""
        runner = DownloadRunner([], str(tmp_path))
        runner.run()
        metrics = runner.get_metrics()

        for key, value in metrics.items():
            assert isinstance(value, (int, float))

    def test_download_verbose_logs_configuration(self, tmp_path, caplog):
        """Verify download verbose mode logs configuration."""
        runner = DownloadRunner([], str(tmp_path))
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "DownloadRunner Configuration" in log_text

    def test_download_verbose_logs_summary(self, tmp_path, caplog):
        """Verify download verbose mode logs summary."""
        runner = DownloadRunner([], str(tmp_path))
        with caplog.at_level(logging.INFO):
            runner.run(verbose=True)

        log_text = caplog.text
        assert "Download Summary" in log_text
