"""Engine: centralised entry point for all findpapers operations.

An :class:`Engine` instance holds shared configuration (API keys, proxy
settings, timeouts) so that callers configure once and invoke multiple
operations without repeating those details.

Example
-------
>>> from findpapers import Engine
>>> engine = Engine(
...     ieee_api_key="...",
...     scopus_api_key="...",
...     proxy="http://proxy:8080",
... )
>>> result = engine.search("[machine learning]", databases=["arxiv", "ieee"])
>>> engine.download(result.papers, "./pdfs")
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Literal

from findpapers.core.paper import Paper
from findpapers.core.search_result import SearchResult
from findpapers.core.snowball_result import SnowballResult
from findpapers.runners.discovery_runner import DEFAULT_ENRICHMENT_DATABASES
from findpapers.runners.download_runner import DownloadRunner
from findpapers.runners.get_runner import GetRunner
from findpapers.runners.search_runner import SearchRunner
from findpapers.runners.snowball_runner import _UNSET as _SNOWBALL_UNSET
from findpapers.runners.snowball_runner import SnowballRunner


class Engine:
    """Centralised facade for findpapers operations.

    Holds shared configuration — API keys, proxy, and SSL settings — that
    would otherwise need to be repeated in every call.  Per-call parameters
    such as *num_workers*, *timeout*, and *verbose* are passed directly to
    each method.

    All parameters fall back to the corresponding ``FINDPAPERS_*``
    environment variable when not supplied explicitly.

    Parameters
    ----------
    ieee_api_key : str | None
        IEEE Xplore API key.  Required to query the ``"ieee"`` database.
        Falls back to ``FINDPAPERS_IEEE_API_TOKEN``.
    scopus_api_key : str | None
        Elsevier / Scopus API key.  Required to query ``"scopus"``.
        Falls back to ``FINDPAPERS_SCOPUS_API_TOKEN``.
    pubmed_api_key : str | None
        NCBI PubMed API key.  Optional — increases the rate limit.
        Falls back to ``FINDPAPERS_PUBMED_API_TOKEN``.
    openalex_api_key : str | None
        OpenAlex API key.  Optional.
        Falls back to ``FINDPAPERS_OPENALEX_API_TOKEN``.
    email : str | None
        Contact email used for polite-pool access on APIs that support it
        (currently OpenAlex and CrossRef).  Highly recommended to avoid
        being rate-limited.
        Falls back to ``FINDPAPERS_EMAIL``.
    semantic_scholar_api_key : str | None
        Semantic Scholar API key.  Optional — increases the rate limit.
        Falls back to ``FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN``.
    wos_api_key : str | None
        Clarivate Web of Science API key.  Required to query ``"wos"``.
        Falls back to ``FINDPAPERS_WOS_API_TOKEN``.
    proxy : str | None
        Proxy URL (e.g. ``"http://proxy:8080"``).
        Falls back to ``FINDPAPERS_PROXY``.
    ssl_verify : bool
        Whether to verify SSL certificates.  Set to ``False`` when using
        institutional proxies that perform SSL inspection.
        Defaults to ``True``.  Falls back to ``FINDPAPERS_SSL_VERIFY``
        (accepted values: ``"0"``, ``"false"``, ``"no"`` → ``False``).

    Examples
    --------
    >>> from findpapers import Engine
    >>> engine = Engine(ieee_api_key="my-key", proxy="http://proxy:8080")
    >>> result = engine.search("[deep learning]", databases=["arxiv", "ieee"])
    >>> engine.download(result.papers, "./pdfs", num_workers=4)
    """

    def __init__(
        self,
        *,
        ieee_api_key: str | None = None,
        scopus_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        openalex_api_key: str | None = None,
        email: str | None = None,
        semantic_scholar_api_key: str | None = None,
        wos_api_key: str | None = None,
        proxy: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialise engine with shared configuration.

        Values not supplied explicitly are resolved from environment
        variables (see class docstring for the mapping).
        """
        self._ieee_api_key = ieee_api_key or os.environ.get("FINDPAPERS_IEEE_API_TOKEN") or None
        self._scopus_api_key = (
            scopus_api_key or os.environ.get("FINDPAPERS_SCOPUS_API_TOKEN") or None
        )
        self._pubmed_api_key = (
            pubmed_api_key or os.environ.get("FINDPAPERS_PUBMED_API_TOKEN") or None
        )
        self._openalex_api_key = (
            openalex_api_key or os.environ.get("FINDPAPERS_OPENALEX_API_TOKEN") or None
        )
        self._email = email or os.environ.get("FINDPAPERS_EMAIL") or None
        self._semantic_scholar_api_key = (
            semantic_scholar_api_key
            or os.environ.get("FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN")
            or None
        )
        self._wos_api_key = wos_api_key or os.environ.get("FINDPAPERS_WOS_API_TOKEN") or None
        self._proxy = proxy or os.environ.get("FINDPAPERS_PROXY") or None

        # ssl_verify: only fall back to env when caller omits the argument
        # (i.e. uses the default True).  Env values "0", "false", "no"
        # are treated as False.
        if ssl_verify is True and os.environ.get("FINDPAPERS_SSL_VERIFY"):
            self._ssl_verify = os.environ["FINDPAPERS_SSL_VERIFY"].lower() not in (
                "0",
                "false",
                "no",
            )
        else:
            self._ssl_verify = ssl_verify

        if not self._ssl_verify:
            logging.getLogger(__name__).warning(
                "SSL certificate verification is disabled. "
                "Connections may be vulnerable to man-in-the-middle attacks."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        databases: list[str] | None = None,
        max_papers_per_database: int | None = None,
        since: dt.date | None = None,
        until: dt.date | None = None,
        num_workers: int = 1,
        verbose: bool = False,
        show_progress: bool = True,
        enrichment_databases: list[str] | None = DEFAULT_ENRICHMENT_DATABASES,
        max_cited_by: int | None = 100,
    ) -> SearchResult:
        """Search for academic papers across multiple databases.

        Queries one or more academic databases and returns a
        :class:`~findpapers.core.search_result.SearchResult` object with the
        collected papers already deduplicated and merged.

        Query syntax
        ~~~~~~~~~~~~
        Wrap each search term in square brackets and combine them with
        ``AND``, ``OR``, or ``AND NOT`` operators.  Optionally prefix a term or
        group with a **filter code** to restrict where it is matched:

        * ``ti`` — title
        * ``abs`` — abstract
        * ``key`` — keywords
        * ``au`` — author
        * ``src`` — source (journal / conference)
        * ``aff`` — affiliation
        * ``tiabs`` — title + abstract (default when no filter is given)
        * ``tiabskey`` — title + abstract + keywords

        Example queries::

            "[machine learning]"                              # simple
            "ti[deep learning] AND abs[transformer]"           # with filters
            "[covid-19] AND ([treatment] OR [vaccine])"        # grouping

        Supported databases
        ~~~~~~~~~~~~~~~~~~~
        ``"arxiv"``, ``"ieee"`` (requires API key), ``"openalex"``,
        ``"pubmed"``, ``"scopus"`` (requires API key),
        ``"semantic_scholar"``.

        When *databases* is ``None`` every database that does **not** require
        a missing API key is queried automatically.

        Parameters
        ----------
        query : str
            Query string following the syntax described above.
        databases : list[str] | None
            Database identifiers to query.  ``None`` (default) selects all
            databases whose required API keys are available.
        max_papers_per_database : int | None
            Cap on the number of papers retrieved from each database.
            ``None`` means no limit.
        since : datetime.date | None
            Only return papers published on or after this date.  Passed to
            each database connector's API when supported.  ``None`` means
            no lower-bound filter.
        until : datetime.date | None
            Only return papers published on or before this date.  Passed to
            each database connector's API when supported.  ``None`` means
            no upper-bound filter.
        num_workers : int
            Number of parallel workers used to query databases concurrently.
            Defaults to ``1`` (sequential).
        verbose : bool
            When ``True``, emit detailed log messages at DEBUG level.
            Defaults to ``False``.
        show_progress : bool
            When ``True`` (default), display tqdm progress bars while
            papers are being fetched.  Set to ``False`` to suppress
            progress output (e.g. in non-interactive environments or to
            keep log output clean).
        enrichment_databases : list[str] | None
            Databases used to enrich papers after search and filtering.
            Defaults to ``["crossref", "web_scraping"]``, which cover the
            majority of metadata gaps without consuming quota from
            rate-limited databases.  Pass an explicit list to enable
            additional (or different) sources.  Accepted values:
            ``"arxiv"``, ``"crossref"``, ``"ieee"``, ``"openalex"``,
            ``"pubmed"``, ``"scopus"``, ``"semantic_scholar"``,
            ``"web_scraping"``.
            Pass ``None`` or ``[]`` to disable enrichment entirely.
        max_cited_by : int | None
            Maximum number of citing-paper DOIs collected per paper when
            ``"openalex"`` or ``"semantic_scholar"`` are in
            *enrichment_databases*.  Defaults to ``100``.  ``None`` means no
            limit — use with caution as highly-cited papers may have thousands
            of citations.  A warning is emitted when this value is ``None`` or
            greater than ``100``.

        Returns
        -------
        SearchResult
            A :class:`~findpapers.core.search_result.SearchResult` object
            whose ``papers`` attribute contains the collected
            :class:`~findpapers.core.paper.Paper` instances.  Save via
            :func:`findpapers.save_to_json` or
            :func:`findpapers.save_to_bibtex`.

        Raises
        ------
        findpapers.exceptions.QueryValidationError
            If *query* has syntax errors (unbalanced brackets, invalid filter
            codes, etc.).
        ValueError
            If an unknown database name is passed in *databases*.
        See Also
        --------
        findpapers.runners.search_runner.SearchRunner :
            Lower-level class for when you need access to per-run metrics or
            want to separate configuration from execution.

        Examples
        --------
        Basic search across all available databases:

        >>> from findpapers import Engine
        >>> engine = Engine()
        >>> result = engine.search("[machine learning]")
        >>> print(f"{len(result.papers)} papers found")
        127 papers found

        Targeted search with filters and database selection:

        >>> engine = Engine(ieee_api_key="my-key")
        >>> result = engine.search(
        ...     "ti[transformer] AND abs[attention mechanism]",
        ...     databases=["arxiv", "ieee"],
        ...     max_papers_per_database=50,
        ... )

        Save results to a file:

        >>> import findpapers
        >>> findpapers.save_to_json(result, "my_search.json")
        >>> findpapers.save_to_bibtex(result.papers, "my_search.bib")
        """
        runner = SearchRunner(
            query=query,
            databases=databases,
            max_papers_per_database=max_papers_per_database,
            ieee_api_key=self._ieee_api_key,
            scopus_api_key=self._scopus_api_key,
            pubmed_api_key=self._pubmed_api_key,
            openalex_api_key=self._openalex_api_key,
            email=self._email,
            semantic_scholar_api_key=self._semantic_scholar_api_key,
            wos_api_key=self._wos_api_key,
            num_workers=num_workers,
            since=since,
            until=until,
            enrichment_databases=enrichment_databases,
            max_cited_by=max_cited_by,
            proxy=self._proxy,
            ssl_verify=self._ssl_verify,
        )
        return runner.run(verbose=verbose, show_progress=show_progress)

    def download(
        self,
        papers: list[Paper],
        output_directory: str,
        *,
        num_workers: int = 1,
        timeout: float | None = 30.0,
        verbose: bool = False,
        show_progress: bool = True,
    ) -> dict[str, int | float]:
        """Download PDFs for a list of papers.

        For each paper, all known URLs are tried and HTML landing pages are
        followed to resolve the actual PDF link.  Downloaded files are saved
        to *output_directory* with a ``year-title.pdf`` naming scheme.  When
        a download fails the paper is logged to ``download_log.txt`` inside
        *output_directory*.  Successful downloads are also logged.

        Parameters
        ----------
        papers : list[Paper]
            Papers whose PDFs should be downloaded — typically obtained from
            ``engine.search(...).papers``.
        output_directory : str
            Directory where PDF files and the error log will be written.
            Created automatically if it does not exist.
        num_workers : int
            Number of parallel download workers.  Defaults to ``1``
            (sequential).  Increase to speed up bulk downloads.
        timeout : float | None
            Per-request HTTP timeout in seconds.  ``None`` disables the
            timeout.  Defaults to ``10.0``.
        verbose : bool
            When ``True``, emit detailed log messages at DEBUG level.
            Defaults to ``False``.
        show_progress : bool
            When ``True`` (default), display a tqdm progress bar while
            papers are being downloaded.  Set to ``False`` to suppress
            progress output.

        Returns
        -------
        dict[str, int | float]
            Metrics dictionary with at least the following keys:

            * ``total_papers`` — number of papers attempted.
            * ``downloaded_papers`` — number of successfully downloaded PDFs.
            * ``runtime_in_seconds`` — wall-clock time of the download
              process.

        See Also
        --------
        findpapers.runners.download_runner.DownloadRunner :
            Lower-level class for when you need finer control over the
            download pipeline.

        Examples
        --------
        >>> from findpapers import Engine
        >>> engine = Engine(proxy="http://proxy:8080")
        >>> result = engine.search("[deep learning]", databases=["arxiv"])
        >>> metrics = engine.download(result.papers, "./pdfs")
        >>> print(f"{metrics['downloaded_papers']}/{metrics['total_papers']} downloaded")
        8/10 downloaded
        """
        runner = DownloadRunner(
            papers=papers,
            output_directory=output_directory,
            num_workers=num_workers,
            timeout=timeout,
            proxy=self._proxy,
            ssl_verify=self._ssl_verify,
        )
        return runner.run(verbose=verbose, show_progress=show_progress)

    def get(
        self,
        identifier: str,
        *,
        databases: list[str] | None = None,
        max_cited_by: int | None = 100,
        timeout: float | None = 10.0,
        verbose: bool = False,
    ) -> Paper | None:
        """Fetch a single paper by its DOI or landing-page URL.

        Accepts three forms of identifier:

        * **Bare DOI** (e.g. ``"10.1038/nature12373"``) — queries each
          database via its API and merges the results into a single
          :class:`~findpapers.core.paper.Paper`.
        * **DOI URL** (e.g. ``"https://doi.org/10.1038/nature12373"``) —
          the ``doi.org`` prefix is stripped and the DOI is resolved
          through the same multi-database path.
        * **Landing-page URL** (e.g. ``"https://arxiv.org/abs/1706.03762"``
          or ``"https://www.nature.com/articles/s41586-021-03819-2"``) —
          for URLs belonging to a supported database (arXiv, PubMed, IEEE,
          OpenAlex, Semantic Scholar) the paper is fetched directly via
          that database's API.  For all other URLs the page is downloaded
          and metadata is extracted from the HTML.

        When OpenAlex or Semantic Scholar are among the queried databases,
        ``paper.cited_by`` is populated with the DOIs of papers that cite
        this paper.  OpenAlex is used as the primary source (results are
        sorted by citation count so the most-impactful papers are kept when
        the list is truncated).  Semantic Scholar is the fallback.

        Parameters
        ----------
        identifier : str
            DOI, DOI URL, or paper landing-page URL.
        databases : list[str] | None
            Sources to consult when looking up the paper.  When ``None``
            all available sources are used.  Pass a list to enable only
            the specified ones.  Accepted values: ``"arxiv"``,
            ``"crossref"``, ``"ieee"``, ``"openalex"``, ``"pubmed"``,
            ``"scopus"``, ``"semantic_scholar"``, ``"web_scraping"``.
        max_cited_by : int | None
            Maximum number of citing-paper DOIs to collect when populating
            ``paper.cited_by``.  Defaults to ``100``.  ``None`` means no
            limit — use with caution as highly-cited papers may have
            thousands of citations.
        timeout : float | None
            HTTP request timeout in seconds.  ``None`` disables the
            timeout.  Defaults to ``10.0``.
        verbose : bool
            When ``True``, emit detailed log messages at DEBUG level.
            Defaults to ``False``.

        Returns
        -------
        Paper | None
            A :class:`~findpapers.core.paper.Paper`, or ``None`` when the
            paper cannot be found or the page yields no metadata.

        Raises
        ------
        ValueError
            If *identifier* is a bare DOI that is empty or blank after
            stripping whitespace and URL prefixes.
        InvalidParameterError
            If *databases* is an empty list or contains unknown database
            names.

        See Also
        --------
        findpapers.runners.get_runner.GetRunner :
            Lower-level class that combines URL scraping and DOI-based
            lookups into a single unified pipeline.

        Examples
        --------
        Bare DOI:

        >>> from findpapers import Engine
        >>> engine = Engine()
        >>> paper = engine.get("10.1038/nature12373")

        DOI URL:

        >>> paper = engine.get("https://doi.org/10.1038/nature12373")

        Landing-page URL (delegates to the arXiv API — no scraping):

        >>> paper = engine.get("https://arxiv.org/abs/1706.03762")

        Publisher landing-page URL (HTML scraping fallback):

        >>> paper = engine.get("https://www.nature.com/articles/s41586-021-03819-2")
        """
        runner = GetRunner(
            identifier=identifier,
            email=self._email,
            databases=databases,
            ieee_api_key=self._ieee_api_key,
            scopus_api_key=self._scopus_api_key,
            pubmed_api_key=self._pubmed_api_key,
            openalex_api_key=self._openalex_api_key,
            semantic_scholar_api_key=self._semantic_scholar_api_key,
            wos_api_key=self._wos_api_key,
            timeout=timeout,
            proxy=self._proxy,
            ssl_verify=self._ssl_verify,
        )
        return runner.run(verbose=verbose, max_cited_by=max_cited_by)

    def snowball(
        self,
        papers: list[Paper] | Paper,
        *,
        max_depth: int = 1,
        direction: Literal["both", "backward", "forward"] = "both",
        max_papers_per_level: int | None = None,
        max_expansion_per_level: int | None = None,
        max_cited_by: int | None = 100,
        databases: list[str] | None = _SNOWBALL_UNSET,  # type: ignore[assignment]
        enrichment_databases: list[str] | None = _SNOWBALL_UNSET,  # type: ignore[assignment]
        since: dt.date | None = None,
        until: dt.date | None = None,
        num_workers: int = 1,
        verbose: bool = False,
        show_progress: bool = True,
    ) -> SnowballResult:
        """Discover papers around seed papers via iterative citation snowballing.

        Starting from one or more seed papers, iteratively fetches their
        references (backward) and/or citing papers (forward).  Seed papers
        are enriched with the full combined set of *databases* and
        *enrichment_databases*.  Papers discovered during BFS are fetched with
        *databases* only; after all BFS levels and filters are applied, the
        surviving non-seed papers are re-enriched with the *enrichment_databases*
        not already used during discovery.

        Papers without a DOI are silently skipped since they cannot be
        resolved by the upstream APIs.

        Parameters
        ----------
        papers : list[Paper] | Paper
            One or more seed papers from which the snowball starts.
            Typically obtained from ``engine.search(...).papers`` or
            ``engine.get(...)``.
        max_depth : int
            Maximum number of BFS levels.  ``1`` (default) retrieves
            only the immediate neighbours.  ``2`` also expands papers
            found at level 1, and so on.
        direction : Literal["both", "backward", "forward"]
            ``"backward"`` follows
            :attr:`~findpapers.core.paper.Paper.references` (papers
            cited *by* the current frontier), ``"forward"`` follows
            :attr:`~findpapers.core.paper.Paper.cited_by` (papers that
            *cite* the current frontier), ``"both"`` expands both.
        max_papers_per_level : int | None
            When set, only the *top N* most-cited papers discovered at each
            level are kept in the final result.  Seed papers are never
            filtered.  ``None`` (default) means all discovered papers
            are included.
        max_expansion_per_level : int | None
            When set, only the *top N* most-cited papers from each level are
            used as seeds for the next BFS round.  Papers already added to the
            result are unaffected.  ``None`` (default) means the full frontier
            is expanded.
        max_cited_by : int | None
            Maximum number of citing-paper DOIs to collect per paper during
            seed and frontier enrichment.  Defaults to ``100``.  ``None``
            means no limit — use with caution as highly-cited papers may have
            thousands of citations.  A warning is emitted when this value is
            ``None`` or greater than ``100``.
        databases : list[str] | None
            Databases used for BFS discovery.  Only ``"crossref"``,
            ``"openalex"``, and ``"semantic_scholar"`` are accepted.
            Defaults to ``["crossref"]`` for backward direction, or all
            three databases for ``"forward"``/``"both"``.  Pass ``None`` to
            use all three databases.  Forward and both directions require at
            least one of ``"openalex"`` or ``"semantic_scholar"``.
        enrichment_databases : list[str] | None
            Databases used to enrich non-seed papers after BFS completes.
            Defaults to ``["crossref", "web_scraping"]``.  Pass ``None`` to
            use the same default.
        since : datetime.date | None
            Only include discovered papers published on or after this
            date.  Seed papers are never filtered.  ``None`` (default)
            disables the lower-bound filter.
        until : datetime.date | None
            Only include discovered papers published on or before this
            date.  Seed papers are never filtered.  ``None`` (default)
            disables the upper-bound filter.
        num_workers : int
            Number of parallel
            :class:`~findpapers.runners.get_runner.GetRunner` calls per
            level.  Defaults to ``1`` (sequential).
        verbose : bool
            When ``True``, emit detailed log messages at DEBUG level.
        show_progress : bool
            When ``True`` (default), display tqdm progress bars while
            papers are being fetched.  Set to ``False`` to suppress
            progress output.

        Returns
        -------
        SnowballResult
            Container with all *discovered* papers (seeds excluded from
            :attr:`~findpapers.core.snowball_result.SnowballResult.papers`;
            enriched seeds are in
            :attr:`~findpapers.core.snowball_result.SnowballResult.seed_papers`).
            Citation relationships are encoded on each paper via
            :attr:`~findpapers.core.paper.Paper.references` and
            :attr:`~findpapers.core.paper.Paper.cited_by`.  Save via
            ``findpapers.save_to_json(result, path)``.

        See Also
        --------
        findpapers.runners.snowball_runner.SnowballRunner :
            Lower-level class for when you need fine-grained control
            over runner configuration.

        Examples
        --------
        Snowball from a single paper found by DOI:

        >>> from findpapers import Engine
        >>> engine = Engine()
        >>> seed = engine.get("10.1038/nature12373")
        >>> result = engine.snowball(seed, max_depth=1)
        >>> print(f"{len(result.papers)} papers found")
        42 papers found

        Save the result to JSON:

        >>> import findpapers
        >>> findpapers.save_to_json(result, "snowball_result.json")

        Snowball from search results with only backward direction:

        >>> sr = engine.search("[deep learning]")
        >>> result = engine.snowball(
        ...     sr.papers[:5],
        ...     max_depth=2,
        ...     direction="backward",
        ... )
        """
        runner = SnowballRunner(
            seed_papers=papers,
            max_depth=max_depth,
            direction=direction,
            max_papers_per_level=max_papers_per_level,
            max_expansion_per_level=max_expansion_per_level,
            max_cited_by=max_cited_by,
            databases=databases,
            enrichment_databases=enrichment_databases,
            openalex_api_key=self._openalex_api_key,
            email=self._email,
            semantic_scholar_api_key=self._semantic_scholar_api_key,
            ieee_api_key=self._ieee_api_key,
            scopus_api_key=self._scopus_api_key,
            pubmed_api_key=self._pubmed_api_key,
            wos_api_key=self._wos_api_key,
            num_workers=num_workers,
            since=since,
            until=until,
            proxy=self._proxy,
            ssl_verify=self._ssl_verify,
        )
        return runner.run(verbose=verbose, show_progress=show_progress)
