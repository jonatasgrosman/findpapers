"""DiscoveryRunner: shared base for SearchRunner and SnowballRunner."""

from __future__ import annotations

import datetime as dt
import logging

from findpapers.core.paper import Paper
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.get_runner import GET_DATABASES, GetRunner
from findpapers.utils.parallel import execute_tasks

# Databases used for enrichment when the caller does not specify any.
# Kept small on purpose: CrossRef is the canonical DOI authority and covers
# the vast majority of metadata gaps; web-scraping fills the rest without
# requiring an API key.  Databases with tight daily quotas (IEEE, Scopus)
# and those that duplicate CrossRef for most papers (OpenAlex, PubMed,
# Semantic Scholar, arXiv) are intentionally excluded from this default to
# avoid unnecessary quota consumption.
DEFAULT_ENRICHMENT_DATABASES: list[str] = ["crossref", "web_scraping"]

logger = logging.getLogger(__name__)


class DiscoveryRunner:
    """Shared base class for :class:`SearchRunner` and :class:`SnowballRunner`.

    Provides date-range filtering and post-discovery paper enrichment via
    per-paper :class:`~findpapers.runners.get_runner.GetRunner` lookups.

    Parameters
    ----------
    since : dt.date | None
        Lower-bound publication date filter (inclusive).  ``None`` disables it.
    until : dt.date | None
        Upper-bound publication date filter (inclusive).  ``None`` disables it.
    ieee_api_key : str | None
        IEEE Xplore API key for enrichment.
    scopus_api_key : str | None
        Scopus API key for enrichment.
    pubmed_api_key : str | None
        PubMed API key for enrichment.
    openalex_api_key : str | None
        OpenAlex API key for enrichment.
    email : str | None
        Contact email for polite-pool access during enrichment.
    semantic_scholar_api_key : str | None
        Semantic Scholar API key for enrichment.
    wos_api_key : str | None
        Clarivate Web of Science API key for enrichment.
    proxy : str | None
        Optional HTTP/HTTPS proxy URL for enrichment requests.
    ssl_verify : bool
        Whether to verify SSL certificates during enrichment.
    enrichment_databases : list[str] | None
        Databases for post-discovery enrichment.  Defaults to
        ``DEFAULT_ENRICHMENT_DATABASES`` (``["crossref", "web_scraping"]``).
        Pass ``None`` or ``[]`` to disable enrichment entirely.

    Raises
    ------
    InvalidParameterError
        If *enrichment_databases* contains unknown database names.
    """

    def __init__(
        self,
        *,
        since: dt.date | None = None,
        until: dt.date | None = None,
        ieee_api_key: str | None = None,
        scopus_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        openalex_api_key: str | None = None,
        email: str | None = None,
        semantic_scholar_api_key: str | None = None,
        wos_api_key: str | None = None,
        proxy: str | None = None,
        ssl_verify: bool = True,
        enrichment_databases: list[str] | None = DEFAULT_ENRICHMENT_DATABASES,
    ) -> None:
        """Initialise shared filter and enrichment state."""
        self._since = since
        self._until = until

        # Store credentials for use in the enrichment phase.
        self._ieee_api_key = ieee_api_key
        self._scopus_api_key = scopus_api_key
        self._pubmed_api_key = pubmed_api_key
        self._openalex_api_key = openalex_api_key
        self._email = email
        self._semantic_scholar_api_key = semantic_scholar_api_key
        self._wos_api_key = wos_api_key
        self._proxy = proxy
        self._ssl_verify = ssl_verify

        # Validate and normalise the enrichment database list.
        # None and [] both mean "no enrichment".
        if enrichment_databases is None or len(enrichment_databases) == 0:
            self._enrichment_databases: list[str] = []
        else:
            normalised = [db.strip().lower() for db in enrichment_databases]
            unknown = [db for db in normalised if db not in GET_DATABASES]
            if unknown:
                raise InvalidParameterError(
                    f"Unknown enrichment database(s): {', '.join(unknown)}. "
                    f"Accepted values: {', '.join(sorted(GET_DATABASES))}"
                )
            self._enrichment_databases = normalised

    def _matches_filters(self, paper: Paper) -> bool:
        """Return ``True`` when *paper* passes all configured date filters.

        Checks the ``since``/``until`` date range.  Any filter that is
        ``None`` (not configured) is treated as a pass-through.  Papers with
        no ``publication_date`` are excluded when any date filter is active.

        Parameters
        ----------
        paper : Paper
            Candidate paper to evaluate.

        Returns
        -------
        bool
            ``True`` if the paper satisfies all active filters.
        """
        if self._since is not None and (
            paper.publication_date is None or paper.publication_date < self._since
        ):
            return False
        return not (
            self._until is not None
            and (paper.publication_date is None or paper.publication_date > self._until)
        )

    def _enrich_papers(
        self,
        papers: list[Paper],
        verbose: bool = False,
        *,
        show_progress: bool = True,
        num_workers: int = 1,
    ) -> None:
        """Enrich a list of papers in-place via per-paper get() lookups.

        For each paper, creates a
        :class:`~findpapers.runners.get_runner.GetRunner` using the paper's
        DOI (preferred) or URL as the identifier and merges the result into
        the original object.  Databases that already provided the paper are
        excluded from each paper's lookup to avoid redundant requests.

        Parameters
        ----------
        papers : list[Paper]
            Papers to enrich.
        verbose : bool
            Enable verbose logging.
        show_progress : bool
            Display a tqdm progress bar while papers are being enriched.
        num_workers : int
            Number of parallel workers for enrichment tasks.

        Returns
        -------
        None
        """
        all_dbs: frozenset[str] = frozenset(self._enrichment_databases)

        enrich_queue: list[tuple[Paper, str, list[str]]] = []
        for paper in papers:
            identifier = paper.doi or paper.url
            if not identifier:
                continue

            # Exclude databases that already returned this paper.
            existing_dbs: set[str] = paper.databases or set()
            effective_dbs = list(all_dbs - existing_dbs)
            if not effective_dbs:
                continue

            enrich_queue.append((paper, identifier, effective_dbs))

        if not enrich_queue:
            return

        ieee_api_key = self._ieee_api_key
        scopus_api_key = self._scopus_api_key
        pubmed_api_key = self._pubmed_api_key
        openalex_api_key = self._openalex_api_key
        email = self._email
        semantic_scholar_api_key = self._semantic_scholar_api_key
        wos_api_key = self._wos_api_key
        proxy = self._proxy
        ssl_verify = self._ssl_verify

        def _enrich_task(item: tuple[Paper, str, list[str]]) -> None:
            """Enrich a single paper via GetRunner.

            Parameters
            ----------
            item : tuple[Paper, str, list[str]]
                A ``(paper, identifier, databases)`` tuple.

            Returns
            -------
            None
            """
            paper, identifier, databases = item
            runner = GetRunner(
                identifier=identifier,
                email=email,
                databases=databases,
                ieee_api_key=ieee_api_key,
                scopus_api_key=scopus_api_key,
                pubmed_api_key=pubmed_api_key,
                openalex_api_key=openalex_api_key,
                semantic_scholar_api_key=semantic_scholar_api_key,
                wos_api_key=wos_api_key,
                timeout=10.0,
                proxy=proxy,
                ssl_verify=ssl_verify,
            )
            result = runner.run(verbose=verbose)
            if result is not None:
                # Preserve the paper's original databases: enrichment provides
                # additional metadata but should not register new database
                # sources for the paper.
                original_databases = set(paper.databases)
                # Save the enriched URL before merging so we can restore it
                # afterwards.  merge() uses merge_value() which keeps the longer
                # string, but enrichment should always replace the URL with the
                # final URL after all redirects (web_scraping URL > crossref URL,
                # resolved inside GetRunner.run()).
                enriched_url = result.url
                paper.merge(result)
                paper.databases = original_databases
                # Replace the paper URL with the enriched one when available.
                if enriched_url is not None:
                    paper.url = enriched_url

        for _item, _result, error in execute_tasks(
            enrich_queue,
            _enrich_task,
            num_workers=num_workers,
            timeout=None,
            progress_total=len(enrich_queue),
            progress_unit="paper",
            progress_desc="Enriching",
            use_progress=show_progress,
        ):
            if error is not None:
                logger.warning("Enrichment error: %s", error)
