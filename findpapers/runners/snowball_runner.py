"""SnowballRunner: discover papers via iterative citation snowballing.

Given one or more seed papers, this runner iteratively fetches their
references (backward) and/or citing papers (forward).  The result is a
:class:`~findpapers.core.snowball_result.SnowballResult` containing all
discovered papers with citation relationships encoded on each paper object.
"""

from __future__ import annotations

import datetime
import logging
from time import perf_counter
from typing import Literal

from findpapers.core.paper import Paper
from findpapers.core.snowball_result import SnowballResult
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.discovery_runner import DiscoveryRunner
from findpapers.runners.get_runner import GET_DATABASES, GetRunner
from findpapers.utils.logging_config import configure_verbose_logging
from findpapers.utils.parallel import execute_tasks

logger = logging.getLogger(__name__)

# Sentinel used to distinguish "argument not passed" from explicit None.
_UNSET: object = object()

# Databases supported for snowball traversal.  Only these three can populate
# paper.references (backward) and paper.cited_by (forward), which are required
# for BFS expansion.
SNOWBALL_DATABASES: list[str] = ["crossref", "openalex", "semantic_scholar"]

# Default databases for backward-direction BFS discovery.  CrossRef is chosen
# because it is unauthenticated, fast (10 req/s), and reliably provides
# backward-reference lists (paper.references).
SNOWBALL_DISCOVERY_DATABASES: list[str] = ["crossref"]

# Default databases for the final enrichment pass on non-seed papers after
# all BFS levels and filters are applied.  CrossRef provides structured
# metadata; web_scraping fills remaining gaps (abstract, PDF URL, etc.).
SNOWBALL_ENRICHMENT_DATABASES: list[str] = ["crossref", "web_scraping"]

# Databases capable of returning forward citation data (paper.cited_by).
_FORWARD_CAPABLE_DATABASES: frozenset[str] = frozenset({"openalex", "semantic_scholar"})


def _validate_snowball_databases(value: list[str], param_name: str) -> list[str]:
    """Validate and normalise a snowball discovery databases list.

    Parameters
    ----------
    value : list[str]
        Raw value to validate.
    param_name : str
        Parameter name used in error messages.

    Returns
    -------
    list[str]
        Normalised (lowercase, stripped) list.

    Raises
    ------
    InvalidParameterError
        If the list is empty or contains unsupported database names.
    """
    if len(value) == 0:
        raise InvalidParameterError(
            f"{param_name} must not be an empty list. Pass None to use the default databases."
        )
    normalised = [db.strip().lower() for db in value]
    unknown = [db for db in normalised if db not in SNOWBALL_DATABASES]
    if unknown:
        raise InvalidParameterError(
            f"Unknown or unsupported database(s) in {param_name}: "
            f"{', '.join(unknown)}. "
            f"Accepted values: {', '.join(sorted(SNOWBALL_DATABASES))}"
        )
    return normalised


def _validate_snowball_enrichment_databases(value: list[str], param_name: str) -> list[str]:
    """Validate and normalise a snowball enrichment databases list.

    Parameters
    ----------
    value : list[str]
        Raw value to validate.
    param_name : str
        Parameter name used in error messages.

    Returns
    -------
    list[str]
        Normalised (lowercase, stripped) list, or an empty list when
        *value* is empty (signals "disable enrichment").

    Raises
    ------
    InvalidParameterError
        If the list contains unknown database names.
    """
    if len(value) == 0:
        return []
    normalised = [db.strip().lower() for db in value]
    unknown = [db for db in normalised if db not in GET_DATABASES]
    if unknown:
        raise InvalidParameterError(
            f"Unknown database(s) in {param_name}: {', '.join(unknown)}. "
            f"Accepted values: {', '.join(sorted(GET_DATABASES))}"
        )
    return normalised


