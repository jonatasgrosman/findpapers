"""Unit tests for DownloadRunner."""

from __future__ import annotations

import logging
import os
from datetime import date
from unittest.mock import MagicMock, patch

from curl_cffi.requests.errors import RequestsError as _CurlError

from findpapers.core.author import Author
from findpapers.core.paper import Paper
from findpapers.runners.download_runner import DownloadRunner


class TestDownloadRunnerInit:
    """Tests for DownloadRunner initialisation."""

    def test_init_stores_config(self, make_paper):
        """Constructor stores configuration without executing."""
        papers = [make_paper()]
        runner = DownloadRunner(papers=papers, output_directory="/tmp/out")
        assert runner._output_directory == "/tmp/out"


class TestDownloadRunnerRun:
    """Tests for the run() method."""

    def test_run_with_empty_list(self, tmp_path):
        """run() with empty paper list completes successfully."""
        runner = DownloadRunner(papers=[], output_directory=str(tmp_path))
        metrics = runner.run()
        assert metrics["total_papers"] == 0
        assert metrics["downloaded_papers"] == 0

    def test_metrics_populated_after_run(self, make_paper, tmp_path):
        """Metrics contain expected keys after run()."""
        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(False, [], None)):
            metrics = runner.run()
        assert "total_papers" in metrics
        assert "downloaded_papers" in metrics
        assert "runtime_in_seconds" in metrics

    def test_creates_output_directory(self, tmp_path):
        """run() creates the output directory when it does not exist."""
        out_dir = str(tmp_path / "nested" / "output")
        runner = DownloadRunner(papers=[], output_directory=out_dir)
        runner.run()
        assert os.path.isdir(out_dir)

    def test_download_success_increments_count(self, make_paper, tmp_path):
        """Successful download increments downloaded_papers metric."""
        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(True, ["http://url"], None)):
            metrics = runner.run()
        assert metrics["downloaded_papers"] == 1

    def test_download_failure_logged(self, make_paper, tmp_path):
        """Failed download leaves downloaded_papers at 0."""
        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(False, ["http://url"], None)):
            metrics = runner.run()
        assert metrics["downloaded_papers"] == 0
        # Log file must exist with a [FAILED] entry
        log_file = os.path.join(str(tmp_path), "download_log.txt")
        assert os.path.exists(log_file)
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "[FAILED]" in content

    def test_download_success_logged(self, make_paper, tmp_path):
        """Successful download is logged with [OK] prefix."""
        paper = make_paper(title="Good Paper")
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(True, ["http://ok-url"], None)):
            runner.run()
        log_file = os.path.join(str(tmp_path), "download_log.txt")
        assert os.path.exists(log_file)
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "[OK] Good Paper" in content
        assert "http://ok-url" in content

    def test_log_contains_both_success_and_failure(self, make_paper, tmp_path):
        """Download log contains both [OK] and [FAILED] entries."""
        papers = [make_paper(title="Success Paper"), make_paper(title="Failure Paper")]
        runner = DownloadRunner(papers=papers, output_directory=str(tmp_path))
        results = iter([(True, ["http://ok"], None), (False, ["http://fail"], None)])
        with patch.object(runner, "_download_paper", side_effect=lambda *a, **kw: next(results)):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "[OK] Success Paper" in content
        assert "[FAILED] Failure Paper" in content

    def test_log_urls_are_indented(self, make_paper, tmp_path):
        """URLs in the log are indented with '  -> ' prefix."""
        paper = make_paper(title="Indented URL Paper")
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(
            runner, "_download_paper", return_value=(True, ["http://indented-url"], None)
        ):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "  -> http://indented-url" in content

    def test_log_session_header_contains_separator(self, tmp_path):
        """Log header uses '=' separator lines."""
        runner = DownloadRunner(papers=[], output_directory=str(tmp_path))
        runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "=" * 80 in content
        assert "Download session started:" in content

    def test_log_failure_no_urls_uses_placeholder(self, make_paper, tmp_path):
        """Failure with no URLs logs a '(no URLs available)' placeholder."""
        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        # Raising an exception triggers the error path which calls _log_download_error([]).
        with patch.object(runner, "_download_paper", side_effect=RuntimeError("boom")):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "(no URLs available)" in content

    def test_log_success_no_urls_uses_skipped_placeholder(self, make_paper, tmp_path):
        """Success with no URLs (PDF already existed) logs an 'already downloaded' note."""
        runner = DownloadRunner(
            papers=[make_paper(title="Cached Paper")], output_directory=str(tmp_path)
        )
        with patch.object(runner, "_download_paper", return_value=(True, [], None)):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "[OK] Cached Paper" in content
        assert "(already downloaded, skipped)" in content

    def test_log_shows_paper_page_url_for_failure(self, make_paper, tmp_path):
        """Failed download log includes a 'Page:' line with the paper's URL."""
        paper = make_paper(title="Page URL Failure", url="http://example.com/paper-page")
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(
            runner, "_download_paper", return_value=(False, ["http://pdf-url"], None)
        ):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "  Page: http://example.com/paper-page" in content
        assert "  -> http://pdf-url" in content

    def test_log_shows_paper_page_url_for_success(self, make_paper, tmp_path):
        """Successful download log includes a 'Page:' line with the paper's URL."""
        paper = make_paper(title="Page URL Success", url="http://example.com/landing")
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(True, ["http://ok-pdf"], None)):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "  Page: http://example.com/landing" in content

    def test_resolved_landing_url_takes_priority_over_paper_url(self, make_paper, tmp_path):
        """resolved_landing_url (the publisher page after DOI redirect) is preferred
        over paper.url (e.g. a Semantic Scholar page) for the 'Page:' log line.
        """
        paper = make_paper(
            title="DOI Redirect Priority",
            url="https://www.semanticscholar.org/paper/abc123",
        )
        publisher_url = "https://ieeexplore.ieee.org/document/11271154"
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(
            runner,
            "_download_paper",
            return_value=(
                False,
                ["https://ieeexplore.ieee.org/ielam/63/11411904/11271154-aam.pdf"],
                publisher_url,
            ),
        ):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert f"  Page: {publisher_url}" in content
        assert "semanticscholar.org" not in content

        """When paper.url is None but doi is set, the Page: line uses the doi.org URL."""
        paper = Paper(
            title="DOI Only Paper",
            abstract="Abstract.",
            authors=[Author(name="Author A")],
            source=None,
            publication_date=None,
            url=None,
            pdf_url=None,
            doi="10.1000/xyz",
        )
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(False, [], None)):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "  Page: https://doi.org/10.1000/xyz" in content

    def test_log_no_page_line_when_no_url_and_no_doi(self, tmp_path):
        """When paper has neither url nor doi, no Page: line is written."""
        paper = Paper(
            title="Bare Paper",
            abstract="Abstract.",
            authors=[Author(name="Author B")],
            source=None,
            publication_date=None,
            url=None,
            pdf_url=None,
            doi=None,
        )
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_download_paper", return_value=(False, [], None)):
            runner.run()
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "  Page:" not in content


