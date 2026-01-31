from __future__ import annotations

import datetime
import logging
import os
import re
import urllib.parse
from time import perf_counter

import requests

from findpapers.exceptions import SearchRunnerNotExecutedError
from findpapers.models import Paper
from findpapers.utils.parallel_util import execute_tasks


class DownloadRunner:
    """Runner that downloads PDFs for a provided list of papers."""

    def __init__(
        self,
        papers: list[Paper],
        output_directory: str,
        max_workers: int | None = None,
        timeout: float | None = 10.0,
        proxy: str | None = None,
    ) -> None:
        """Initialize a download run configuration without executing it.

        Parameters
        ----------
        papers : list[Paper]
            Papers to download.
        output_directory : str
            Directory where PDFs and logs will be written.
        max_workers : int | None
            Maximum workers for parallelism.
        timeout : float | None
            Global timeout in seconds.
        proxy : str | None
            Proxy URL to use for HTTP/HTTPS requests.
        """
        self._executed = False
        self._results = list(papers)
        self._metrics: dict[str, int | float] = {}
        self._output_directory = output_directory
        self._max_workers = max_workers
        self._timeout = timeout
        self._proxy = proxy

    def run(self, verbose: bool = False) -> None:
        """Download PDFs for configured papers.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging (placeholder).

        Returns
        -------
        None
        """
        if verbose:
            logging.getLogger().setLevel(logging.INFO)
        start = perf_counter()
        self._results = list(self._results)
        metrics: dict[str, int | float] = {
            "total_papers": len(self._results),
            "runtime_in_seconds": 0.0,
            "downloaded_papers": 0,
        }

        os.makedirs(self._output_directory, exist_ok=True)
        error_log_path = os.path.join(self._output_directory, "download_errors.txt")
        with open(error_log_path, "a", encoding="utf-8") as fp:
            now = datetime.datetime.now()
            fp.write(
                "------- A new download process started at: "
                f"{datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')} \n"
            )

        max_workers = self._max_workers if isinstance(self._max_workers, int) else None
        timeout = self._timeout
        proxies = self._build_proxies()

        # Download task wrapper so the parallel helper can execute per paper.
        def download_task(paper: Paper) -> tuple[bool, list[str]]:
            return self._download_paper(
                paper,
                self._output_directory,
                timeout=timeout,
                proxies=proxies,
            )

        # Parallel/sequential execution with a single progress bar over papers.
        for paper, result, error in execute_tasks(
            self._results,
            download_task,
            max_workers=max_workers,
            timeout=timeout,
            progress_total=len(self._results),
            progress_unit="paper",
            use_progress=True,
            stop_on_timeout=True,
        ):
            if error is not None or result is None:
                self._log_download_error(error_log_path, paper.title, [])
                continue
            downloaded, attempted_urls = result
            if downloaded:
                metrics["downloaded_papers"] += 1
            else:
                self._log_download_error(error_log_path, paper.title, attempted_urls)

        metrics["runtime_in_seconds"] = perf_counter() - start
        self._metrics = metrics
        self._executed = True

    def get_metrics(self) -> dict[str, int | float]:
        """Return a copy of numeric metrics after `run()`.

        Returns
        -------
        dict[str, int | float]
            Numeric metrics snapshot.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        self._ensure_executed()
        return dict(self._metrics)

    def _ensure_executed(self) -> None:
        """Guard against accessing results before `run()`.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        if not self._executed:
            raise SearchRunnerNotExecutedError("DownloadRunner has not been executed yet.")

    def _build_proxies(self) -> dict[str, str] | None:
        """Build a proxies dictionary for requests if configured.

        Returns
        -------
        dict[str, str] | None
            Proxies dictionary or None.
        """
        proxy = self._proxy or os.getenv("FINDPAPERS_PROXY")
        if not proxy:
            return None
        return {"http": proxy, "https": proxy}

    def _log_download_error(
        self,
        error_log_path: str,
        title: str,
        attempted_urls: list[str],
    ) -> None:
        """Append a download error entry to the log file.

        Parameters
        ----------
        error_log_path : str
            Path to the error log file.
        title : str
            Paper title.
        attempted_urls : list[str]
            URLs attempted for download.
        """
        with open(error_log_path, "a", encoding="utf-8") as fp:
            fp.write(f"[FAILED] {title}\n")
            if not attempted_urls:
                fp.write("Empty URL list\n")
            else:
                for url in attempted_urls:
                    fp.write(f"{url}\n")

    def _download_paper(
        self,
        paper: Paper,
        output_directory: str,
        timeout: float | None,
        proxies: dict[str, str] | None,
    ) -> tuple[bool, list[str]]:
        """Attempt to download a PDF for a single paper.

        Parameters
        ----------
        paper : Paper
            Paper to download.
        output_directory : str
            Directory where the PDF will be written.
        timeout : float | None
            Request timeout.
        proxies : dict[str, str] | None
            Proxies for HTTP/HTTPS requests.

        Returns
        -------
        tuple[bool, list[str]]
            Download status and attempted URLs.
        """
        attempted_urls: list[str] = []
        output_filepath = os.path.join(output_directory, self._build_filename(paper))
        if os.path.exists(output_filepath):
            logging.info("Paper's PDF file has already been collected")
            return True, attempted_urls

        candidate_urls = set(paper.urls)
        if paper.doi is not None:
            candidate_urls.add(f"http://doi.org/{paper.doi}")

        for url in candidate_urls:
            attempted_urls.append(str(url))
            try:
                logging.info("Fetching data from: %s", url)
                response = self._request(url, timeout=timeout, proxies=proxies)
                if response is None:
                    continue
                content_type = response.headers.get("content-type", "").lower()

                if "text/html" in content_type:
                    pdf_url = self._resolve_pdf_url(response.url, paper)
                    if pdf_url is not None:
                        attempted_urls.append(str(pdf_url))
                        response = self._request(pdf_url, timeout=timeout, proxies=proxies)
                        if response is None:
                            continue
                        content_type = response.headers.get("content-type", "").lower()

                if "application/pdf" in content_type:
                    with open(output_filepath, "wb") as fp:
                        fp.write(response.content)
                    return True, attempted_urls
            except Exception:
                logging.debug("Failed while downloading paper", exc_info=True)

        return False, attempted_urls

    def _request(
        self,
        url: str,
        timeout: float | None,
        proxies: dict[str, str] | None,
    ) -> requests.Response | None:
        """Perform a GET request with configured timeout and proxies.

        Parameters
        ----------
        url : str
            URL to request.
        timeout : float | None
            Request timeout.
        proxies : dict[str, str] | None
            Proxies for HTTP/HTTPS requests.

        Returns
        -------
        requests.Response | None
            Response instance or None when request fails.
        """
        try:
            return requests.get(url, timeout=timeout, proxies=proxies)
        except Exception:
            return None

    def _build_filename(self, paper: Paper) -> str:
        """Build a sanitized filename for the paper.

        Parameters
        ----------
        paper : Paper
            Paper for filename generation.

        Returns
        -------
        str
            Sanitized filename ending with .pdf.
        """
        year = self._paper_year(paper) or "unknown"
        title = paper.title or "paper"
        output_filename = f"{year}-{title}"
        output_filename = re.sub(r"[^\w\d-]", "_", output_filename)
        return f"{output_filename}.pdf"

    def _paper_year(self, paper: Paper) -> int | None:
        """Extract publication year from the paper if present.

        Parameters
        ----------
        paper : Paper
            Paper to inspect.

        Returns
        -------
        int | None
            Year if available.
        """
        if paper.publication_date is None:
            return None
        return getattr(paper.publication_date, "year", None)

    def _resolve_pdf_url(self, response_url: str, paper: Paper) -> str | None:
        """Resolve a PDF URL from an HTML landing page URL.

        Parameters
        ----------
        response_url : str
            Final URL after redirects.
        paper : Paper
            Paper being downloaded.

        Returns
        -------
        str | None
            PDF URL or None if not resolved.
        """
        response_url_split = urllib.parse.urlsplit(response_url)
        response_query_string = urllib.parse.parse_qs(urllib.parse.urlparse(response_url).query)
        response_url_path = response_url_split.path
        host_url = f"{response_url_split.scheme}://{response_url_split.hostname}"

        if response_url_path.endswith("/"):
            response_url_path = response_url_path[:-1]
        response_url_path = response_url_path.split("?")[0]

        if host_url in ["https://dl.acm.org"]:
            doi = paper.doi
            if (
                doi is None
                and response_url_path.startswith("/doi/")
                and "/doi/pdf/" not in response_url_path
            ):
                doi = response_url_path[4:]
            if doi is None:
                return None
            return f"https://dl.acm.org/doi/pdf/{doi}"

        if host_url in ["https://ieeexplore.ieee.org"]:
            if response_url_path.startswith("/document/"):
                document_id = response_url_path[10:]
            elif response_query_string.get("arnumber", None) is not None:
                document_id = response_query_string.get("arnumber", [""])[0]
            else:
                return None
            return f"{host_url}/stampPDF/getPDF.jsp?tp=&arnumber={document_id}"

        if host_url in ["https://www.sciencedirect.com", "https://linkinghub.elsevier.com"]:
            paper_id = response_url_path.split("/")[-1]
            return (
                "https://www.sciencedirect.com/science/article/pii/"
                f"{paper_id}/pdfft?isDTMRedir=true&download=true"
            )

        if host_url in ["https://pubs.rsc.org"]:
            return response_url.replace("/articlelanding/", "/articlepdf/")

        if host_url in ["https://www.tandfonline.com", "https://www.frontiersin.org"]:
            return response_url.replace("/full", "/pdf")

        if host_url in [
            "https://pubs.acs.org",
            "https://journals.sagepub.com",
            "https://royalsocietypublishing.org",
        ]:
            return response_url.replace("/doi", "/doi/pdf")

        if host_url in ["https://link.springer.com"]:
            return response_url.replace("/article/", "/content/pdf/").replace("%2F", "/") + ".pdf"

        if host_url in ["https://www.isca-speech.org"]:
            return response_url.replace("/abstracts/", "/pdfs/").replace(".html", ".pdf")

        if host_url in ["https://onlinelibrary.wiley.com"]:
            return response_url.replace("/full/", "/pdfdirect/").replace("/abs/", "/pdfdirect/")

        if host_url in ["https://www.jmir.org", "https://www.mdpi.com"]:
            return f"{response_url}/pdf"

        if host_url in ["https://www.pnas.org"]:
            return response_url.replace("/content/", "/content/pnas/") + ".full.pdf"

        if host_url in ["https://www.jneurosci.org"]:
            return response_url.replace("/content/", "/content/jneuro/") + ".full.pdf"

        if host_url in ["https://www.ijcai.org"]:
            paper_id = response_url.split("/")[-1].zfill(4)
            return "/".join(response_url.split("/")[:-1]) + "/" + paper_id + ".pdf"

        if host_url in ["https://asmp-eurasipjournals.springeropen.com"]:
            return response_url.replace("/articles/", "/track/pdf/")

        return None
