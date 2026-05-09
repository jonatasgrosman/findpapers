"""DownloadRunner: downloads PDFs for a list of papers."""

from __future__ import annotations

import datetime
import logging
import os
import re
import urllib.parse
from collections.abc import Callable
from datetime import UTC
from time import perf_counter
from typing import cast

import lxml.etree as _lxml_etree
import lxml.html as _lxml_html
from curl_cffi.requests import Response as _CurlResponse
from curl_cffi.requests import Session as _CurlSession
from curl_cffi.requests.errors import RequestsError as _CurlError

from findpapers.core.paper import Paper
from findpapers.utils.logging_config import configure_verbose_logging
from findpapers.utils.parallel import execute_tasks

logger = logging.getLogger(__name__)


class DownloadRunner:
    """Runner that downloads PDFs for a provided list of papers.

    For each paper, the runner tries all known URLs and follows HTML landing
    pages to resolve the actual PDF URL.  Downloaded files are saved to
    *output_directory* with a ``year-title.pdf`` naming scheme.  Both
    successful and failed downloads are logged to ``download_log.txt``
    inside *output_directory*.

    Parameters
    ----------
    papers : list[Paper]
        Papers to download.
    output_directory : str
        Directory where PDFs and the error log will be written.
    num_workers : int
        Number of parallel workers.  Defaults to ``1``, which runs
        sequentially.  Values greater than ``1`` enable parallel execution.
    timeout : float | None
        Per-request HTTP timeout in seconds.
    proxy : str | None
        Proxy URL for HTTP/HTTPS requests (also read from
        ``FINDPAPERS_PROXY`` env variable if ``None``).
    ssl_verify : bool
        Whether to verify SSL certificates.  Set to ``False`` when using
        institutional proxies that perform SSL inspection.  Defaults to
        ``True``.

    Examples
    --------
    >>> runner = DownloadRunner(papers=papers, output_directory="/tmp/pdfs")
    >>> metrics = runner.run(verbose=True)
    """

    def __init__(
        self,
        papers: list[Paper],
        output_directory: str,
        num_workers: int = 1,
        timeout: float | None = 30.0,
        proxy: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialise download configuration without executing it."""
        self._results = list(papers)
        self._metrics: dict[str, int | float] = {}
        self._output_directory = output_directory
        self._num_workers = num_workers
        self._timeout = timeout
        self._proxy = proxy
        self._ssl_verify = ssl_verify

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, verbose: bool = False, show_progress: bool = True) -> dict[str, int | float]:
        """Download PDFs for all configured papers.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging and print a summary after execution.
        show_progress : bool
            When ``True`` (default), display a tqdm progress bar while
            papers are being downloaded.  Set to ``False`` to suppress
            progress output (e.g. in non-interactive environments or to
            keep log output clean).

        Returns
        -------
        dict[str, int | float]
            Metrics with at least ``total_papers``, ``downloaded_papers``,
            and ``runtime_in_seconds``.
        """
        _root_logger = logging.getLogger()
        _saved_log_level = _root_logger.level
        if verbose:
            configure_verbose_logging()
        logger.debug("=== DownloadRunner Configuration ===")
        logger.debug("Total papers: %d", len(self._results))
        logger.debug("Output directory: %s", self._output_directory)
        logger.debug("Num workers: %d", self._num_workers)
        logger.debug("Timeout: %s", self._timeout or "default")
        logger.debug("Proxy: %s", self._mask_proxy_credentials(self._proxy))
        logger.debug("SSL verify: %s", self._ssl_verify)
        logger.debug("====================================")

        start = perf_counter()
        self._results = list(self._results)
        metrics: dict[str, int | float] = {
            "total_papers": len(self._results),
            "runtime_in_seconds": 0.0,
            "downloaded_papers": 0,
        }

        os.makedirs(self._output_directory, exist_ok=True)
        log_path = os.path.join(self._output_directory, "download_log.txt")
        with open(log_path, "a", encoding="utf-8") as fp:
            now = datetime.datetime.now(UTC)
            ts = datetime.datetime.strftime(now, "%Y-%m-%d %H:%M:%S")
            separator = "=" * 80
            fp.write(f"\n{separator}\nDownload session started: {ts}\n{separator}\n")

        num_workers = self._num_workers
        timeout = self._timeout
        proxies = self._build_proxies(self._proxy)
        ssl_verify = self._ssl_verify

        def _download_task(paper: Paper) -> tuple[bool, list[str], str | None]:
            return self._download_paper(
                paper,
                self._output_directory,
                timeout=timeout,
                proxies=proxies,
                ssl_verify=ssl_verify,
            )

        for paper, result, error in execute_tasks(
            self._results,
            _download_task,
            num_workers=num_workers,
            timeout=None,
            progress_total=len(self._results),
            progress_unit="paper",
            progress_desc="Downloading",
            use_progress=show_progress,
        ):
            if error is not None or result is None:
                # No landing page was resolved; use paper.url as fallback.
                paper_url = paper.url or (
                    f"https://doi.org/{paper.doi}" if paper.doi is not None else None
                )
                self._log_download_error(log_path, paper.title, paper_url, [])
                logger.warning("Error downloading '%s': %s", paper.title, error)
                continue
            downloaded, attempted_urls, resolved_landing_url = result
            # Prefer the publisher landing page URL obtained after following DOI
            # redirects; fall back to paper.url when no landing page was fetched
            # (e.g. attempt 1 succeeded directly from paper.pdf_url), and use a
            # doi.org URL as last resort when only a DOI is available.
            paper_url = (
                resolved_landing_url
                or paper.url
                or (f"https://doi.org/{paper.doi}" if paper.doi is not None else None)
            )
            if downloaded:
                metrics["downloaded_papers"] += 1
                self._log_download_success(log_path, paper.title, paper_url, attempted_urls)
            else:
                self._log_download_error(log_path, paper.title, paper_url, attempted_urls)

        metrics["runtime_in_seconds"] = perf_counter() - start
        self._metrics = metrics

        logger.debug("=== Download Summary ===")
        logger.debug("Total papers: %d", int(metrics["total_papers"]))
        logger.debug("Downloaded: %d", int(metrics["downloaded_papers"]))
        logger.debug("Failed: %d", int(metrics["total_papers"] - metrics["downloaded_papers"]))
        logger.debug("Runtime: %.2f s", metrics["runtime_in_seconds"])
        logger.debug("========================")

        _root_logger.setLevel(_saved_log_level)
        return dict(self._metrics)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _log_response(self, response: _CurlResponse) -> None:
        """Log a concise summary of an HTTP response at DEBUG level.

        This mirrors the behaviour in SearchConnectorBase._log_response but is
        local to the runner so downloads always produce a consistent
        debug message.
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return
        status = f"{response.status_code} {getattr(response, 'reason', '')}"
        content_type = response.headers.get("content-type", "unknown").split(";")[0].strip()
        size = len(getattr(response, "content", b""))
        logger.debug(
            "[DownloadRunner] <- %s | content-type: %s | %d bytes", status, content_type, size
        )

    @staticmethod
    def _mask_proxy_credentials(proxy: str | None) -> str:
        """Return a redacted proxy URL safe for logging.

        Credentials embedded in the URL (``user:password@``) are replaced
        with ``***:***`` so that secrets are never written to log output.

        Parameters
        ----------
        proxy : str | None
            Raw proxy URL, potentially containing embedded credentials.

        Returns
        -------
        str
            Proxy representation with credentials masked, or ``"none"``
            when *proxy* is ``None``.
        """
        if not proxy:
            return "none"
        try:
            parsed = urllib.parse.urlparse(proxy)
            if parsed.username or parsed.password:
                masked_netloc = f"***:***@{parsed.hostname or ''}"
                if parsed.port:
                    masked_netloc += f":{parsed.port}"
                return urllib.parse.urlunparse(parsed._replace(netloc=masked_netloc))
        except (ValueError, AttributeError):
            pass
        return proxy

    @staticmethod
    def _extract_meta_pdf_url(html_content: bytes, base_url: str = "") -> str | None:
        """Extract a direct PDF URL from HTML meta tags.

        Checks the following meta tag names (in order of preference):
        ``citation_pdf_url`` and ``fulltext_pdf_url``.

        Relative URLs are resolved against *base_url* so the returned value
        is always an absolute URL (or ``None``).

        Parameters
        ----------
        html_content : bytes
            Raw HTML response body.
        base_url : str
            Absolute URL of the page, used to resolve relative meta-tag values.
            Defaults to ``""`` (no resolution performed).

        Returns
        -------
        str | None
            The absolute PDF URL found in a meta tag, or ``None`` when not present.
        """
        try:
            tree = _lxml_html.fromstring(html_content)
        except Exception:
            return None
        # Attribute values are case-insensitive per HTML spec; lxml lower-cases them.
        _meta_names = {"citation_pdf_url", "fulltext_pdf_url"}
        for meta in cast(list[_lxml_etree._Element], tree.xpath("//head/meta")):
            name = (meta.get("name") or meta.get("property") or "").lower()
            if name in _meta_names:
                content = meta.get("content", "").strip()
                if content:
                    # Resolve relative paths (e.g. /en/download/…) to absolute URLs.
                    return urllib.parse.urljoin(base_url, content) if base_url else content
        return None

    @staticmethod
    def _resolve_pdf_url(response_url: str, doi: str | None = None) -> str | None:
        """Attempt to resolve a direct PDF URL from an HTML landing-page URL.

        Recognises publisher-specific URL patterns for a set of known academic
        publishers and transforms them into a URL that should serve the PDF
        directly.

        Parameters
        ----------
        response_url : str
            Final URL (after any redirects) that returned an HTML response.
        doi : str | None
            DOI of the paper, used when the publisher URL does not embed it.
            Defaults to ``None``.

        Returns
        -------
        str | None
            A URL expected to serve the PDF, or ``None`` when the publisher is
            not recognised.

        Examples
        --------
        >>> DownloadRunner._resolve_pdf_url("https://dl.acm.org/doi/10.1145/1234567.1234568")
        'https://dl.acm.org/doi/pdf/10.1145/1234567.1234568'
        """
        parts = urllib.parse.urlsplit(response_url)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(response_url).query)
        path = parts.path.rstrip("/").split("?")[0]
        host = f"{parts.scheme}://{parts.hostname}"

        if host == "https://dl.acm.org":
            return DownloadRunner._resolve_acm_pdf_url(response_url, path, doi)

        if host == "https://ieeexplore.ieee.org":
            return DownloadRunner._resolve_ieee_pdf_url(host, path, qs)

        # Simple path-pattern transforms
        _SIMPLE: dict[str, Callable[[str], str]] = {
            "https://pubs.rsc.org": lambda u: u.replace("/articlelanding/", "/articlepdf/"),
            "https://link.springer.com": lambda u: (
                u.replace("/article/", "/content/pdf/").replace("%2F", "/") + ".pdf"
            ),
            "https://www.isca-speech.org": lambda u: u.replace("/abstracts/", "/pdfs/").replace(
                ".html", ".pdf"
            ),
            "https://onlinelibrary.wiley.com": lambda u: u.replace("/full/", "/pdfdirect/").replace(
                "/abs/", "/pdfdirect/"
            ),
            "https://www.pnas.org": lambda u: (
                u.replace("/content/", "/content/pnas/") + ".full.pdf"
            ),
            "https://www.jneurosci.org": lambda u: (
                u.replace("/content/", "/content/jneuro/") + ".full.pdf"
            ),
            "https://asmp-eurasipjournals.springeropen.com": lambda u: u.replace(
                "/articles/", "/track/pdf/"
            ),
        }
        if host in _SIMPLE:
            return _SIMPLE[host](response_url)

        if host in ("https://www.tandfonline.com", "https://www.frontiersin.org"):
            return response_url.replace("/full", "/pdf")

        if host in (
            "https://pubs.acs.org",
            "https://journals.sagepub.com",
            "https://royalsocietypublishing.org",
        ):
            if "/doi/pdf/" in path:
                return None
            return response_url.replace("/doi", "/doi/pdf")

        if host in ("https://www.jmir.org", "https://www.mdpi.com"):
            return f"{response_url}/pdf"

        if host == "https://www.ijcai.org":
            paper_id = response_url.split("/")[-1].zfill(4)
            return "/".join(response_url.split("/")[:-1]) + "/" + paper_id + ".pdf"

        return None

    @staticmethod
    def _resolve_acm_pdf_url(response_url: str, path: str, doi: str | None) -> str | None:
        """Build the ACM direct-PDF URL from the landing-page URL.

        Parameters
        ----------
        response_url : str
            Final ACM landing-page URL.
        path : str
            URL path component (no query string).
        doi : str | None
            Paper DOI when known.

        Returns
        -------
        str | None
            Direct PDF URL or ``None`` when DOI cannot be determined.
        """
        resolved_doi = doi
        if resolved_doi is None and path.startswith("/doi/") and "/doi/pdf/" not in path:
            resolved_doi = path[5:]
        if resolved_doi is None:
            return None
        return f"https://dl.acm.org/doi/pdf/{resolved_doi}"

    @staticmethod
    def _resolve_ieee_pdf_url(host: str, path: str, qs: dict[str, list[str]]) -> str | None:
        """Build the IEEE Xplore direct-PDF URL from the landing-page URL.

        Parameters
        ----------
        host : str
            IEEE host (scheme + hostname).
        path : str
            URL path component (no query string).
        qs : dict[str, list[str]]
            Parsed query string parameters.

        Returns
        -------
        str | None
            Direct PDF URL or ``None`` when the document ID cannot be found.
        """
        if path.startswith("/stamp/stamp.jsp"):
            arnumber = qs.get("arnumber", [None])[0]
            if arnumber is None:
                return None
            return f"{host}/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}&ref="
        if path.startswith("/document/"):
            doc_id = path[10:]
        elif qs.get("arnumber"):
            doc_id = qs["arnumber"][0]
        else:
            return None
        return f"{host}/stampPDF/getPDF.jsp?tp=&arnumber={doc_id}&ref="

    @staticmethod
    def _build_filename(year: int | None, title: str | None) -> str:
        """Build a sanitised ``year-title.pdf`` filename for a paper.

        Non-alphanumeric characters (except ``-``) are replaced with underscores
        so the result is safe to use as a filesystem path on all major platforms.

        Parameters
        ----------
        year : int | None
            Publication year. Uses ``"unknown"`` when ``None``.
        title : str | None
            Paper title. Uses ``"paper"`` when ``None`` or empty.

        Returns
        -------
        str
            Sanitised filename ending in ``.pdf``.

        Examples
        --------
        >>> DownloadRunner._build_filename(2024, "Deep Learning: A Survey")
        '2024-Deep_Learning__A_Survey.pdf'
        """
        safe_year = str(year) if year is not None else "unknown"
        safe_title = title if title else "paper"
        raw = f"{safe_year}-{safe_title}"
        sanitised = re.sub(r"[^\w-]", "_", raw)
        return f"{sanitised}.pdf"

    @staticmethod
    def _build_proxies(proxy: str | None = None) -> dict[str, str] | None:
        """Build a *requests*-compatible proxy mapping if a proxy is configured.

        The proxy value is taken from the *proxy* parameter first; if that is
        ``None``, the ``FINDPAPERS_PROXY`` environment variable is checked.

        Parameters
        ----------
        proxy : str | None
            Explicit proxy URL.  When ``None``, falls back to the environment
            variable ``FINDPAPERS_PROXY``.

        Returns
        -------
        dict[str, str] | None
            Mapping suitable for the ``proxies`` keyword of ``requests.get``,
            or ``None`` when no proxy is configured.

        Examples
        --------
        >>> DownloadRunner._build_proxies("http://proxy.example.com:8080")
        {'http': 'http://proxy.example.com:8080', 'https': 'http://proxy.example.com:8080'}
        """
        resolved = proxy or os.getenv("FINDPAPERS_PROXY")
        if not resolved:
            return None
        return {"http": resolved, "https": resolved}

    def _log_download_success(
        self,
        log_path: str,
        title: str,
        paper_url: str | None,
        attempted_urls: list[str],
    ) -> None:
        """Append a success entry to the download log file.

        Parameters
        ----------
        log_path : str
            Path to the download log file.
        title : str
            Paper title.
        paper_url : str | None
            The paper's landing-page URL (``paper.url`` or a DOI URL).
            Written as a separate ``Page:`` line so the user can visit it
            manually if needed.
        attempted_urls : list[str]
            PDF download URLs that were tried.

        Returns
        -------
        None
        """
        with open(log_path, "a", encoding="utf-8") as fp:
            fp.write(f"\n[OK] {title}\n")
            if paper_url:
                fp.write(f"  Page: {paper_url}\n")
            if not attempted_urls:
                fp.write("  (already downloaded, skipped)\n")
            else:
                for url in attempted_urls:
                    fp.write(f"  -> {url}\n")

    def _log_download_error(
        self,
        log_path: str,
        title: str,
        paper_url: str | None,
        attempted_urls: list[str],
    ) -> None:
        """Append a failure entry to the download log file.

        Parameters
        ----------
        log_path : str
            Path to the download log file.
        title : str
            Paper title.
        paper_url : str | None
            The paper's landing-page URL (``paper.url`` or a DOI URL).
            Written as a separate ``Page:`` line so the user can visit it
            manually to attempt a download.
        attempted_urls : list[str]
            PDF download URLs that were tried.

        Returns
        -------
        None
        """
        with open(log_path, "a", encoding="utf-8") as fp:
            fp.write(f"\n[FAILED] {title}\n")
            if paper_url:
                fp.write(f"  Page: {paper_url}\n")
            if not attempted_urls:
                fp.write("  (no URLs available)\n")
            else:
                for url in attempted_urls:
                    fp.write(f"  -> {url}\n")

    def _download_paper(
        self,
        paper: Paper,
        output_directory: str,
        timeout: float | None,
        proxies: dict[str, str] | None,
        ssl_verify: bool = True,
    ) -> tuple[bool, list[str], str | None]:
        """Attempt to download the PDF for a single paper.

        Parameters
        ----------
        paper : Paper
            Paper to download.
        output_directory : str
            Target directory.
        timeout : float | None
            HTTP request timeout.
        proxies : dict[str, str] | None
            Proxy configuration.
        ssl_verify : bool
            Whether to verify SSL certificates.

        Returns
        -------
        tuple[bool, list[str], str | None]
            ``(downloaded, attempted_urls, resolved_landing_url)`` where
            *downloaded* is ``True`` when the PDF was saved successfully and
            *resolved_landing_url* is the final URL of the publisher landing
            page after DOI redirect (``None`` when no landing page was
            fetched, e.g. attempt 1 succeeded directly).
        """
        attempted_urls: list[str] = []
        year = getattr(paper.publication_date, "year", None) if paper.publication_date else None
        output_filepath = os.path.join(output_directory, self._build_filename(year, paper.title))
        if os.path.exists(output_filepath):
            logger.info("PDF already exists, skipping: %s", output_filepath)
            return True, attempted_urls, None

        def _is_absolute(url: str) -> bool:
            return url.startswith(("http://", "https://"))

        def _try_fetch_pdf(url: str) -> bool:
            """Fetch *url*, save to disk when PDF is returned; add to attempted list.

            Returns ``True`` on success.  Silently skips relative URLs and
            swallows :exc:`OSError` so a single failure never aborts the run.
            """
            if not _is_absolute(url):
                logger.debug("Skipping non-absolute URL: %s", url)
                return False
            attempted_urls.append(url)
            try:
                response = self._request(
                    url, timeout=timeout, proxies=proxies, ssl_verify=ssl_verify
                )
            except OSError:
                logger.debug("Request failed for %s", url, exc_info=True)
                return False
            if response is None:
                logger.debug("No response for %s", url)
                return False
            self._log_response(response)
            if "application/pdf" not in response.headers.get("content-type", "").lower():
                return False
            try:
                with open(output_filepath, "wb") as fp:
                    fp.write(response.content)
            except OSError:
                logger.debug("Failed to write PDF from %s", url, exc_info=True)
                return False
            return True

        # ─────────────────────────────────────────────────────────────────────
        # Attempt 1 — paper.pdf_url
        # Direct PDF link supplied by the data source (e.g. from an OA
        # repository).  Tried first as it is the most likely to succeed.
        # ─────────────────────────────────────────────────────────────────────
        if paper.pdf_url and _try_fetch_pdf(paper.pdf_url):
            return True, attempted_urls, None

        # Attempts 2 and 3 both require visiting the paper's landing page to
        # discover the actual PDF URL.  We prefer the DOI URL (canonical,
        # always resolves to the publisher); paper.url is used as a fallback
        # when no DOI is available.
        if paper.doi is not None:
            landing_url: str = f"https://doi.org/{paper.doi}"
        elif paper.url and _is_absolute(paper.url):
            landing_url = paper.url
        else:
            return False, attempted_urls, None  # no way to discover a PDF URL

        try:
            landing_response = self._request(
                landing_url, timeout=timeout, proxies=proxies, ssl_verify=ssl_verify
            )
        except OSError:
            logger.debug("Landing page request failed for %s", landing_url, exc_info=True)
            return False, attempted_urls, None

        if landing_response is None:
            logger.debug("No response for landing page %s", landing_url)
            return False, attempted_urls, None

        self._log_response(landing_response)
        landing_content_type = landing_response.headers.get("content-type", "").lower()

        # Edge case: the landing URL itself serves a PDF (e.g. paper.url
        # points directly to an open-access PDF file).
        if "application/pdf" in landing_content_type:
            attempted_urls.append(landing_response.url)
            try:
                with open(output_filepath, "wb") as fp:
                    fp.write(landing_response.content)
                return True, attempted_urls, landing_response.url
            except OSError:
                logger.debug("Failed to write PDF from landing page %s", landing_url, exc_info=True)
                return False, attempted_urls, landing_response.url

        if "text/html" not in landing_content_type:
            logger.debug(
                "Landing page %s returned unexpected content-type: %s",
                landing_url,
                landing_content_type,
            )
            return False, attempted_urls, None

        # Final URL after any redirects (e.g. doi.org → publisher landing page).
        final_landing_url = landing_response.url

        # ─────────────────────────────────────────────────────────────────────
        # Attempt 2 — meta tag PDF URL
        # Many publishers embed the PDF URL in a <meta name="citation_pdf_url">
        # tag.  This is publisher-agnostic and preferred over hardcoded patterns.
        # ─────────────────────────────────────────────────────────────────────
        meta_pdf_url = self._extract_meta_pdf_url(
            landing_response.content, base_url=final_landing_url
        )
        if meta_pdf_url and _try_fetch_pdf(meta_pdf_url):
            return True, attempted_urls, final_landing_url

        # ─────────────────────────────────────────────────────────────────────
        # Attempt 3 — publisher-specific PDF URL pattern
        # Derived from the landing page's *final* URL (after DOI redirects)
        # using known publisher URL conventions (see _resolve_pdf_url).
        # ─────────────────────────────────────────────────────────────────────
        pattern_pdf_url = self._resolve_pdf_url(final_landing_url, doi=paper.doi)
        if pattern_pdf_url and pattern_pdf_url != meta_pdf_url and _try_fetch_pdf(pattern_pdf_url):
            return True, attempted_urls, final_landing_url

        return False, attempted_urls, final_landing_url

    def _request(
        self,
        url: str,
        timeout: float | None,
        proxies: dict[str, str] | None,
        ssl_verify: bool = True,
    ) -> _CurlResponse | None:
        """Perform a GET request, returning ``None`` on failure.

        Parameters
        ----------
        url : str
            URL to fetch.
        timeout : float | None
            Request timeout in seconds.
        proxies : dict[str, str] | None
            Proxy configuration.
        ssl_verify : bool
            Whether to verify SSL certificates.  Set to ``False`` when using
            proxies that perform SSL inspection.

        Returns
        -------
        _CurlResponse | None
            Response object, or ``None`` when the request fails.
        """
        try:
            logger.debug("GET %s", url)
            with _CurlSession(impersonate="chrome") as session:
                response = session.get(
                    url,
                    proxies=proxies,
                    verify=ssl_verify,
                    allow_redirects=True,
                    timeout=timeout,
                )
        except _CurlError:
            logger.debug("Request failed for %s", url, exc_info=True)
            return None
        content_type = response.headers.get("content-type", "unknown").split(";")[0].strip()
        logger.debug(
            "<- %s %s | content-type: %s | %d bytes",
            response.status_code,
            response.reason,
            content_type,
            len(response.content),
        )
        if response.status_code == 418:
            logger.warning(
                "Server returned 418 (bot-detection) for %s — "
                "the publisher is blocking automated requests.",
                url,
            )
        elif not response.ok:
            logger.debug(
                "Non-success status %s for %s",
                response.status_code,
                url,
            )
        return response  # type: ignore[no-any-return]