class TestDownloadRunnerVerbose:
    """Tests for the verbose=True logging path."""

    def test_verbose_run_does_not_raise(self, tmp_path):
        """run(verbose=True) completes without raising."""

        runner = DownloadRunner(papers=[], output_directory=str(tmp_path))
        # Should not raise.
        metrics = runner.run(verbose=True)
        assert metrics["total_papers"] == 0

    def test_verbose_true_emits_configuration_header(self, make_paper, tmp_path, caplog):
        """verbose=True logs the DownloadRunner configuration header."""
        import logging

        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with (
            patch.object(runner, "_download_paper", return_value=(True, ["http://url"], None)),
            caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)
        assert "DownloadRunner Configuration" in " ".join(caplog.messages)

    def test_verbose_true_emits_download_summary(self, make_paper, tmp_path, caplog):
        """verbose=True logs the download summary after execution."""
        import logging

        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with (
            patch.object(runner, "_download_paper", return_value=(True, ["http://url"], None)),
            caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)
        messages = " ".join(caplog.messages)
        assert "Download Summary" in messages
        assert "Runtime" in messages

    def test_verbose_true_logs_download_error(self, make_paper, tmp_path, caplog):
        """verbose=True logs a WARNING when a paper download fails."""
        import logging

        paper = make_paper(title="Failing Paper")
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with (
            patch.object(runner, "_download_paper", side_effect=RuntimeError("network error")),
            caplog.at_level(logging.WARNING, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)
        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Failing Paper" in str(w) for w in warnings)

    def test_verbose_false_emits_no_configuration_log(self, tmp_path, caplog):
        """verbose=False (default) does not log the configuration header."""
        import logging

        runner = DownloadRunner(papers=[], output_directory=str(tmp_path))
        with caplog.at_level(logging.INFO, logger="findpapers.runners.download_runner"):
            runner.run(verbose=False)
        assert "DownloadRunner Configuration" not in " ".join(caplog.messages)

    def test_verbose_true_restores_root_logger_level(self, tmp_path):
        """run(verbose=True) restores the root logger level on exit."""
        import logging

        runner = DownloadRunner(papers=[], output_directory=str(tmp_path))
        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.WARNING)
        try:
            runner.run(verbose=True)
            assert root_logger.level == logging.WARNING
        finally:
            root_logger.setLevel(original_level)

    def test_show_progress_false_disables_progress_bar(self, make_paper, tmp_path):
        """show_progress=False suppresses the tqdm progress bar."""
        papers = [make_paper()]
        runner = DownloadRunner(papers=papers, output_directory=str(tmp_path))
        with (
            patch.object(runner, "_download_paper", return_value=(True, [], None)),
            patch("findpapers.utils.parallel.make_progress_bar") as mock_pbar,
        ):
            runner.run(show_progress=False)
            # Verify that make_progress_bar was called with disable=True
            assert mock_pbar.called
            for call in mock_pbar.call_args_list:
                assert call.kwargs.get("disable") is True

    def test_verbose_true_suppresses_third_party_loggers(self, tmp_path):
        """verbose=True sets noisy third-party loggers to WARNING to avoid credential leaks."""
        import logging

        runner = DownloadRunner(papers=[], output_directory=str(tmp_path))
        runner.run(verbose=True)
        for lib in ("urllib3", "requests", "curl_cffi", "charset_normalizer"):
            assert logging.getLogger(lib).level == logging.WARNING

    def test_verbose_true_masks_proxy_credentials(self, tmp_path, caplog):
        """verbose=True does not log proxy credentials in plain text."""
        import logging

        runner = DownloadRunner(
            papers=[],
            output_directory=str(tmp_path),
            proxy="http://user:secret@proxy.example.com:8080",
        )
        with caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"):
            runner.run(verbose=True)
        messages = " ".join(caplog.messages)
        assert "secret" not in messages
        assert "user" not in messages
        assert "proxy.example.com" in messages

    def test_request_and_response_logged_at_debug(self, make_paper, tmp_path, caplog):
        """_request() logs GET url and response details at DEBUG level."""
        paper = make_paper(title="Debug Log Paper")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.content = b"%PDF"
        mock_resp.url = "http://example.com/paper.pdf"

        ctx = MagicMock()
        ctx.get.return_value = mock_resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with (
            patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session),
            caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)

        debug_messages = " ".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        assert "GET" in debug_messages
        assert "200" in debug_messages

    def test_response_not_logged_when_connection_fails(self, make_paper, tmp_path, caplog):
        """No response log is emitted when the curl_cffi request raises (no connection)."""
        ctx = MagicMock()
        ctx.get.side_effect = _CurlError("refused")
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with (
            patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session),
            caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)

        debug_messages = " ".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        # GET is logged before the request attempt; response must NOT appear
        assert "GET" in debug_messages
        assert "<-" not in debug_messages

    def test_chrome_impersonation_used_in_request(self, make_paper, tmp_path):
        """_CurlSession is created with impersonate='chrome' for bot-detection bypass."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.content = b"%PDF"
        mock_resp.url = "http://example.com/paper.pdf"
        mock_resp.ok = True

        ctx = MagicMock()
        ctx.get.return_value = mock_resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with patch(
            "findpapers.runners.download_runner._CurlSession", return_value=mock_session
        ) as MockSession:
            runner.run()

        MockSession.assert_called_once_with(impersonate="chrome")

    def test_418_response_emits_warning(self, make_paper, tmp_path, caplog):
        """A 418 response from bot-detection logs a WARNING with a clear message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 418
        mock_resp.reason = "I'm a Teapot"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.content = b"<html>blocked</html>"
        mock_resp.url = "http://example.com/paper"
        mock_resp.ok = False

        ctx = MagicMock()
        ctx.get.return_value = mock_resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with (
            patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session),
            caplog.at_level(logging.WARNING, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)

        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("418" in str(w) or "bot" in str(w).lower() for w in warnings)