def _validate_snowball_scalar_params(
    max_depth: int,
    max_papers_per_level: int | None,
    max_expansion_per_level: int | None,
    max_cited_by: int | None,
    direction: str,
) -> None:
    """Validate scalar SnowballRunner init parameters and emit warnings.

    Parameters
    ----------
    max_depth : int
        Must be >= 1.
    max_papers_per_level : int | None
        Must be >= 1 when set.
    max_expansion_per_level : int | None
        Must be >= 1 when set.
    max_cited_by : int | None
        Must be >= 1 when set.  Warning emitted when ``None`` or > 100
        and direction includes forward expansion.
    direction : str
        Snowball direction (``"both"``, ``"backward"``, or ``"forward"``).

    Raises
    ------
    InvalidParameterError
        If any parameter is out of range.
    """
    if max_depth < 1:
        raise InvalidParameterError(f"max_depth must be >= 1, got {max_depth}")
    if max_papers_per_level is not None and max_papers_per_level < 1:
        raise InvalidParameterError(
            f"max_papers_per_level must be >= 1 when set, got {max_papers_per_level}"
        )
    if max_expansion_per_level is not None and max_expansion_per_level < 1:
        raise InvalidParameterError(
            f"max_expansion_per_level must be >= 1 when set, got {max_expansion_per_level}"
        )
    if max_cited_by is not None and max_cited_by < 1:
        raise InvalidParameterError(f"max_cited_by must be >= 1 when set, got {max_cited_by}")
    if direction in ("forward", "both") and (max_cited_by is None or max_cited_by > 100):
        logger.warning(
            "max_cited_by is %s. Fetching cited-by may be very slow or produce "
            "large lists for highly-cited papers (forward/both direction). "
            "Consider setting max_cited_by <= 100.",
            max_cited_by if max_cited_by is not None else "None (unlimited)",
        )


