"""SnowballRunner: discover papers via iterative citation snowballing.

Given one or more seed papers, this runner iteratively fetches their
references (backward) and/or citing papers (forward) by calling
:class:`~findpapers.runners.get_runner.GetRunner` for each DOI.  Each
:class:`~findpapers.core.paper.Paper` returned by the runner is already
enriched (metadata filled from multiple databases) and carries the
:attr:`~findpapers.core.paper.Paper.references` and
:attr:`~findpapers.core.paper.Paper.cited_by` lists that drive the BFS
expansion.  The result is a :class:`~findpapers.core.snowball_result.SnowballResult`
containing all discovered papers with citation relationships encoded on each
paper object.
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

# Default databases for the fast BFS discovery fetch.  CrossRef is chosen
# because it is unauthenticated, fast (10 req/s), and reliably provides
# backward-reference lists (paper.references) that drive BFS expansion.
SNOWBALL_DISCOVERY_DATABASES: list[str] = ["crossref"]

# Databases used when re-enriching seeds and frontier papers so that
# paper.references and paper.cited_by are populated from the best available
# sources.  Web scraping is excluded here and applied in a dedicated final
# pass instead, to avoid double-scraping frontier papers.
SNOWBALL_ENRICHMENT_DATABASES: list[str] = sorted(GET_DATABASES - {"web_scraping"})

# Databases used for the optional final enrichment pass that fills any
# remaining metadata gaps on surviving papers via HTML scraping.
SNOWBALL_WEBSCRAPING_DATABASES: list[str] = ["web_scraping"]


class SnowballRunner(DiscoveryRunner):
    """Discover papers around seed papers via iterative citation snowballing.

    For each paper in the current frontier the runner calls
    :class:`~findpapers.runners.get_runner.GetRunner` to obtain its full
    metadata together with populated
    :attr:`~findpapers.core.paper.Paper.references` (DOIs of papers it cites)
    and :attr:`~findpapers.core.paper.Paper.cited_by` (DOIs of papers that
    cite it).  New DOIs collected from these lists become the next frontier,
    and the process repeats up to *max_depth* levels.

    The runner uses a three-tier fetch strategy to minimise API calls
    while keeping result quality high:

    1. **BFS discovery** — candidate papers (found via references / cited_by)
       are fetched with *databases* (default: CrossRef only).  CrossRef is
       fast, unauthenticated, and reliably returns backward references.
    2. **Frontier enrichment** — papers that will drive the next BFS level
       are re-fetched with *enrichment_databases* (all API connectors by
       default) so that both ``paper.references`` *and* ``paper.cited_by``
       are fully populated before the next expansion round.
    3. **Final web-scraping pass** (optional) — after all BFS levels are
       complete, every surviving paper is re-enriched via HTML scraping to
       fill any metadata gaps (e.g. abstract, PDF URL, keywords) without
       burning extra API calls on papers that were later filtered out.

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
    max_per_level : int | None
        When set, only the *top-N* most-cited papers discovered at each
        level are kept in the final result.  Seed papers are never filtered.
        ``None`` (default) keeps all discovered papers.
    max_expansion_per_level : int | None
        When set, only the *top-N* most-cited papers from each level are
        used as seeds for the next BFS round.  Papers already added to the
        result are unaffected.  ``None`` (default) expands the full frontier.
    databases : list[str] | None
        Databases used for the fast BFS discovery of candidate papers.
        Defaults to ``["crossref"]`` for speed — CrossRef is unauthenticated
        and reliably returns backward references.  Pass ``None`` to use all
        available sources.  Accepted values: ``"arxiv"``, ``"crossref"``,
        ``"ieee"``, ``"openalex"``, ``"pubmed"``, ``"scopus"``,
        ``"semantic_scholar"``, ``"web_scraping"``.
    enrichment_databases : list[str] | None
        Databases used when re-fetching seed and frontier papers to populate
        ``paper.references`` and ``paper.cited_by`` for the next BFS round.
        Defaults to all API connectors (web scraping excluded).  Pass
        ``None`` to use the same default.  Pass a custom list to restrict
        which connectors are used for this enrichment phase.
    final_webscraping : bool
        When ``True`` (default), all papers that survive BFS filtering are
        re-enriched via HTML scraping at the end of the run to fill any
        remaining metadata gaps.  Set to ``False`` to skip this pass.
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
        max_per_level: int | None = None,
        max_expansion_per_level: int | None = None,
        databases: list[str] | None = _UNSET,  # type: ignore[assignment]
        enrichment_databases: list[str] | None = _UNSET,  # type: ignore[assignment]
        final_webscraping: bool = True,
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
        max_per_level : int | None
            Per-level result cap.  When set, only the top-N most-cited papers
            discovered at each BFS level are kept in the final result.  Seed
            papers are never filtered.  ``None`` means all papers are kept.
        max_expansion_per_level : int | None
            Per-level frontier cap.  When set, only the top-N most-cited papers
            from each level are used as seeds for the next BFS round.  Papers
            already added to the result are unaffected.  ``None`` means the
            full set of discovered papers drives the next level.
        databases : list[str] | None
            Databases used for the fast BFS discovery fetch.  When not
            provided, defaults to ``["crossref"]`` for speed.  Pass ``None``
            to use all available sources.
        enrichment_databases : list[str] | None
            Databases used when re-fetching seed and frontier papers to
            populate ``paper.references`` and ``paper.cited_by``.  When not
            provided, defaults to all API connectors (web scraping excluded).
            Pass ``None`` to use the same default.
        final_webscraping : bool
            When ``True`` (default), all surviving papers are re-enriched via
            HTML scraping at the end of the run.  Set to ``False`` to skip.
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
            If *max_depth* is less than 1, *max_per_level* is less than 1,
            *max_expansion_per_level* is less than 1,
            *databases* is an empty list, or *databases* contains unknown
            database identifiers.
        """
        if max_depth < 1:
            raise InvalidParameterError(f"max_depth must be >= 1, got {max_depth}")
        if max_per_level is not None and max_per_level < 1:
            raise InvalidParameterError(f"max_per_level must be >= 1 when set, got {max_per_level}")
        if max_expansion_per_level is not None and max_expansion_per_level < 1:
            raise InvalidParameterError(
                f"max_expansion_per_level must be >= 1 when set, got {max_expansion_per_level}"
            )

        # Apply defaults for the sentinel-based parameters.
        if databases is _UNSET:
            databases = list(SNOWBALL_DISCOVERY_DATABASES)
        if enrichment_databases is _UNSET or enrichment_databases is None:
            enrichment_databases = list(SNOWBALL_ENRICHMENT_DATABASES)

        def _validate_databases(value: list[str] | None, param_name: str) -> list[str] | None:
            """Validate and normalise a databases list parameter.

            Parameters
            ----------
            value : list[str] | None
                Raw value to validate.
            param_name : str
                Parameter name used in error messages.

            Returns
            -------
            list[str] | None
                Normalised (lowercase, stripped) list, or ``None``.

            Raises
            ------
            InvalidParameterError
                If the list is empty or contains unknown database names.
            """
            if value is None:
                return None
            if len(value) == 0:
                raise InvalidParameterError(
                    f"{param_name} must not be an empty list. "
                    "Pass None to use all available databases."
                )
            normalised = [db.strip().lower() for db in value]
            unknown = [db for db in normalised if db not in GET_DATABASES]
            if unknown:
                raise InvalidParameterError(
                    f"Unknown database(s) in {param_name}: {', '.join(unknown)}. "
                    f"Accepted values: {', '.join(sorted(GET_DATABASES))}"
                )
            return normalised

        databases = _validate_databases(databases, "databases")
        enrichment_databases = _validate_databases(enrichment_databases, "enrichment_databases")

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
        self._max_per_level = max_per_level
        self._max_expansion_per_level = max_expansion_per_level
        self._databases = databases
        self._enrichment_databases: list[str] = enrichment_databases  # type: ignore[assignment]
        self._final_webscraping = final_webscraping
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
            # Use enrichment databases for seeds since they ARE the initial
            # frontier — they need full metadata including cited_by.
            fetched_seeds = self._fetch_dois(
                seed_dois,
                databases=self._enrichment_databases,
                desc="Seeds",
                verbose=verbose,
                show_progress=show_progress,
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
            str(self._max_per_level) if self._max_per_level else "unlimited",
        )
        logger.debug("Discovery databases: %s", self._databases or "all")
        logger.debug("Enrichment databases: %s", self._enrichment_databases or "all")
        logger.debug("Final web scraping: %s", self._final_webscraping)
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

        # --- BFS levels 1 … max_depth ---
        for level in range(1, self._max_depth + 1):
            if not frontier:
                logger.debug("Level %d: empty frontier — stopping.", level)
                break

            frontier = self._process_bfs_level(
                level=level,
                frontier=frontier,
                visited=visited,
                all_papers=all_papers,
                verbose=verbose,
                show_progress=show_progress,
            )

        # --- Optional final web-scraping pass on all surviving papers ---
        if self._final_webscraping and all_papers:
            self._run_final_webscraping(all_papers, verbose=verbose, show_progress=show_progress)

        elapsed = perf_counter() - start

        logger.debug("=== Snowball Results ===")
        logger.debug("Total papers discovered: %d", len(all_papers))
        logger.debug("Runtime: %.2f s", elapsed)
        logger.debug("========================")

        _root_logger.setLevel(_saved_log_level)
        seed_dois: set[str] = {seed.doi.strip().lower() for seed in enriched_seeds if seed.doi}
        discovered_papers = [p for doi, p in all_papers.items() if doi not in seed_dois]

        return SnowballResult(
            seed_papers=enriched_seeds,
            max_depth=self._max_depth,
            direction=self._direction,
            since=self._since,
            until=self._until,
            databases=self._databases,
            max_per_level=self._max_per_level,
            max_expansion_per_level=self._max_expansion_per_level,
            papers=discovered_papers,
            processed_at=datetime.datetime.now(datetime.UTC),
            runtime_seconds=elapsed,
            skipped_seeds_without_doi=self._skipped_seeds,
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
        """Run one BFS level: discover, filter, store, and optionally enrich.

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

        fetched = self._fetch_dois(
            candidate_dois,
            databases=self._databases,
            desc=f"Level {level}/{self._max_depth}",
            verbose=verbose,
            show_progress=show_progress,
        )

        valid_papers = [p for p in fetched if self._matches_filters(p)]

        if self._max_per_level is not None:
            result_papers = sorted(valid_papers, key=lambda p: p.citations or 0, reverse=True)[
                : self._max_per_level
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
            f" (top {self._max_per_level} kept in result)" if self._max_per_level else "",
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

        if level < self._max_depth and expansion_base:
            return self._enrich_frontier(
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
            return runner.run(verbose=verbose)

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
        """Re-fetch frontier papers with full enrichment databases.

        Papers that will drive the next BFS round are re-fetched using
        *enrichment_databases* (all API connectors by default) so that both
        ``paper.references`` and ``paper.cited_by`` are populated.  The
        enriched versions replace their corresponding entries in *all_papers*.

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
            ``None`` fall back to their original (discovery-fetch) version.
        """
        dois = [p.doi for p in papers if p.doi]
        if not dois:
            return papers

        enriched_list = self._fetch_dois(
            dois,
            databases=self._enrichment_databases,
            desc=f"Level {level}/{self._max_depth} [enrichment]",
            verbose=verbose,
            show_progress=show_progress,
        )
        enriched_map: dict[str, Paper] = {}
        for p in enriched_list:
            if p.doi:
                norm = p.doi.strip().lower()
                enriched_map[norm] = p
                # Update all_papers with the richer version.
                if norm in all_papers:
                    all_papers[norm] = p

        # Return enriched papers; fall back to the original when not found.
        result: list[Paper] = []
        for p in papers:
            norm = p.doi.strip().lower()  # type: ignore[union-attr]
            result.append(enriched_map.get(norm, p))
        return result

    def _run_final_webscraping(
        self,
        all_papers: dict[str, Paper],
        *,
        verbose: bool,
        show_progress: bool,
    ) -> None:
        """Re-enrich all surviving papers via HTML scraping.

        Fetches each paper in *all_papers* using only the
        ``"web_scraping"`` connector.  For DOI-based identifiers GetRunner
        follows the ``https://doi.org/{doi}`` redirect and scrapes the
        publisher page.  Any extra metadata retrieved (abstract, PDF URL,
        keywords, etc.) is merged into the existing paper object in place.

        Parameters
        ----------
        all_papers : dict[str, Paper]
            Canonical result store; updated in place with scraped data.
        verbose : bool
            Forwarded to each :meth:`GetRunner.run` call.
        show_progress : bool
            Whether to display a tqdm progress bar.
        """
        dois = [p.doi for p in all_papers.values() if p.doi]
        if not dois:
            return

        logger.debug("Final web-scraping pass: %d papers.", len(dois))
        scraped = self._fetch_dois(
            dois,
            databases=SNOWBALL_WEBSCRAPING_DATABASES,
            desc="Final web scraping",
            verbose=verbose,
            show_progress=show_progress,
        )
        for scraped_paper in scraped:
            if scraped_paper.doi:
                norm = scraped_paper.doi.strip().lower()
                if norm in all_papers:
                    all_papers[norm].merge(scraped_paper)