class TestDownloadRunnerSslVerify:
    """Tests for the ssl_verify parameter."""

    def test_ssl_verify_defaults_to_true(self):
        """ssl_verify defaults to True when not specified."""
        runner = DownloadRunner(papers=[], output_directory="/tmp")
        assert runner._ssl_verify is True

    def test_ssl_verify_stored_when_false(self):
        """ssl_verify=False is stored on the runner."""
        runner = DownloadRunner(papers=[], output_directory="/tmp", ssl_verify=False)
        assert runner._ssl_verify is False

    def test_ssl_verify_passed_to_curl_session_get(self, make_paper, tmp_path):
        """ssl_verify value is forwarded to _CurlSession.get() as verify=."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.content = b"%PDF"
        mock_resp.url = "http://example.com/paper.pdf"

        ctx = MagicMock()
        ctx.get.return_value = mock_resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(
            papers=[make_paper()],
            output_directory=str(tmp_path),
            ssl_verify=False,
        )
        with patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session):
            runner.run()

        _, kwargs = ctx.get.call_args
        assert kwargs.get("verify") is False

    def test_ssl_verify_true_passed_to_curl_session_get(self, make_paper, tmp_path):
        """ssl_verify=True (default) forwards verify=True to _CurlSession.get()."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.content = b"%PDF"
        mock_resp.url = "http://example.com/paper.pdf"

        ctx = MagicMock()
        ctx.get.return_value = mock_resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(
            papers=[make_paper()],
            output_directory=str(tmp_path),
        )
        with patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session):
            runner.run()

        _, kwargs = ctx.get.call_args
        assert kwargs.get("verify") is True

    def test_ssl_verify_logged_in_verbose_mode(self, tmp_path, caplog):
        """verbose=True includes ssl_verify value in the configuration log."""
        runner = DownloadRunner(
            papers=[],
            output_directory=str(tmp_path),
            ssl_verify=False,
        )
        with caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"):
            runner.run(verbose=True)
        messages = " ".join(caplog.messages)
        assert "SSL verify" in messages
        assert "False" in messages

    def test_request_exception_logged_at_debug(self, make_paper, tmp_path, caplog):
        """When _CurlSession.get raises, the exception is logged at DEBUG level."""
        ctx = MagicMock()
        ctx.get.side_effect = _CurlError("SSL handshake failed")
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[make_paper()], output_directory=str(tmp_path))
        with (
            patch(
                "findpapers.runners.download_runner._CurlSession",
                return_value=mock_session,
            ),
            caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"),
        ):
            runner.run(verbose=True)

        debug_messages = [r for r in caplog.records if r.levelno == logging.DEBUG]
        # At least one record should carry exc_info about the failure
        assert any(r.exc_info is not None for r in debug_messages)


class TestDownloadRunnerMaskProxyCredentials:
    """Tests for the _mask_proxy_credentials static method."""

    def test_none_returns_none_string(self):
        """None proxy returns the string 'none'."""
        assert DownloadRunner._mask_proxy_credentials(None) == "none"

    def test_proxy_without_credentials_returned_as_is(self):
        """Proxy URL without credentials is returned unchanged."""
        url = "http://proxy.example.com:8080"
        assert DownloadRunner._mask_proxy_credentials(url) == url

    def test_credentials_are_masked(self):
        """User and password in proxy URL are replaced with ***."""
        url = "http://user:secret@proxy.example.com:8080"
        masked = DownloadRunner._mask_proxy_credentials(url)
        assert "secret" not in masked
        assert "user" not in masked
        assert "proxy.example.com" in masked
        assert "8080" in masked
        assert "***:***@" in masked

    def test_only_username_masked(self):
        """A URL with only a username (no password) is also masked."""
        url = "http://user@proxy.example.com:3128"
        masked = DownloadRunner._mask_proxy_credentials(url)
        assert "user" not in masked
        assert "***:***@" in masked

    def test_malformed_proxy_url_returned_as_is(self):
        """A badly-formed proxy URL that causes urlparse to fail is returned as-is."""

        def _raising_urlparse(url, *args, **kwargs):
            raise ValueError("boom")

        with patch("findpapers.runners.download_runner.urllib.parse.urlparse", _raising_urlparse):
            result = DownloadRunner._mask_proxy_credentials("not-a-url")
        assert result == "not-a-url"


class TestDownloadRunnerUrlPriority:
    """Tests that pdf_url is tried before other URLs."""

    @staticmethod
    def _make_pdf_response():
        """Return a mock response that looks like a PDF."""
        resp = MagicMock()
        resp.headers = {"content-type": "application/pdf"}
        resp.content = b"%PDF-1.4 fake"
        resp.url = "http://example.com/paper.pdf"
        resp.ok = True
        return resp

    def test_pdf_url_tried_before_url(self, tmp_path):
        """When both pdf_url and url are set, pdf_url is tried first."""
        paper = Paper(
            title="Priority Test",
            abstract="Abstract.",
            authors=[Author(name="Author")],
            source=None,
            publication_date=date(2023, 1, 1),
            url="http://example.com/landing",
            pdf_url="http://example.com/paper.pdf",
        )
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        call_order: list[str] = []

        def _fake_request(url: str, **kwargs):
            call_order.append(url)
            return self._make_pdf_response()

        with patch.object(runner, "_request", side_effect=_fake_request):
            metrics = runner.run()

        assert call_order[0] == "http://example.com/paper.pdf", (
            "pdf_url must be the first URL tried"
        )
        assert metrics["downloaded_papers"] == 1

    def test_falls_back_to_url_when_pdf_url_fails(self, tmp_path):
        """When pdf_url request fails, url is tried next."""
        paper = Paper(
            title="Fallback Test",
            abstract="Abstract.",
            authors=[Author(name="Author")],
            source=None,
            publication_date=date(2023, 1, 1),
            url="http://example.com/landing",
            pdf_url="http://example.com/broken.pdf",
        )
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        call_order: list[str] = []

        def _fake_request(url: str, **kwargs):
            call_order.append(url)
            if "broken" in url:
                return None  # simulate failure
            return self._make_pdf_response()

        with patch.object(runner, "_request", side_effect=_fake_request):
            metrics = runner.run()

        assert call_order[0] == "http://example.com/broken.pdf"
        assert "http://example.com/landing" in call_order
        assert metrics["downloaded_papers"] == 1

    def test_only_url_when_no_pdf_url(self, tmp_path):
        """When pdf_url is not set, url is used directly."""
        paper = Paper(
            title="No PDF URL",
            abstract="Abstract.",
            authors=[Author(name="Author")],
            source=None,
            publication_date=date(2023, 1, 1),
            url="http://example.com/landing",
            pdf_url=None,
        )
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        call_order: list[str] = []

        def _fake_request(url: str, **kwargs):
            call_order.append(url)
            return self._make_pdf_response()

        with patch.object(runner, "_request", side_effect=_fake_request):
            metrics = runner.run()

        assert call_order[0] == "http://example.com/landing"
        assert metrics["downloaded_papers"] == 1


