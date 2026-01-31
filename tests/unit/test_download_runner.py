"""Tests for DownloadRunner behavior."""

import datetime
from types import SimpleNamespace

import pytest

from findpapers import DownloadRunner, SearchRunnerNotExecutedError
from findpapers.models import Paper


def test_download_runner_requires_run():
    runner = DownloadRunner([], "output")
    with pytest.raises(SearchRunnerNotExecutedError):
        runner.get_metrics()


def test_download_runner_saves_pdf(tmp_path, monkeypatch):
    paper = Paper(
        title="A",
        abstract="",
        authors=["A"],
        publication=None,
        publication_date=datetime.date(2020, 1, 1),
        urls={"https://example.com/file.pdf"},
    )

    def mock_request(self, url, timeout, proxies):
        return SimpleNamespace(
            headers={"content-type": "application/pdf"},
            content=b"pdf",
            url=url,
        )

    monkeypatch.setattr(DownloadRunner, "_request", mock_request)

    runner = DownloadRunner([paper], str(tmp_path))
    runner.run()

    assert (tmp_path / "2020-A.pdf").exists()
    metrics = runner.get_metrics()
    assert metrics["downloaded_papers"] == 1


def test_download_runner_logs_errors(tmp_path, monkeypatch):
    paper = Paper(
        title="A",
        abstract="",
        authors=["A"],
        publication=None,
        publication_date=datetime.date(2020, 1, 1),
        urls={"https://example.com/file.pdf"},
    )

    def mock_request(self, url, timeout, proxies):
        return None

    monkeypatch.setattr(DownloadRunner, "_request", mock_request)

    runner = DownloadRunner([paper], str(tmp_path))
    runner.run()

    error_log = tmp_path / "download_errors.txt"
    assert error_log.exists()
    assert "[FAILED] A" in error_log.read_text()