class SnowballRunner(DiscoveryRunner):
    """Discover papers around seed papers via iterative citation snowballing.

    Starting from one or more seed papers, the runner iteratively collects
    new DOIs from each paper's :attr:`~findpapers.core.paper.Paper.references`
    and/or :attr:`~findpapers.core.paper.Paper.cited_by` lists up to
    *max_depth* BFS levels.

    Seed papers and frontier papers (those driving the next BFS level) are
    fetched with the combined set of *databases* and *enrichment_databases*
    so they carry full metadata, including ``paper.cited_by``, before each
    expansion round.  Papers discovered during BFS are fetched with
    ``crossref`` only: this is fast and sufficient to populate
    ``paper.references`` for the next round.  After all BFS levels complete
    and date filters are applied, the surviving non-seed papers are
    re-enriched with the databases in *enrichment_databases* that were not
    already used (i.e., those not in *databases*).

    Only ``"crossref"``, ``"openalex"``, and ``"semantic_scholar"`` are valid
    for *databases*: these are the only sources that populate
    ``paper.references`` and ``paper.cited_by`` for BFS expansion.
    Forward direction (``"forward"`` or ``"both"``) requires at least one
    of ``"openalex"`` or ``"semantic_scholar"`` in *databases*.

    Parameters
    ----------
    seed_papers : list[Paper] | Paper
        One or more papers to start the snowball from.  Papers without a
        DOI are silently skipped.
    max_depth : int
        Maximum number of BFS levels.  ``1`` (default) fetches only the
        immediate neighbours of seed papers.
    direction : Literal["both", "backward", "forward"]
        ``"backward"`` follows :attr:`~findpapers.core.paper.Paper.references`
        (papers cited *by* the current frontier),
        ``"forward"`` follows :attr:`~findpapers.core.paper.Paper.cited_by`
        (papers that *cite* the current frontier),
        ``"both"`` expands in both directions.
    max_papers_per_level : int | None
        When set, only the *top-N* most-cited papers discovered at each
        level are kept in the final result.  Seed papers are never filtered.
        ``None`` (default) keeps all discovered papers.
    max_expansion_per_level : int | None
        When set, only the *top-N* most-cited papers from each level are
        used as seeds for the next BFS round.  Papers already added to the
        result are unaffected.  ``None`` (default) expands the full frontier.
    databases : list[str] | None
        Databases used to enrich seeds and frontier papers.  Only
        ``"crossref"``, ``"openalex"``, and ``"semantic_scholar"`` are
        accepted.  BFS discovery always uses ``crossref`` regardless of
        this value.  Defaults to ``["crossref"]`` for backward direction,
        or all three databases for ``"forward"``/``"both"`` direction.
        Pass ``None`` to use all three databases.
    enrichment_databases : list[str] | None
        Databases used to enrich non-seed papers after all BFS levels and
        filters are applied.  Databases already used in discovery are
        skipped (they were already fetched).  Defaults to
        ``["crossref", "web_scraping"]``.  ``None`` uses the default.
        Pass ``[]`` to disable enrichment entirely.  Accepted values:
        ``"arxiv"``, ``"crossref"``, ``"ieee"``, ``"openalex"``,
        ``"pubmed"``, ``"scopus"``, ``"semantic_scholar"``,
        ``"web_scraping"``, ``"wos"``.
    num_workers : int
        Number of parallel :class:`~findpapers.runners.get_runner.GetRunner`
        calls to make per level.  Defaults to ``1`` (sequential).
    since : datetime.date | None
        Only include discovered papers published on or after this date.
        Seed papers are never filtered.  ``None`` disables the filter.
    until : datetime.date | None
        Only include discovered papers published on or before this date.
        Seed papers are never filtered.  ``None`` disables the filter.
    openalex_api_key : str | None
        OpenAlex API key.
    email : str | None
        Contact email for polite-pool access (OpenAlex, CrossRef).
    semantic_scholar_api_key : str | None
        Semantic Scholar API key.
    ieee_api_key : str | None
        IEEE Xplore API key.
    scopus_api_key : str | None
        Elsevier / Scopus API key.
    pubmed_api_key : str | None
        NCBI PubMed API key.
    wos_api_key : str | None
        Clarivate Web of Science API key.
    proxy : str | None
        Optional HTTP/HTTPS proxy URL for all requests.
    ssl_verify : bool
        Whether to verify SSL certificates.  Defaults to ``True``.
    """

    def __init__(
        self,
        seed_papers: list[Paper] | Paper,
        *,
        max_depth: int = 1,
        direction: Literal["both", "backward", "forward"] = "both",
        max_papers_per_level: int | None = None,
        max_expansion_per_level: int | None = None,
        max_cited_by: int | None = 100,
        databases: list[str] | None = _UNSET,  # type: ignore[assignment]
        enrichment_databases: list[str] | None = _UNSET,  # type: ignore[assignment]
        num_workers: int = 1,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
        openalex_api_key: str | None = None,
        email: str | None = None,
        semantic_scholar_api_key: str | None = None,
        ieee_api_key: str | None = None,
        scopus_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        wos_api_key: str | None = None,
        proxy: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialise snowball configuration without executing it.

        Parameters
        ----------
        seed_papers : list[Paper] | Paper
            One or more seed papers.
        max_depth : int
            Maximum BFS depth.  Must be >= 1.
        direction : Literal["both", "backward", "forward"]
            Snowball direction(s).
        max_papers_per_level : int | None
            Per-level result cap.  When set, only the top-N most-cited papers
            discovered at each BFS level are kept in the final result.  Seed
            papers are never filtered.  ``None`` means all papers are kept.
        max_expansion_per_level : int | None
            Per-level frontier cap.  When set, only the top-N most-cited papers
            from each level are used as seeds for the next BFS round.  Papers
            already added to the result are unaffected.  ``None`` means the
            full set of discovered papers drives the next level.
        max_cited_by : int | None
            Maximum number of citing-paper DOIs collected per paper when
            populating ``paper.cited_by`` during seed and frontier enrichment.
            Defaults to ``100``.  ``None`` means no limit: use with caution as
            highly-cited classic papers may have thousands of citations.
            A warning is emitted when this value is ``None`` or greater than ``100``.
        databases : list[str] | None
            Databases used to enrich seeds and frontier papers.  Only
            ``"crossref"``, ``"openalex"``, and ``"semantic_scholar"`` are
            accepted.  BFS discovery always uses ``crossref`` regardless of
            this value.  When not provided, defaults to ``["crossref"]`` for
            backward direction or all three databases for forward/both
            direction.  Pass ``None`` to use all three databases.
        enrichment_databases : list[str] | None
            Databases used to enrich non-seed papers after BFS completes.
            When not provided or ``None``, defaults to
            ``["crossref", "web_scraping"]``.  Pass ``[]`` to disable
            enrichment entirely.  Accepted values: ``"arxiv"``,
            ``"crossref"``, ``"ieee"``, ``"openalex"``, ``"pubmed"``,
            ``"scopus"``, ``"semantic_scholar"``, ``"web_scraping"``,
            ``"wos"``.
        num_workers : int
            Number of parallel GetRunner calls per level.
        since : datetime.date | None
            Lower-bound publication date filter for discovered papers.
        until : datetime.date | None
            Upper-bound publication date filter for discovered papers.
        openalex_api_key : str | None
            OpenAlex API key.
        email : str | None
            Contact email for polite-pool access.
        semantic_scholar_api_key : str | None
            Semantic Scholar API key.
        ieee_api_key : str | None
            IEEE Xplore API key.
        scopus_api_key : str | None
            Scopus API key.
        pubmed_api_key : str | None
            PubMed API key.
        wos_api_key : str | None
            Web of Science API key.
        proxy : str | None
            Optional proxy URL.
        ssl_verify : bool
            Whether to verify SSL certificates.

        Raises
        ------
        InvalidParameterError
            If *max_depth* is less than 1, *max_papers_per_level* is less than 1,
            *max_expansion_per_level* is less than 1, *databases* is an
            empty list, *databases* contains unsupported database identifiers,
            or the declared *direction* cannot be satisfied by *databases*
            (e.g. ``"forward"`` with only ``"crossref"``).
        """
        _validate_snowball_scalar_params(
            max_depth, max_papers_per_level, max_expansion_per_level, max_cited_by, direction
        )

        # Apply defaults for the sentinel-based parameters.
        if databases is _UNSET:
            # For forward or both directions, all snowball databases are needed;
            # for backward-only, CrossRef alone is sufficient.
            if direction == "backward":
                databases = list(SNOWBALL_DISCOVERY_DATABASES)
            else:
                databases = list(SNOWBALL_DATABASES)
        elif databases is None:
            databases = list(SNOWBALL_DATABASES)

        if enrichment_databases is _UNSET or enrichment_databases is None:
            enrichment_databases = list(SNOWBALL_ENRICHMENT_DATABASES)

        databases = _validate_snowball_databases(databases, "databases")
        enrichment_databases = _validate_snowball_enrichment_databases(
            enrichment_databases, "enrichment_databases"
        )

        # Validate that the declared databases can satisfy the requested direction.
        # CrossRef only supports backward references; forward requires OpenAlex or
        # Semantic Scholar.
        if direction in ("forward", "both") and not any(
            db in _FORWARD_CAPABLE_DATABASES for db in databases
        ):
            raise InvalidParameterError(
                f"Direction '{direction}' requires at least one forward-capable database "
                f"({', '.join(sorted(_FORWARD_CAPABLE_DATABASES))}), "
                f"but databases={databases!r}. "
                "Add 'openalex' or 'semantic_scholar' to the databases list."
            )

        # DiscoveryRunner handles shared credentials and date filters.
        # enrichment_databases=[] because GetRunner is invoked directly here.
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
            enrichment_databases=[],
        )

        if isinstance(seed_papers, Paper):
            seed_papers = [seed_papers]

        self._seed_papers = [p for p in seed_papers if p.doi]
        self._skipped_seeds = len(seed_papers) - len(self._seed_papers)
        self._max_depth = max_depth
        self._direction = direction
        self._max_papers_per_level = max_papers_per_level
        self._max_expansion_per_level = max_expansion_per_level
        self._max_cited_by = max_cited_by
        self._databases = databases
        self._enrichment_databases: list[str] = enrichment_databases
        self._num_workers = max(num_workers, 1)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def _process_seed_papers(
        self,
        visited: set[str],
        verbose: bool,
        show_progress: bool,
    ) -> list[Paper]:
        """Fetch and enrich level-0 seed papers, returning them as the initial frontier.

        Seeds are the first BFS frontier, so they are fetched with the full
        *enrichment_databases* set (all API connectors) to ensure that both
        ``paper.references`` and ``paper.cited_by`` are populated before the
        first expansion round.

        Parameters
        ----------
        visited : set[str]
            Already-seen normalised DOIs.  Updated in place with seed DOIs.
        verbose : bool
            Enable verbose logging.
        show_progress : bool
            Show tqdm progress bars.

        Returns
        -------
        list[Paper]
            Enriched seed papers to be used as the initial BFS frontier.
            Seeds for which GetRunner returned nothing are included as-is.
        """
        seed_dois = [p.doi for p in self._seed_papers if p.doi]
        enriched: dict[str, Paper] = {}
        if seed_dois:
            # Seeds are enriched with all available databases: both the
            # discovery set and the enrichment set: to ensure full metadata
            # (including references and cited_by) before the first BFS round.
            seed_databases = sorted(set(self._databases + self._enrichment_databases))
            fetched_seeds = self._fetch_dois(
                seed_dois,
                databases=seed_databases,
                desc="Seeds",
                verbose=verbose,
                show_progress=False,
                max_cited_by=self._max_cited_by,
            )
            for paper in fetched_seeds:
                if paper.doi:
                    enriched[paper.doi.strip().lower()] = paper

        # Seeds for which GetRunner returned nothing are included as-is.
        for seed in self._seed_papers:
            norm = seed.doi.strip().lower()  # type: ignore[union-attr]
            if norm not in enriched:
                enriched[norm] = seed

        return list(enriched.values())

    def _collect_candidate_dois(self, frontier: list[Paper], visited: set[str]) -> list[str]:
        """Collect new candidate DOIs from *frontier* based on the configured direction.

        Mutates *visited* to mark each returned DOI as seen.

        Parameters
        ----------
        frontier : list[Paper]
            Papers in the current expansion frontier.
        visited : set[str]
            Normalised DOIs already scheduled or processed.

        Returns
        -------
        list[str]
            Deduplicated list of new DOIs to fetch in the next level.
        """
        candidate_dois: list[str] = []
        seen_this_batch: set[str] = set()
        for paper in frontier:
            if self._direction in ("both", "backward"):
                for doi in paper.references:
                    norm = doi.strip().lower()
                    if norm not in visited and norm not in seen_this_batch:
                        candidate_dois.append(doi)
                        seen_this_batch.add(norm)
                        visited.add(norm)
            if self._direction in ("both", "forward"):
                for doi in paper.cited_by:
                    norm = doi.strip().lower()
                    if norm not in visited and norm not in seen_this_batch:
                        candidate_dois.append(doi)
                        seen_this_batch.add(norm)
                        visited.add(norm)
        return candidate_dois

    def run(self, verbose: bool = False, show_progress: bool = True) -> SnowballResult:
        """Execute the snowball and return the result.

        Can be called multiple times; each call is independent.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging.
        show_progress : bool
            When ``True`` (default), display tqdm progress bars for each
            snowball level.  Set to ``False`` to suppress progress output.

        Returns
        -------
        SnowballResult
            Container with all discovered papers (including seeds).
            Citation relationships are encoded on each paper via
            :attr:`~findpapers.core.paper.Paper.references` and
            :attr:`~findpapers.core.paper.Paper.cited_by`.
        """
        _root_logger = logging.getLogger()
        _saved_log_level = _root_logger.level
        if verbose:
            configure_verbose_logging()

        logger.debug("=== SnowballRunner Configuration ===")
        logger.debug(
            "Seed papers: %d (skipped %d without DOI)",
            len(self._seed_papers),
            self._skipped_seeds,
        )
        logger.debug("Max depth: %d", self._max_depth)
        logger.debug("Direction: %s", self._direction)
        logger.debug(
            "Top N per level: %s",
            str(self._max_papers_per_level) if self._max_papers_per_level else "unlimited",
        )
        logger.debug("Discovery databases: %s", self._databases or "all")
        logger.debug("Enrichment databases: %s", self._enrichment_databases or "all")
        logger.debug("Num workers: %d", self._num_workers)
        logger.debug("=====================================")

        start = perf_counter()

        # visited: normalized DOIs already fetched or scheduled.
        visited: set[str] = {p.doi.strip().lower() for p in self._seed_papers}  # type: ignore[union-attr]

        # all_papers: canonical paper objects keyed by normalized DOI (seeds included).
        all_papers: dict[str, Paper] = {}

        # --- Level 0: fetch/enrich seed papers using full enrichment databases ---
        enriched_seeds = self._process_seed_papers(visited, verbose, show_progress)

        # Add enriched seeds to all_papers so they participate in the final
        # web-scraping pass and are available for any post-processing.
        for seed in enriched_seeds:
            if seed.doi:
                all_papers[seed.doi.strip().lower()] = seed

        frontier: list[Paper] = enriched_seeds

        # --- BFS levels 1 ... max_depth ---
        for level in range(1, self._max_depth + 1):
            if not frontier:
                logger.debug("Level %d: empty frontier: stopping.", level)
                break

            frontier = self._process_bfs_level(
                level=level,
                frontier=frontier,
                visited=visited,
                all_papers=all_papers,
                verbose=verbose,
                show_progress=show_progress,
            )

        # --- Final enrichment of non-seed papers ---
        seed_dois: set[str] = {seed.doi.strip().lower() for seed in enriched_seeds if seed.doi}
        if all_papers:
            self._run_final_enrichment(
                all_papers, seed_dois, verbose=verbose, show_progress=show_progress
            )

        elapsed = perf_counter() - start

        logger.debug("=== Snowball Results ===")
        logger.debug("Total papers discovered: %d", len(all_papers))
        logger.debug("Runtime: %.2f s", elapsed)
        logger.debug("========================")

        _root_logger.setLevel(_saved_log_level)
        discovered_papers = [p for doi, p in all_papers.items() if doi not in seed_dois]

        return SnowballResult(
            seed_papers=enriched_seeds,
            max_depth=self._max_depth,
            direction=self._direction,
            since=self._since,
            until=self._until,
            databases=self._databases,
            max_papers_per_level=self._max_papers_per_level,
            max_expansion_per_level=self._max_expansion_per_level,
            papers=discovered_papers,
            processed_at=datetime.datetime.now(datetime.UTC),
            runtime_seconds=elapsed,
            skipped_seeds_without_doi=self._skipped_seeds,
            enrichment_databases=list(self._enrichment_databases),
            max_cited_by=self._max_cited_by,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_bfs_level(
        self,
        *,
        level: int,
        frontier: list[Paper],
        visited: set[str],
        all_papers: dict[str, Paper],
        verbose: bool,
        show_progress: bool,
    ) -> list[Paper]:
        """Run one BFS level: discover, filter, store, and enrich the next frontier.

        Parameters
        ----------
        level : int
            Current BFS level (1-based).
        frontier : list[Paper]
            Papers whose citation lists drive this level's expansion.
        visited : set[str]
            Normalised DOIs already scheduled or processed; mutated in place.
        all_papers : dict[str, Paper]
            Canonical result store; updated in place with new papers.
        verbose : bool
            Forwarded to each :meth:`GetRunner.run` call.
        show_progress : bool
            Whether to display a tqdm progress bar.

        Returns
        -------
        list[Paper]
            The frontier to use for the next BFS level.  Returns an empty list
            when there are no more candidates to expand.
        """
        candidate_dois = self._collect_candidate_dois(frontier, visited)

        logger.debug(
            "Level %d/%d: %d candidate DOIs from %d frontier papers.",
            level,
            self._max_depth,
            len(candidate_dois),
            len(frontier),
        )

        if not candidate_dois:
            return []

        # BFS discovery always uses only CrossRef: it is fast, unauthenticated,
        # and provides paper.references for expansion.  openalex and
        # semantic_scholar are reserved for seed/frontier enrichment so that
        # the richer (but slower) APIs are called only on papers that actually
        # drive the next BFS level.
        fetched = self._fetch_dois(
            candidate_dois,
            databases=SNOWBALL_DISCOVERY_DATABASES,
            desc=f"Level {level}/{self._max_depth}",
            verbose=verbose,
            show_progress=show_progress,
        )

        valid_papers = [p for p in fetched if self._matches_filters(p)]

        if self._max_papers_per_level is not None:
            result_papers = sorted(valid_papers, key=lambda p: p.citations or 0, reverse=True)[
                : self._max_papers_per_level
            ]
        else:
            result_papers = valid_papers

        for p in result_papers:
            if p.doi:
                norm = p.doi.strip().lower()
                if norm not in all_papers:
                    all_papers[norm] = p

        logger.debug(
            "Level %d/%d complete: %d/%d papers passed date filters%s%s.",
            level,
            self._max_depth,
            len(valid_papers),
            len(fetched),
            f" (top {self._max_papers_per_level} kept in result)"
            if self._max_papers_per_level
            else "",
            f" (top {self._max_expansion_per_level} used for expansion)"
            if self._max_expansion_per_level
            else "",
        )

        if self._max_expansion_per_level is not None:
            expansion_base = sorted(valid_papers, key=lambda p: p.citations or 0, reverse=True)[
                : self._max_expansion_per_level
            ]
        else:
            expansion_base = valid_papers

        # Re-enrich frontier papers before the next BFS round so that
        # paper.references and paper.cited_by are fully populated.
        # Skipped at the last level since there is no further expansion.
        if level < self._max_depth and expansion_base:
            expansion_base = self._enrich_frontier(
                expansion_base,
                level=level,
                all_papers=all_papers,
                verbose=verbose,
                show_progress=show_progress,
            )

        return expansion_base

    def _fetch_dois(
        self,
        dois: list[str],
        databases: list[str] | None,
        *,
        desc: str,
        verbose: bool,
        show_progress: bool,
        max_cited_by: int | None = None,
    ) -> list[Paper]:
        """Fetch papers for a list of DOIs using GetRunner.

        Each DOI is resolved via a separate
        :class:`~findpapers.runners.get_runner.GetRunner` call.  When
        *num_workers* is greater than 1, calls are made in parallel.

        Parameters
        ----------
        dois : list[str]
            DOI strings to fetch.
        databases : list[str] | None
            Database filter passed to each :class:`GetRunner`.  ``None``
            means all available sources.
        desc : str
            Human-readable label for the tqdm progress bar.
        verbose : bool
            Forwarded to each :meth:`GetRunner.run` call.
        show_progress : bool
            Whether to display a tqdm progress bar.
        max_cited_by : int | None
            Forwarded to :meth:`GetRunner.run` to cap cited-by pagination.
            ``None`` means no limit.

        Returns
        -------
        list[Paper]
            Successfully fetched papers (DOIs that returned ``None`` from
            GetRunner are silently skipped).
        """
        ieee_api_key = self._ieee_api_key
        scopus_api_key = self._scopus_api_key
        pubmed_api_key = self._pubmed_api_key
        openalex_api_key = self._openalex_api_key
        email = self._email
        semantic_scholar_api_key = self._semantic_scholar_api_key
        wos_api_key = self._wos_api_key
        proxy = self._proxy
        ssl_verify = self._ssl_verify

        def _fetch_task(doi: str) -> Paper | None:
            """Fetch a single paper by DOI via GetRunner.

            Parameters
            ----------
            doi : str
                DOI to fetch.

            Returns
            -------
            Paper | None
                Fetched paper, or ``None`` if not found.
            """
            runner = GetRunner(
                identifier=doi,
                email=email,
                databases=databases,
                ieee_api_key=ieee_api_key,
                scopus_api_key=scopus_api_key,
                pubmed_api_key=pubmed_api_key,
                openalex_api_key=openalex_api_key,
                semantic_scholar_api_key=semantic_scholar_api_key,
                wos_api_key=wos_api_key,
                proxy=proxy,
                ssl_verify=ssl_verify,
            )
            return runner.run(verbose=verbose, max_cited_by=max_cited_by)

        results: list[Paper] = []
        for doi, result, error in execute_tasks(
            dois,
            _fetch_task,
            num_workers=self._num_workers,
            timeout=None,
            progress_total=len(dois),
            progress_unit="paper",
            progress_desc=desc,
            use_progress=show_progress,
        ):
            if error is not None:
                logger.warning("Failed to fetch DOI '%s': %s", doi, error)
            elif result is not None:
                results.append(result)
        return results

    def _enrich_frontier(
        self,
        papers: list[Paper],
        *,
        level: int,
        all_papers: dict[str, Paper],
        verbose: bool,
        show_progress: bool,
    ) -> list[Paper]:
        """Re-enrich frontier papers with the full combined set of databases.

        Papers that will drive the next BFS round are re-fetched using the
        union of *databases* and *enrichment_databases*, the same strategy
        applied to level-0 seeds.  This ensures that ``paper.references`` and
        ``paper.cited_by`` are fully populated before the next expansion.

        The enriched versions replace their entries in *all_papers* in place.

        Parameters
        ----------
        papers : list[Paper]
            Frontier papers to re-enrich.
        level : int
            Current BFS level (used in the progress bar label).
        all_papers : dict[str, Paper]
            Canonical result store; updated in place with enriched versions.
        verbose : bool
            Forwarded to each :meth:`GetRunner.run` call.
        show_progress : bool
            Whether to display a tqdm progress bar.

        Returns
        -------
        list[Paper]
            Enriched frontier papers.  Papers for which enrichment returned
            nothing fall back to their original (discovery-fetch) version.
        """
        dois = [p.doi for p in papers if p.doi]
        if not dois:
            return papers

        frontier_databases = sorted(set(self._databases + self._enrichment_databases))
        enriched_list = self._fetch_dois(
            dois,
            databases=frontier_databases,
            desc=f"Level {level}/{self._max_depth} [enrichment]",
            verbose=verbose,
            show_progress=show_progress,
            max_cited_by=self._max_cited_by,
        )
        enriched_map: dict[str, Paper] = {}
        for p in enriched_list:
            if p.doi:
                norm = p.doi.strip().lower()
                enriched_map[norm] = p
                if norm in all_papers:
                    all_papers[norm] = p

        return [enriched_map.get(p.doi.strip().lower(), p) for p in papers]  # type: ignore[union-attr]

    def _run_final_enrichment(
        self,
        all_papers: dict[str, Paper],
        seed_dois: set[str],
        *,
        verbose: bool,
        show_progress: bool,
    ) -> None:
        """Re-enrich non-seed papers with enrichment-only databases.

        After all BFS levels and filters are applied, papers that were
        discovered during BFS have only been fetched with the discovery
        databases.  This method enriches them with the databases declared in
        *enrichment_databases* that were **not** already used during
        discovery, avoiding redundant API calls.

        Seed papers are excluded because they were already enriched with the
        full combined set at the start.

        Parameters
        ----------
        all_papers : dict[str, Paper]
            Canonical result store; updated in place with enriched data.
        seed_dois : set[str]
            Normalised DOIs of seed papers to exclude from enrichment.
        verbose : bool
            Forwarded to each :meth:`GetRunner.run` call.
        show_progress : bool
            Whether to display a tqdm progress bar.
        """
        # Only use databases that haven't already been used in BFS discovery.
        discovery_dbs = set(self._databases)
        enrichment_only_dbs = [db for db in self._enrichment_databases if db not in discovery_dbs]
        if not enrichment_only_dbs:
            return

        non_seed_dois = [p.doi for doi, p in all_papers.items() if doi not in seed_dois and p.doi]
        if not non_seed_dois:
            return

        logger.debug(
            "Final enrichment pass: %d non-seed papers, databases: %s",
            len(non_seed_dois),
            enrichment_only_dbs,
        )
        enriched = self._fetch_dois(
            non_seed_dois,
            databases=enrichment_only_dbs,
            desc="Enrichment",
            verbose=verbose,
            show_progress=show_progress,
            max_cited_by=self._max_cited_by,
        )
        for enriched_paper in enriched:
            if enriched_paper.doi:
                norm = enriched_paper.doi.strip().lower()
                if norm in all_papers:
                    all_papers[norm].merge(enriched_paper)
