"""SimilarRunner: single-hop content-similarity lookup around a seed paper.

Given one seed paper, this runner queries each content-similarity source
(Semantic Scholar recommendations, PubMed related-articles, OpenAlex
related_works) and merges the results into a single deduplicated list.
Unlike :class:`~findpapers.runners.snowball_runner.SnowballRunner`, this is
a single-hop lookup: there is no BFS expansion.
"""

from __future__ import annotations

import logging
from time import perf_counter

from findpapers.connectors.openalex import OpenAlexConnector
from findpapers.connectors.pubmed import PubmedConnector
from findpapers.connectors.semantic_scholar import SemanticScholarConnector
from findpapers.core.paper import Database, Paper
from findpapers.core.similar_result import SimilarResult
from findpapers.exceptions import InvalidParameterError
from findpapers.utils.logging_config import configure_verbose_logging
from findpapers.utils.progress import make_progress_bar

logger = logging.getLogger(__name__)

# Sources supported for content-similarity lookup, in priority order.
# Semantic Scholar comes first (learned embeddings, best general fit),
# PubMed second (precise but biomedicine-only), OpenAlex last (cheap but
# coarser topic-tag-overlap signal).
SIMILAR_DATABASES: list[str] = ["semantic_scholar", "pubmed", "openalex"]


def _validate_similar_databases(value: list[str] | None) -> list[str]:
    """Validate and normalise the ``databases`` parameter for :class:`SimilarRunner`.

    Parameters
    ----------
    value : list[str] | None
        Raw value to validate.  ``None`` selects all of
        :data:`SIMILAR_DATABASES`.

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
        return list(SIMILAR_DATABASES)
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


class SimilarRunner:
    """Runner that finds content-similar papers around a single seed paper.

    Queries each configured source sequentially (in :data:`SIMILAR_DATABASES`
    priority order), merges results by identity (DOI, falling back to
    lowercased title) via :meth:`~findpapers.core.paper.Paper.merge`, and
    records per-paper provenance via
    :meth:`~findpapers.core.paper.Paper.add_database`.  A source failure is
    isolated and logged; it does not abort the other sources.

    All three sources are DOI-anchored: a seed paper without a DOI yields an
    empty result without any HTTP calls.

    Parameters
    ----------
    paper : Paper
        The seed paper to find related papers for.
    databases : list[str] | None
        Sources to consult, in priority order.  ``None`` (default) uses all
        of :data:`SIMILAR_DATABASES`.
    max_papers_per_database : int | None
        Cap on the number of related papers requested/kept from each source
        before merging.  ``None`` (default) lets each source's own natural
        default apply (Semantic Scholar: 100; PubMed: 100, a hard NCBI cap;
        OpenAlex: whatever short, fixed ``related_works`` list is embedded in
        the seed work, typically 10-20).
    email : str | None
        Unused by the three similarity sources today; accepted for interface
        symmetry with the other runners and forward compatibility.
    openalex_api_key : str | None
        OpenAlex API key.  Optional: increases the daily quota.
    semantic_scholar_api_key : str | None
        Semantic Scholar API key.  Optional: increases the rate limit.
    pubmed_api_key : str | None
        NCBI PubMed API key.  Optional: increases the rate limit.
    timeout : float | None
        HTTP request timeout in seconds.  ``None`` uses the ``requests``
        default.
    proxy : str | None
        Unused by the three similarity sources today (none perform HTML
        scraping); accepted for interface symmetry.
    ssl_verify : bool
        Whether to verify SSL certificates.  Defaults to ``True``.

    Raises
    ------
    InvalidParameterError
        If *databases* is an empty list or contains unknown database names.
    """

    def __init__(
        self,
        paper: Paper,
        *,
        databases: list[str] | None = None,
        max_papers_per_database: int | None = None,
        email: str | None = None,
        openalex_api_key: str | None = None,
        semantic_scholar_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        timeout: float | None = 10.0,
        proxy: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialise the runner with a seed paper and connection settings.

        See the class docstring for parameter descriptions.

        Raises
        ------
        InvalidParameterError
            If *databases* is an empty list or contains unknown database
            names.
        """
        self._paper = paper
        self._active_databases = _validate_similar_databases(databases)
        self._requested_databases = databases
        self._max_papers_per_database = max_papers_per_database

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
            deduplicated related papers.
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
            if not self._paper.doi:
                logger.debug("similar: seed paper has no DOI, skipping all sources.")
                skipped_databases = list(self._active_databases)
            else:
                self._run_sources(merged, order, failed_databases, skipped_databases, show_progress)
        finally:
            for connector in (self._semantic_scholar, self._pubmed, self._openalex):
                if connector is not None:
                    connector.close()

        result = SimilarResult(
            seed_paper=self._paper,
            databases=self._requested_databases,
            max_papers_per_database=self._max_papers_per_database,
            papers=[merged[key] for key in order],
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
        # run() only calls this method after confirming self._paper.doi is set.
        doi = self._paper.doi
        if doi is None:  # pragma: no cover: guarded by run() before this call
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
                if name == Database.PUBMED.value:
                    pmid = self._pubmed._resolve_pmid(doi)  # type: ignore[union-attr]
                    if pmid is None:
                        logger.debug(
                            "similar: PubMed skipped (no PMID for DOI %s).", self._paper.doi
                        )
                        skipped_databases.append(name)
                        progress.update(1)
                        continue
                try:
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