class TestDownloadRunnerEdgeCases:
    """Tests for uncovered edge-case paths in _download_paper and _request."""

    @staticmethod
    def _make_response(status_code=200, content_type="application/pdf", content=b"%PDF"):
        """Build a minimal mock response."""
        resp = MagicMock()
        resp.status_code = status_code
        resp.reason = "OK" if status_code == 200 else "Error"
        resp.headers = {"content-type": content_type}
        resp.content = content
        resp.url = "http://example.com/paper"
        resp.ok = status_code < 400
        return resp

    def test_existing_pdf_skipped(self, make_paper, tmp_path):
        """_download_paper returns True without HTTP call when PDF already exists."""
        paper = make_paper(title="Already There")
        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        # Pre-create the file that _build_filename would generate
        year = getattr(paper.publication_date, "year", None) if paper.publication_date else None
        filename = DownloadRunner._build_filename(year, paper.title)
        filepath = tmp_path / filename
        filepath.write_bytes(b"%PDF-existing")

        with patch.object(runner, "_request") as mock_request:
            metrics = runner.run()

        # The file already existed so _request() should not be called.
        mock_request.assert_not_called()
        assert metrics["downloaded_papers"] == 1

    def test_doi_url_used_as_candidate(self, make_paper, tmp_path):
        """DOI-based URL is used when paper has a DOI but no pdf_url/url."""
        paper = make_paper(title="DOI Only")
        paper.pdf_url = None
        paper.url = None
        paper.doi = "10.1234/test"

        resp = self._make_response()
        ctx = MagicMock()
        ctx.get.return_value = resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session):
            runner.run()

        called_url = ctx.get.call_args[0][0]
        assert "doi.org/10.1234/test" in called_url

    def test_html_response_resolves_to_pdf(self, make_paper, tmp_path):
        """HTML response triggers _resolve_pdf_url and follows the resolved URL."""
        paper = make_paper(title="HTML Redirect")
        paper.pdf_url = None
        paper.url = "https://link.springer.com/article/10.1007/s00000-000-0000-0"
        paper.doi = None

        html_resp = self._make_response(content_type="text/html", content=b"<html>")
        html_resp.url = "https://link.springer.com/article/10.1007/s00000-000-0000-0"
        pdf_resp = self._make_response(content_type="application/pdf", content=b"%PDF-data")

        call_count = {"n": 0}

        def _fake_get(url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return html_resp
            return pdf_resp

        ctx = MagicMock()
        ctx.get.side_effect = _fake_get
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 1
        assert call_count["n"] == 2

    def test_non_ok_response_logged(self, make_paper, tmp_path, caplog):
        """Non-success status (non-418) logs at DEBUG level."""
        paper = make_paper(title="Server Error")
        paper.pdf_url = "http://example.com/broken"
        paper.url = None
        paper.doi = None

        resp = self._make_response(status_code=500, content_type="text/html", content=b"error")
        resp.ok = False

        ctx = MagicMock()
        ctx.get.return_value = resp
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with (
            patch("findpapers.runners.download_runner._CurlSession", return_value=mock_session),
            caplog.at_level(logging.DEBUG, logger="findpapers.runners.download_runner"),
        ):
            runner.run()

        debug_msgs = " ".join(r.message for r in caplog.records if r.levelno == logging.DEBUG)
        assert "500" in debug_msgs

    def test_download_exception_caught(self, make_paper, tmp_path):
        """Exception during _download_paper loop is caught; download returns False."""
        paper = make_paper(title="Exception Paper")
        paper.pdf_url = "http://example.com/paper.pdf"
        paper.url = None
        paper.doi = None

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))

        with patch.object(runner, "_request", side_effect=RuntimeError("unexpected boom")):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 0

    def test_proxy_with_port_masked(self):
        """Proxy URL with user:pass and port masks credentials but keeps port."""
        masked = DownloadRunner._mask_proxy_credentials("http://myuser:mypass@proxy.local:9090")
        assert "myuser" not in masked
        assert "mypass" not in masked
        assert "9090" in masked
        assert "proxy.local" in masked

    def test_html_resolved_pdf_url_returns_none(self, make_paper, tmp_path):
        """When resolved PDF URL request returns None, download continues to next URL."""
        paper = make_paper(title="Resolved None")
        paper.pdf_url = None
        paper.url = "https://link.springer.com/article/10.1007/s00000-000-0000-0"
        paper.doi = None

        html_resp = self._make_response(content_type="text/html", content=b"<html>")
        html_resp.url = "https://link.springer.com/article/10.1007/s00000-000-0000-0"

        call_count = {"n": 0}

        def _fake_get(url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return html_resp
            # Resolved PDF URL request fails
            return None

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_request", side_effect=_fake_get):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 0
        assert call_count["n"] == 2

    def test_download_loop_exception_is_caught(self, make_paper, tmp_path):
        """Exception raised inside download loop is caught, paper not downloaded."""
        paper = make_paper(title="Loop Exception")
        paper.pdf_url = "http://example.com/paper.pdf"
        paper.url = None
        paper.doi = None

        resp = self._make_response(content_type="application/pdf")
        # Make response.content raise to trigger the broad except
        type(resp).content = property(lambda self: (_ for _ in ()).throw(OSError("disk full")))

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_request", return_value=resp):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 0

    def test_landing_page_is_pdf_logs_url_not_skipped_placeholder(self, tmp_path):
        """When paper.url itself points to a PDF, the download succeeds and the
        log shows the PDF URL on a '  ->' line, not '(already downloaded, skipped)'.

        This covers the bug where the landing-page-is-PDF path returned
        ``(True, [])`` — which the log interpreted as 'file already existed'.
        """
        pdf_url = "https://www.ijmems.in/uploads/paper.pdf"
        paper = Paper(
            title="Direct PDF Paper",
            abstract="Abstract.",
            authors=[Author(name="Author")],
            source=None,
            publication_date=None,
            url=pdf_url,
            pdf_url=None,
            doi=None,
        )
        pdf_resp = self._make_response(content_type="application/pdf", content=b"%PDF-ok")
        pdf_resp.url = pdf_url

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_request", return_value=pdf_resp):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 1
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "(already downloaded, skipped)" not in content
        assert f"  -> {pdf_url}" in content

    def test_pdf_url_equals_paper_url_logs_arrow_not_skipped_placeholder(self, tmp_path):
        """When paper.pdf_url == paper.url, the URL must appear in the '  ->' log
        line and not be silently swallowed as if the file already existed.

        This covers the bug where the paper_url filter removed the only URL from
        attempted_urls, producing '(already downloaded, skipped)' for a fresh download.
        """
        shared_url = "https://example.com/paper.pdf"
        paper = Paper(
            title="Same URL Paper",
            abstract="Abstract.",
            authors=[Author(name="Author")],
            source=None,
            publication_date=None,
            url=shared_url,
            pdf_url=shared_url,
            doi=None,
        )
        pdf_resp = self._make_response(content_type="application/pdf", content=b"%PDF-ok")
        pdf_resp.url = shared_url

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_request", return_value=pdf_resp):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 1
        content = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "(already downloaded, skipped)" not in content
        assert f"  -> {shared_url}" in content

    def test_duplicate_resolved_pdf_url_is_not_retried(self, make_paper, tmp_path):
        """When both paper.url and paper.doi are set, only the DOI landing page
        is visited (DOI takes priority).  The resolved PDF URL is tried exactly
        once regardless of how many candidates could have produced the same URL.
        """
        pdf_url = (
            "https://www.sciencedirect.com/science/article/pii/S1234/pdfft"
            "?isDTMRedir=true&download=true"
        )
        paper = make_paper(title="Duplicate Resolved URL")
        paper.pdf_url = None
        paper.url = "https://linkinghub.elsevier.com/retrieve/pii/S1234"
        paper.doi = "10.1016/j.foo.2026.001"

        landing_url = "https://linkinghub.elsevier.com/retrieve/pii/S1234"
        html_resp = self._make_response(content_type="text/html", content=b"<html>")
        html_resp.url = landing_url

        # Resolved PDF URL returns HTML (paywall/login page)
        pdf_html_resp = self._make_response(content_type="text/html", content=b"<html>login</html>")
        pdf_html_resp.url = pdf_url

        request_urls: list[str] = []

        def _fake_request(url, **kwargs):
            request_urls.append(url)
            if "doi.org" in url:
                return html_resp  # DOI redirects to the Elsevier landing page
            if url == landing_url:
                return html_resp
            return pdf_html_resp  # resolved PDF URL returns a paywall page

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with (
            patch.object(runner, "_request", side_effect=_fake_request),
            patch.object(DownloadRunner, "_resolve_pdf_url", return_value=pdf_url),
        ):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 0
        # DOI is preferred as the landing page source; paper.url is never fetched.
        doi_reqs = [u for u in request_urls if "doi.org" in u]
        assert len(doi_reqs) == 1
        assert paper.url not in request_urls
        # The resolved PDF URL is tried exactly once.
        assert request_urls.count(pdf_url) == 1

    def test_doi_url_logged_as_final_redirect_url(self, make_paper, tmp_path):
        """When a DOI URL redirects to a publisher landing page, the log shows
        the final URL (after redirects) rather than the original doi.org URL.
        """
        paper = make_paper(title="DOI Redirect Paper")
        paper.pdf_url = None
        paper.url = None
        paper.doi = "10.1016/j.foo.2026.001"

        landing_url = "https://linkinghub.elsevier.com/retrieve/pii/S9999"
        html_resp = self._make_response(content_type="text/html", content=b"<html>")
        # Simulate the DOI redirecting to the publisher landing page.
        html_resp.url = landing_url

        pdf_url = (
            "https://www.sciencedirect.com/science/article/pii/S9999"
            "/pdfft?isDTMRedir=true&download=true"
        )
        pdf_resp = self._make_response(content_type="application/pdf", content=b"%PDF-ok")
        pdf_resp.url = pdf_url

        def _fake_request(url, **kwargs):
            if "doi.org" in url:
                return html_resp
            return pdf_resp

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with (
            patch.object(runner, "_request", side_effect=_fake_request),
            patch.object(DownloadRunner, "_resolve_pdf_url", return_value=pdf_url),
        ):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 1
        log = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        # Page: shows the final resolved landing URL (after DOI redirect) for manual access.
        assert "  Page: https://linkinghub.elsevier.com/retrieve/pii/S9999" in log
        # -> lines show only actual PDF-level attempts (pattern URL), not the
        # landing page itself.
        attempted_lines = [line for line in log.splitlines() if line.startswith("  -> ")]
        assert any(pdf_url in line for line in attempted_lines)
        assert not any("doi.org" in line for line in attempted_lines)
        assert not any(landing_url in line for line in attempted_lines)

    def test_relative_pdf_url_is_skipped(self, make_paper, tmp_path):
        """Relative URLs stored in paper.pdf_url are silently skipped and never
        logged, since they cannot be requested without a base URL.
        """
        paper = make_paper(title="Relative PDF Paper")
        paper.pdf_url = "/en/download/article-file/5252864"  # relative path
        paper.url = None
        paper.doi = None

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        requested_urls: list[str] = []

        def _fake_request(url, **kwargs):
            requested_urls.append(url)
            return None

        with patch.object(runner, "_request", side_effect=_fake_request):
            runner.run()

        # The relative URL must never have been requested or logged.
        assert requested_urls == []
        log = (tmp_path / "download_log.txt").read_text(encoding="utf-8")
        assert "/en/download/article-file/5252864" not in log


# ---------------------------------------------------------------------------
# Tests for DownloadRunner static method helpers
# ---------------------------------------------------------------------------

# Shortcuts for cleaner test code
_resolve_pdf_url = DownloadRunner._resolve_pdf_url
_build_filename = DownloadRunner._build_filename
_build_proxies = DownloadRunner._build_proxies
_extract_meta_pdf_url = DownloadRunner._extract_meta_pdf_url


class TestExtractMetaPdfUrl:
    """Tests for _extract_meta_pdf_url()."""

    def test_citation_pdf_url_meta_tag(self) -> None:
        """citation_pdf_url meta tag is extracted."""
        html = b'<html><head><meta name="citation_pdf_url" content="https://example.com/paper.pdf"></head></html>'
        assert _extract_meta_pdf_url(html) == "https://example.com/paper.pdf"

    def test_fulltext_pdf_url_meta_tag(self) -> None:
        """fulltext_pdf_url meta tag is extracted."""
        html = b'<html><head><meta name="fulltext_pdf_url" content="https://example.com/full.pdf"></head></html>'
        assert _extract_meta_pdf_url(html) == "https://example.com/full.pdf"

    def test_citation_pdf_url_takes_precedence_over_fulltext(self) -> None:
        """citation_pdf_url is returned before fulltext_pdf_url (document order)."""
        html = (
            b"<html><head>"
            b'<meta name="citation_pdf_url" content="https://example.com/cite.pdf">'
            b'<meta name="fulltext_pdf_url" content="https://example.com/full.pdf">'
            b"</head></html>"
        )
        assert _extract_meta_pdf_url(html) == "https://example.com/cite.pdf"

    def test_missing_meta_returns_none(self) -> None:
        """HTML with no relevant meta tags returns None."""
        html = b"<html><head><title>Paper</title></head></html>"
        assert _extract_meta_pdf_url(html) is None

    def test_empty_content_attr_ignored(self) -> None:
        """Meta tag with empty content attribute is ignored."""
        html = b'<html><head><meta name="citation_pdf_url" content=""></head></html>'
        assert _extract_meta_pdf_url(html) is None

    def test_invalid_html_returns_none(self) -> None:
        """Completely invalid bytes that cannot be parsed return None."""
        assert _extract_meta_pdf_url(b"\x00\x01\x02") is None

    def test_relative_url_resolved_against_base(self) -> None:
        """Relative meta URL is resolved to an absolute URL using base_url."""
        html = b'<html><head><meta name="citation_pdf_url" content="/en/download/article-file/123"></head></html>'
        result = _extract_meta_pdf_url(
            html, base_url="https://dergipark.org.tr/en/pub/tuje/article/456"
        )
        assert result == "https://dergipark.org.tr/en/download/article-file/123"

    def test_absolute_url_not_altered_by_base(self) -> None:
        """Absolute meta URL is returned unchanged even when base_url is provided."""
        html = b'<html><head><meta name="citation_pdf_url" content="https://other.host/paper.pdf"></head></html>'
        result = _extract_meta_pdf_url(html, base_url="https://dergipark.org.tr/en/pub/article/1")
        assert result == "https://other.host/paper.pdf"

    def test_no_base_url_returns_relative_as_is(self) -> None:
        """When base_url is empty, relative content is returned unchanged (legacy)."""
        html = (
            b'<html><head><meta name="citation_pdf_url" content="/relative/path.pdf"></head></html>'
        )
        result = _extract_meta_pdf_url(html)
        assert result == "/relative/path.pdf"

    def test_meta_pdf_url_used_before_pattern_resolver(self, make_paper, tmp_path) -> None:
        """When HTML contains citation_pdf_url, it is tried first; the pattern-resolved
        URL is only requested if the meta URL does not return a PDF."""
        paper = make_paper(title="Meta Tag Paper")
        paper.pdf_url = None
        paper.url = "https://link.springer.com/article/10.1007/s00000-000-0000-0"
        paper.doi = None

        # A meta URL distinct from the Springer pattern URL.
        meta_pdf_url = "https://link.springer.com/content/pdf/direct-from-meta.pdf"
        html_content = (
            f'<html><head><meta name="citation_pdf_url" content="{meta_pdf_url}"></head></html>'
        ).encode()

        html_resp = MagicMock()
        html_resp.status_code = 200
        html_resp.reason = "OK"
        html_resp.headers = {"content-type": "text/html"}
        html_resp.content = html_content
        html_resp.url = paper.url
        html_resp.ok = True

        pdf_resp = MagicMock()
        pdf_resp.status_code = 200
        pdf_resp.reason = "OK"
        pdf_resp.headers = {"content-type": "application/pdf"}
        pdf_resp.content = b"%PDF-data"
        pdf_resp.url = meta_pdf_url
        pdf_resp.ok = True

        requested_urls: list[str] = []

        def _fake_request(url, **kwargs):
            requested_urls.append(url)
            if url == paper.url:
                return html_resp
            return pdf_resp  # meta URL returns PDF directly

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_request", side_effect=_fake_request):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 1
        # Meta URL was used; the Springer pattern URL was never requested.
        pattern_url = "https://link.springer.com/content/pdf/10.1007/s00000-000-0000-0.pdf"
        assert meta_pdf_url in requested_urls
        assert pattern_url not in requested_urls

    def test_pattern_resolver_used_when_meta_url_fails(self, make_paper, tmp_path) -> None:
        """When the meta PDF URL does not return a PDF, the pattern-resolved URL is tried."""
        paper = make_paper(title="Meta Fail Fallback")
        paper.pdf_url = None
        paper.url = "https://link.springer.com/article/10.1007/s00000-000-0000-0"
        paper.doi = None

        meta_pdf_url = "https://link.springer.com/content/pdf/direct-from-meta.pdf"
        pattern_url = "https://link.springer.com/content/pdf/10.1007/s00000-000-0000-0.pdf"
        html_content = (
            f'<html><head><meta name="citation_pdf_url" content="{meta_pdf_url}"></head></html>'
        ).encode()

        html_resp = MagicMock()
        html_resp.status_code = 200
        html_resp.reason = "OK"
        html_resp.headers = {"content-type": "text/html"}
        html_resp.content = html_content
        html_resp.url = paper.url
        html_resp.ok = True

        # Meta URL returns HTML (e.g. paywall), not a PDF.
        meta_fail_resp = MagicMock()
        meta_fail_resp.status_code = 200
        meta_fail_resp.reason = "OK"
        meta_fail_resp.headers = {"content-type": "text/html"}
        meta_fail_resp.content = b"<html>paywall</html>"
        meta_fail_resp.url = meta_pdf_url
        meta_fail_resp.ok = True

        pdf_resp = MagicMock()
        pdf_resp.status_code = 200
        pdf_resp.reason = "OK"
        pdf_resp.headers = {"content-type": "application/pdf"}
        pdf_resp.content = b"%PDF-ok"
        pdf_resp.url = pattern_url
        pdf_resp.ok = True

        def _fake_request(url, **kwargs):
            if url == paper.url:
                return html_resp
            if url == meta_pdf_url:
                return meta_fail_resp
            return pdf_resp  # pattern URL succeeds

        runner = DownloadRunner(papers=[paper], output_directory=str(tmp_path))
        with patch.object(runner, "_request", side_effect=_fake_request):
            metrics = runner.run()

        assert metrics["downloaded_papers"] == 1


class TestResolvePdfUrl:
    """Tests for _resolve_pdf_url()."""

    def test_acm_doi_embedded_in_path(self) -> None:
        """ACM URL with DOI in path resolves to /doi/pdf/ variant."""
        url = "https://dl.acm.org/doi/10.1145/1234567.1234568"
        result = _resolve_pdf_url(url)
        assert result == "https://dl.acm.org/doi/pdf/10.1145/1234567.1234568"

    def test_acm_uses_explicit_doi(self) -> None:
        """ACM URL without embedded DOI uses the doi parameter."""
        url = "https://dl.acm.org/doi/abs/short"
        result = _resolve_pdf_url(url, doi="10.9999/test")
        assert result == "https://dl.acm.org/doi/pdf/10.9999/test"

    def test_acm_no_doi_returns_none(self) -> None:
        """ACM URL with no extractable DOI returns None."""
        result = _resolve_pdf_url("https://dl.acm.org/", doi=None)
        assert result is None

    def test_acm_already_pdf_path_uses_doi(self) -> None:
        """ACM /doi/pdf/ path with doi param still resolves correctly."""
        result = _resolve_pdf_url(
            "https://dl.acm.org/doi/pdf/10.1145/1234567.1234568",
            doi="10.1145/1234567.1234568",
        )
        assert result == "https://dl.acm.org/doi/pdf/10.1145/1234567.1234568"

    def test_ieee_document_path(self) -> None:
        """IEEE document path is converted directly to stampPDF/getPDF.jsp URL."""
        url = "https://ieeexplore.ieee.org/document/9999999"
        result = _resolve_pdf_url(url)
        assert result == "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9999999&ref="

    def test_ieee_arnumber_querystring(self) -> None:
        """IEEE URL with arnumber query param is converted."""
        url = "https://ieeexplore.ieee.org/xpls/abs_all.jsp?arnumber=8888888"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "arnumber=8888888" in result

    def test_ieee_stamp_url_resolves_to_get_pdf(self) -> None:
        """IEEE stamp.jsp URL is resolved to the stampPDF/getPDF.jsp endpoint."""
        url = "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10000095"
        result = _resolve_pdf_url(url)
        assert (
            result == "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=10000095&ref="
        )

    def test_ieee_stamp_url_without_arnumber_returns_none(self) -> None:
        """IEEE stamp.jsp URL without arnumber returns None."""
        url = "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp="
        result = _resolve_pdf_url(url)
        assert result is None

    def test_ieee_unknown_path_returns_none(self) -> None:
        """IEEE URL without document path or arnumber returns None."""
        url = "https://ieeexplore.ieee.org/search/searchresult.jsp"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_sciencedirect_url(self) -> None:
        """ScienceDirect URL resolve is disabled; returns None."""
        url = "https://www.sciencedirect.com/science/article/pii/S0004370221000060"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_linkinghub_elsevier_url(self) -> None:
        """linkinghub.elsevier.com URL resolve is disabled; returns None."""
        url = "https://linkinghub.elsevier.com/retrieve/pii/S0004370221000060"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_rsc_articlelanding(self) -> None:
        """RSC articlelanding URL becomes articlepdf URL."""
        url = "https://pubs.rsc.org/en/content/articlelanding/2021/sc/d1sc01234a"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/articlepdf/" in result

    def test_tandfonline_full_to_pdf(self) -> None:
        """Tandfonline /full URL becomes /pdf URL."""
        url = "https://www.tandfonline.com/doi/full/10.1080/00000000.2021.123456"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/pdf" in result
        assert "/full" not in result

    def test_frontiersin_full_to_pdf(self) -> None:
        """Frontiers /full URL becomes /pdf URL."""
        url = "https://www.frontiersin.org/articles/10.3389/fpsyg.2021.123456/full"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/pdf" in result

    def test_pubs_acs_doi_to_doi_pdf(self) -> None:
        """ACS /doi URL becomes /doi/pdf URL."""
        url = "https://pubs.acs.org/doi/10.1021/acs.jcim.1c00000"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/doi/pdf/" in result

    def test_sagepub_doi_to_doi_pdf(self) -> None:
        """SAGE /doi URL becomes /doi/pdf URL."""
        url = "https://journals.sagepub.com/doi/10.1177/00000000000000"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/doi/pdf/" in result

    def test_sagepub_already_doi_pdf_returns_none(self) -> None:
        """SAGE URL already containing /doi/pdf/ is not double-modified."""
        url = "https://journals.sagepub.com/doi/pdf/10.1177/00000000000000"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_pubs_acs_already_doi_pdf_returns_none(self) -> None:
        """ACS URL already containing /doi/pdf/ is not double-modified."""
        url = "https://pubs.acs.org/doi/pdf/10.1021/acs.jcim.1c00000"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_royalsociety_already_doi_pdf_returns_none(self) -> None:
        """Royal Society URL already containing /doi/pdf/ is not double-modified."""
        url = "https://royalsocietypublishing.org/doi/pdf/10.1098/rsif.2021.0000"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_springer_article_to_content_pdf(self) -> None:
        """Springer /article/ URL is converted to /content/pdf/ + .pdf."""
        url = "https://link.springer.com/article/10.1007/s00000-021-00000-0"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/content/pdf/" in result
        assert result.endswith(".pdf")

    def test_isca_abstracts_to_pdfs(self) -> None:
        """ISCA /abstracts/*.html URL becomes /pdfs/*.pdf."""
        url = "https://www.isca-speech.org/archive/abstracts/interspeech_2021/paper.html"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/pdfs/" in result
        assert result.endswith(".pdf")

    def test_wiley_full_to_pdfdirect(self) -> None:
        """Wiley /full/ URL becomes /pdfdirect/."""
        url = "https://onlinelibrary.wiley.com/doi/full/10.1002/joc.0001"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/pdfdirect/" in result

    def test_wiley_abs_to_pdfdirect(self) -> None:
        """Wiley /abs/ URL becomes /pdfdirect/."""
        url = "https://onlinelibrary.wiley.com/doi/abs/10.1002/joc.0001"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/pdfdirect/" in result

    def test_jmir_appends_pdf(self) -> None:
        """JMIR URL gets /pdf appended."""
        url = "https://www.jmir.org/2021/1/e12345"
        result = _resolve_pdf_url(url)
        assert result == f"{url}/pdf"

    def test_mdpi_appends_pdf(self) -> None:
        """MDPI URL gets /pdf appended."""
        url = "https://www.mdpi.com/1234-5678/12/3/45"
        result = _resolve_pdf_url(url)
        assert result == f"{url}/pdf"

    def test_pnas_adds_full_pdf_suffix(self) -> None:
        """PNAS /content/ URL gets /content/pnas/ and .full.pdf suffix."""
        url = "https://www.pnas.org/content/118/1/e2015816118"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/content/pnas/" in result
        assert result.endswith(".full.pdf")

    def test_jneurosci_adds_full_pdf_suffix(self) -> None:
        """JNeurosci /content/ URL gets /content/jneuro/ and .full.pdf suffix."""
        url = "https://www.jneurosci.org/content/41/1/1"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/content/jneuro/" in result
        assert result.endswith(".full.pdf")

    def test_ijcai_paper_id_padding(self) -> None:
        """IJCAI paper ID is zero-padded to 4 digits."""
        url = "https://www.ijcai.org/proceedings/2021/42"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert result.endswith("0042.pdf")

    def test_ijcai_already_4_digit_id(self) -> None:
        """IJCAI paper ID already 4 digits is preserved."""
        url = "https://www.ijcai.org/proceedings/2021/1234"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert result.endswith("1234.pdf")

    def test_asmp_springeropen(self) -> None:
        """ASMP Springer Open /articles/ URL becomes /track/pdf/."""
        url = "https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-021-00000-0"
        result = _resolve_pdf_url(url)
        assert result is not None
        assert "/track/pdf/" in result

    def test_unknown_publisher_returns_none(self) -> None:
        """Unrecognised publisher returns None."""
        url = "https://www.unknown-publisher.edu/paper/123"
        result = _resolve_pdf_url(url)
        assert result is None

    def test_doi_param_ignored_for_non_acm(self) -> None:
        """doi parameter is ignored for non-ACM publishers."""
        url = "https://www.unknown-publisher.edu/paper/123"
        result = _resolve_pdf_url(url, doi="10.9999/test")
        assert result is None


class TestBuildFilename:
    """Tests for _build_filename()."""

    def test_basic_filename(self) -> None:
        """Standard year and title produce sanitised filename."""
        name = _build_filename(2024, "Deep Learning Survey")
        assert name.endswith(".pdf")
        assert "2024" in name
        assert "Deep" in name

    def test_special_chars_replaced(self) -> None:
        """Special characters in title are replaced with underscores."""
        name = _build_filename(2020, "Title: A & B (2020)")
        assert ".pdf" in name
        stem = name[:-4]
        for ch in stem:
            assert ch.isalnum() or ch in "_-"

    def test_none_year_uses_unknown(self) -> None:
        """None year produces 'unknown' in filename."""
        name = _build_filename(None, "Some Paper")
        assert "unknown" in name

    def test_none_title_uses_paper(self) -> None:
        """None title produces 'paper' in filename."""
        name = _build_filename(2021, None)
        assert "paper" in name

    def test_empty_title_uses_paper(self) -> None:
        """Empty string title produces 'paper' in filename."""
        name = _build_filename(2021, "")
        assert "paper" in name

    def test_always_ends_with_pdf(self) -> None:
        """Filename always ends with .pdf."""
        assert _build_filename(2022, "My Paper").endswith(".pdf")
        assert _build_filename(None, None).endswith(".pdf")

    def test_hyphen_preserved(self) -> None:
        """Hyphens in title are preserved in the filename."""
        name = _build_filename(2023, "State-of-the-Art")
        assert "-" in name


class TestBuildProxies:
    """Tests for _build_proxies()."""

    def test_explicit_proxy(self) -> None:
        """Explicit proxy URL produces http and https entries."""
        proxies = _build_proxies("http://proxy.example.com:8080")
        assert proxies == {
            "http": "http://proxy.example.com:8080",
            "https": "http://proxy.example.com:8080",
        }

    def test_no_proxy_returns_none(self, monkeypatch) -> None:
        """No proxy and no env var returns None."""
        monkeypatch.delenv("FINDPAPERS_PROXY", raising=False)
        result = _build_proxies(None)
        assert result is None

    def test_env_var_used_when_no_explicit(self, monkeypatch) -> None:
        """FINDPAPERS_PROXY env var is used when proxy param is None."""
        monkeypatch.setenv("FINDPAPERS_PROXY", "http://env-proxy:3128")
        proxies = _build_proxies(None)
        assert proxies is not None
        assert proxies["http"] == "http://env-proxy:3128"
        assert proxies["https"] == "http://env-proxy:3128"

    def test_explicit_proxy_takes_precedence(self, monkeypatch) -> None:
        """Explicit proxy overrides FINDPAPERS_PROXY env var."""
        monkeypatch.setenv("FINDPAPERS_PROXY", "http://env-proxy:3128")
        proxies = _build_proxies("http://explicit-proxy:9090")
        assert proxies is not None
        assert proxies["http"] == "http://explicit-proxy:9090"

    def test_empty_string_proxy_treated_as_none(self, monkeypatch) -> None:
        """Empty proxy string with no env var returns None."""
        monkeypatch.delenv("FINDPAPERS_PROXY", raising=False)
        result = _build_proxies("")
        assert result is None
