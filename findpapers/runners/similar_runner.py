"""SimilarRunner: single-hop content-similarity lookup around a seed paper.

Given one seed paper, this runner queries each content-similarity source
(Semantic Scholar recommendations, PubMed related-articles, OpenAlex
related_works) and merges the results into a single deduplicated list.
Unlike :class:`~findpapers.runners.snowball_runner.SnowballRunner`, this is
a single-hop lookup: there is no BFS expansion.
"""

from __future__ import annotations

import datetime as dt
import logging
from time import perf_counter

from findpapers.connectors.openalex import OpenAlexConnector
from findpapers.connectors.pubmed import PubmedConnector
from findpapers.connectors.semantic_scholar import SemanticScholarConnector
from findpapers.core.paper import Database, Paper
from findpapers.core.similar_result import SimilarResult
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.discovery_runner import DEFAULT_ENRICHMENT_DATABASES, DiscoveryRunner
from findpapers.utils.logging_config import configure_verbose_logging
from findpapers.utils.progress import make_progress_bar

logger = logging.getLogger(__name__)

# Sources supported for content-similarity lookup, in priority order.
# Semantic Scholar comes first (learned embeddings, best general fit),
# PubMed second (precise but biomedicine-only), OpenAlex last (cheap but
# coarser topic-tag-overlap signal).
SIMILAR_DATABASES: list[str] = ["semantic_scholar", "pubmed", "openalex"]

# Databases used when the caller does not pass an explicit ``databases``
# value.  OpenAlex is deliberately excluded from the default: its
# ``related_works`` field is a topic-tag-overlap signal rather than a
# learned semantic one, and live testing repeatedly turned up entries with
# no discernible connection to the seed paper (see docs/similar.md). It
# remains fully supported and can still be requested explicitly via
# ``databases=[..., "openalex"]``.
DEFAULT_SIMILAR_DATABASES: list[str] = ["semantic_scholar", "pubmed"]


def _validate_similar_databases(value: list[str] | None) -> list[str]:
    """Validate and normalise the ``databases`` parameter for :class:`SimilarRunner`.

    Parameters
    ----------
    value : list[str] | None
        Raw value to validate.  ``None`` selects
        :data:`DEFAULT_SIMILAR_DATABASES`.

    Returns
    -------
    list[str]
        Normalised (lowercased, stripped) list of database names, restricted
        to the ones supplied by *value* but always in
        :data:`SIMILAR_DATABASES` priority order.

    Raises
    ------
    InvalidParameterError
        If *value* is an empty list or contains unknown database names.
    """
    if value is None:
        return list(DEFAULT_SIMILAR_DATABASES)
    if len(value) == 0:
        raise InvalidParameterError(
            "databases must not be an empty list. Pass None to select all available databases."
        )
    normalised = {db.strip().lower() for db in value}
    unknown = normalised - set(SIMILAR_DATABASES)
    if unknown:
        raise InvalidParameterError(
            f"Unknown database(s): {', '.join(sorted(unknown))}. "
            f"Accepted values: {', '.join(SIMILAR_DATABASES)}"
        )
    return [db for db in SIMILAR_DATABASES if db in normalised]


class SimilarRunner(DiscoveryRunner):
    """Runner that finds content-similar papers around a single seed paper.

    Queries each configured source sequentially (in :data:`SIMILAR_DATABASES`
    priority order), merges results by identity (DOI, falling back to
    lowercased title) via :meth:`~findpapers.core.paper.Paper.merge`, and
    records per-paper provenance via
    :meth:`~findpapers.core.paper.Paper.add_database`.  A source failure is
    isolated and logged; it does not abort the other sources.

    Like :class:`~findpapers.runners.search_runner.SearchRunner` and
    :class:`~findpapers.runners.snowball_runner.SnowballRunner`, this runner
    inherits from :class:`~findpapers.runners.discovery_runner.DiscoveryRunner`
    for the shared post-fetch date filter and post-fetch enrichment pass.
    Neither of the three similarity sources supports native date filtering,
    so ``since``/``until`` are applied after the merge instead.

    All three sources are DOI-anchored, so the seed paper must have a DOI;
    one without a DOI is rejected at construction time.

    Parameters
    ----------
    paper : Paper
        The seed paper to find related papers for.  Must have a DOI.
    databases : list[str] | None
        Sources to consult, in priority order.  ``None`` (default) uses
        :data:`DEFAULT_SIMILAR_DATABASES` (Semantic Scholar and PubMed).
        OpenAlex is supported but not included by default because its
        ``related_works`` signal is coarser and noisier; pass it explicitly
        (e.g. ``databases=["semantic_scholar", "pubmed", "openalex"]``) to
        include it.
    max_papers_per_database : int | None
        Cap on the number of related papers requested/kept from each source
        before merging.  ``None`` (default) lets each source's own natural
        default apply (Semantic Scholar: 100; PubMed: 100, a hard NCBI cap;
        OpenAlex: whatever short, fixed ``related_works`` list is embedded in
        the seed work, typically 10-20).
    since : dt.date | None
        Only keep related papers published on or after this date.  Applied
        after merging, since none of the three sources support native date
        filtering.  ``None`` disables the lower-bound filter.
    until : dt.date | None
        Only keep related papers published on or before this date.  Applied
        after merging.  ``None`` disables the upper-bound filter.
    enrichment_databases : list[str] | None
        Databases used to enrich related papers after merging and filtering,
        via per-paper :class:`~findpapers.runners.get_runner.GetRunner`
        lookups (same mechanism as :class:`SearchRunner`/:class:`SnowballRunner`).
        Defaults to ``["crossref", "web_scraping"]``.  Pass ``[]`` to disable
        enrichment entirely.
    max_cited_by : int | None
        Maximum number of citing-paper DOIs to collect per paper during
        enrichment, when ``"openalex"`` or ``"semantic_scholar"`` are in
        *enrichment_databases*.  Defaults to ``100``.
    num_workers : int
        Number of parallel workers used for the enrichment pass.  Defaults
        to ``1`` (sequential).
    email : str | None
        Contact email for CrossRef/OpenAlex polite-pool access during
        enrichment.  Unused by the three similarity sources themselves.
    openalex_api_key : str | None
        OpenAlex API key.  Optional: increases the daily quota.
    semantic_scholar_api_key : str | None
        Semantic Scholar API key.  Optional: increases the rate limit.
    pubmed_api_key : str | None
        NCBI PubMed API key.  Optional: increases the rate limit.
    ieee_api_key : str | None
        IEEE Xplore API key, used only if ``"ieee"`` is included in
        *enrichment_databases*.
    scopus_api_key : str | None
        Elsevier/Scopus API key, used only if ``"scopus"`` is included in
        *enrichment_databases*.
    wos_api_key : str | None
        Clarivate Web of Science API key, used only if ``"wos"`` is included
        in *enrichment_databases*.
    timeout : float | None
        HTTP request timeout in seconds for the three similarity sources.
        ``None`` uses the ``requests`` default.
    proxy : str | None
        Optional HTTP/HTTPS proxy URL for enrichment requests.
    ssl_verify : bool
        Whether to verify SSL certificates.  Defaults to ``True``.

    Raises
    ------
    InvalidParameterError
        If *paper* has no DOI.
    InvalidParameterError
        If *databases* is an empty list or contains unknown database names.
    InvalidParameterError
        If *enrichment_databases* contains unknown database names.
    """

    def __init__(
        self,
        paper: Paper,
        *,
        databases: list[str] | None = None,
        max_papers_per_database: int | None = None,
        since: dt.date | None = None,
        until: dt.date | None = None,
        enrichment_databases: list[str] | None = DEFAULT_ENRICHMENT_DATABASES,
        max_cited_by: int | None = 100,
        num_workers: int = 1,
        email: str | None = None,
        openalex_api_key: str | None = None,
        semantic_scholar_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        ieee_api_key: str | None = None,
        scopus_api_key: str | None = None,
        wos_api_key: str | None = None,
        timeout: float | None = 10.0,
        proxy: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialise the runner with a seed paper and connection settings.

        See the class docstring for parameter descriptions.

        Raises
        ------
        InvalidParameterError
            If *paper* has no DOI.
        InvalidParameterError
            If *databases* is an empty list or contains unknown database
            names.
        InvalidParameterError
            If *enrichment_databases* contains unknown database names.
        """
        if not paper.doi:
            raise InvalidParameterError("paper must have a DOI.")

        self._paper = paper
        self._active_databases = _validate_similar_databases(databases)
        self._requested_databases = databases
        self._max_papers_per_database = max_papers_per_database
        self._num_workers = num_workers
        self._max_cited_by = max_cited_by

        _enrichment_dbs_set = set(enrichment_databases or [])
        _has_citation_enrich = bool(_enrichment_dbs_set & {"openalex", "semantic_scholar"})
        if _has_citation_enrich and (max_cited_by is None or max_cited_by > 100):
            logger.warning(
                "max_cited_by is %s. Fetching cited-by during enrichment may be very slow "
                "or produce large lists for highly-cited papers. "
                "Consider setting max_cited_by <= 100.",
                max_cited_by if max_cited_by is not None else "None (unlimited)",
            )

        super().__init__(
            since=since,
            until=until,
            ieee_api_key=ieee_api_key,
            scopus_api_key=scopus_api_key,
            pubmed_api_key=pubmed_api_key,
            openalex_api_key=openalex_api_key,
            email=email,
            semantic_scholar_api_key=semantic_scholar_api_key,
            wos_api_key=wos_api_key,
            proxy=proxy,
            ssl_verify=ssl_verify,
            enrichment_databases=enrichment_databases,
        )

        self._semantic_scholar = (
            SemanticScholarConnector(api_key=semantic_scholar_api_key)
            if Database.SEMANTIC_SCHOLAR.value in self._active_databases
            else None
        )
        self._pubmed = (
            PubmedConnector(api_key=pubmed_api_key)
            if Database.PUBMED.value in self._active_databases
            else None
        )
        self._openalex = (
            OpenAlexConnector(api_key=openalex_api_key, email=email)
            if Database.OPENALEX.value in self._active_databases
            else None
        )

        if timeout is not None:
            for connector in (self._semantic_scholar, self._pubmed, self._openalex):
                if connector is not None:
                    connector._timeout = timeout

    def run(self, verbose: bool = False, show_progress: bool = True) -> SimilarResult:
        """Execute the content-similarity lookup for the configured seed paper.

        Runs the fetch/merge pipeline, then (like
        :class:`~findpapers.runners.search_runner.SearchRunner`) applies the
        ``since``/``until`` date filter and the enrichment pass inherited
        from :class:`~findpapers.runners.discovery_runner.DiscoveryRunner`.

        Parameters
        ----------
        verbose : bool
            When ``True``, emit detailed log messages at DEBUG level.
            Defaults to ``False``.
        show_progress : bool
            When ``True`` (default), display a tqdm progress bar across
            sources.

        Returns
        -------
        SimilarResult
            Container whose ``papers`` attribute holds the merged,
            deduplicated, filtered, and enriched related papers.
        """
        _root_logger = logging.getLogger()
        _saved_log_level = _root_logger.level
        if verbose:
            configure_verbose_logging()

        start = perf_counter()
        failed_databases: list[str] = []
        skipped_databases: list[str] = []
        merged: dict[str, Paper] = {}
        order: list[str] = []

        try:
            self._run_sources(merged, order, failed_databases, skipped_databases, show_progress)
        finally:
            for connector in (self._semantic_scholar, self._pubmed, self._openalex):
                if connector is not None:
                    connector.close()

        papers = [merged[key] for key in order]

        # Apply post-fetch date filters: none of the three sources supports
        # native date filtering, so this always runs as a post-fetch pass.
        if self._since is not None or self._until is not None:
            before_filter = len(papers)
            papers = [p for p in papers if self._matches_filters(p)]
            logger.debug(
                "similar: post-fetch filter: %d -> %d papers (%d removed).",
                before_filter,
                len(papers),
                before_filter - len(papers),
            )

        # Enrich the filtered papers via per-paper get() lookups.
        # enrichment_databases=[] (normalised by DiscoveryRunner.__init__) disables this.
        if len(self._enrichment_databases) > 0:
            self._enrich_papers(
                papers,
                verbose,
                show_progress=show_progress,
                num_workers=self._num_workers,
                max_cited_by=self._max_cited_by,
            )

        result = SimilarResult(
            seed_paper=self._paper,
            databases=self._requested_databases,
            max_papers_per_database=self._max_papers_per_database,
            since=self._since,
            until=self._until,
            enrichment_databases=self._enrichment_databases,
            max_cited_by=self._max_cited_by,
            papers=papers,
            runtime_seconds=perf_counter() - start,
            failed_databases=failed_databases,
            skipped_databases=skipped_databases,
        )

        _root_logger.setLevel(_saved_log_level)
        return result

    def _run_sources(
        self,
        merged: dict[str, Paper],
        order: list[str],
        failed_databases: list[str],
        skipped_databases: list[str],
        show_progress: bool,
    ) -> None:
        """Query each active source in priority order, merging results in place.

        Parameters
        ----------
        merged : dict[str, Paper]
            Accumulator mapping identity key to merged paper (mutated).
        order : list[str]
            Identity keys in first-seen (priority) order (mutated).
        failed_databases : list[str]
            Sources that raised an error (mutated).
        skipped_databases : list[str]
            Sources not applicable to this seed paper (mutated).
        show_progress : bool
            Whether to display a tqdm progress bar across sources.

        Returns
        -------
        None
        """
        # __init__ already guarantees self._paper.doi is set.
        doi = self._paper.doi
        if doi is None:  # pragma: no cover: guarded by __init__ before this call
            return
        seed_key = self._paper._identity_key()

        sources: list[tuple[str, list[Paper]]] = []
        # (name, connector, fetch_fn) triples, evaluated lazily below so a
        # source's absence (not in self._active_databases) is a no-op.
        source_specs = (
            (Database.SEMANTIC_SCHOLAR.value, self._semantic_scholar, "fetch_related"),
            (Database.PUBMED.value, self._pubmed, "fetch_related"),
            (Database.OPENALEX.value, self._openalex, "fetch_related"),
        )
        active_specs = [spec for spec in source_specs if spec[1] is not None]

        progress = make_progress_bar(
            desc="similar", total=len(active_specs), unit="source", disable=not show_progress
        )
        try:
            for name, connector, method_name in active_specs:
                # PubMed's PMID resolution is done here (rather than left to
                # fetch_related) so we can distinguish skip from run, and the
                # resolved pmid is then passed straight through below: this
                # avoids a second, redundant esearch call against NCBI's
                # rate-limited endpoint for the same DOI.
                pubmed_pmid: str | None = None
                if name == Database.PUBMED.value:
                    pubmed_pmid = self._pubmed._resolve_pmid(doi)  # type: ignore[union-attr]
                    if pubmed_pmid is None:
                        logger.debug(
                            "similar: PubMed skipped (no PMID for DOI %s).", self._paper.doi
                        )
                        skipped_databases.append(name)
                        progress.update(1)
                        continue
                try:
                    if name == Database.PUBMED.value:
                        related = self._pubmed.fetch_related(  # type: ignore[union-attr]
                            self._paper, self._max_papers_per_database, pmid=pubmed_pmid
                        )
                    else:
                        related = getattr(connector, method_name)(
                            self._paper, self._max_papers_per_database
                        )
                except Exception:
                    logger.debug("similar: source %s failed.", name, exc_info=True)
                    failed_databases.append(name)
                    progress.update(1)
                    continue

                sources.append((name, related))
                progress.update(1)
        finally:
            progress.close()

        for name, related in sources:
            for candidate in related:
                key = candidate._identity_key()
                if key is None or key == seed_key:
                    continue
                candidate.add_database(name)
                if key in merged:
                    merged[key].merge(candidate)
                else:
                    merged[key] = candidate
                    order.append(key)
