"""SnowballRunner: build a citation graph via forward/backward snowballing.

Given one or more seed papers, this runner iteratively fetches their
references (backward) and citing papers (forward) up to a configurable
depth, producing a :class:`~findpapers.core.citation_graph.CitationGraph`.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Literal

from tqdm import tqdm

from findpapers.connectors import CITATION_REGISTRY
from findpapers.connectors.citation_base import CitationConnectorBase
from findpapers.core.citation_graph import CitationGraph
from findpapers.core.paper import Database, Paper
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.discovery_runner import DEFAULT_ENRICHMENT_DATABASES, DiscoveryRunner
from findpapers.utils.logging_config import configure_verbose_logging
from findpapers.utils.progress import make_progress_bar

logger = logging.getLogger(__name__)


class SnowballRunner(DiscoveryRunner):
    """Build a citation graph around seed papers via iterative snowballing.

    The runner traverses the citation network in a BFS fashion: at each
    depth level it collects references and/or citing papers for every paper
    in the current frontier, adds the new papers as nodes to the graph, and
    records directed edges (``source`` → ``target`` meaning *source cites
    target*).

    Parameters
    ----------
    seed_papers : list[Paper] | Paper
        One or more papers to start the snowball from.  Papers without a
        DOI are silently skipped (they cannot be resolved by the APIs).
    max_depth : int
        Maximum number of snowball iterations.  ``1`` (the default)
        retrieves only the immediate neighbours of seed papers.
    direction : Literal["both", "backward", "forward"]
        ``"backward"`` fetches references (papers cited *by* the seed),
        ``"forward"`` fetches citing papers (papers that *cite* the seed),
        ``"both"`` fetches in both directions.
    top_n_per_level : int | None
        When set, only the *top N* most-cited papers discovered at each
        snowball level are kept as candidates for expansion in the next
        level.  Seed papers are always expanded regardless of this limit.
        This is useful for controlling cost when running deep snowballs:
        setting a small value (e.g. ``20``) avoids the combinatorial
        explosion that occurs without a cut-off.  When ``None`` (default)
        all discovered papers are expanded.
    openalex_api_key : str | None
        OpenAlex API key.
    email : str | None
        Contact email for polite-pool access (OpenAlex, CrossRef).
    semantic_scholar_api_key : str | None
        Semantic Scholar API key.
    num_workers : int
        Maximum number of connectors to query in parallel for each paper.
        Defaults to ``1`` (sequential).  The effective parallelism is
        capped at the number of available connectors.
    since : datetime.date | None
        Only include discovered papers published on or after this date.
        Seed papers are never filtered.  ``None`` (default) disables
        the lower-bound date filter.
    until : datetime.date | None
        Only include discovered papers published on or before this date.
        Seed papers are never filtered.  ``None`` (default) disables
        the upper-bound date filter.
    ieee_api_key : str | None
        IEEE Xplore API key used during the enrichment phase.
    scopus_api_key : str | None
        Elsevier / Scopus API key used during the enrichment phase.
    pubmed_api_key : str | None
        NCBI PubMed API key used during the enrichment phase.
    wos_api_key : str | None
        Clarivate Web of Science API key used during the enrichment phase.
    databases : list[str] | None
        Citation database identifiers to use for snowballing.  ``None``
        (default) uses all available citation databases (``openalex``,
        ``semantic_scholar``, ``crossref``).  Pass an explicit list to
        restrict which connectors are queried.  An empty list raises
        :class:`~findpapers.exceptions.InvalidParameterError`.
    enrichment_databases : list[str] | None
        Databases used to enrich graph nodes after snowballing completes.
        ``None`` (default) uses ``crossref`` and ``web_scraping``; pass
        ``[]`` to disable enrichment entirely.
    proxy : str | None
        Optional HTTP/HTTPS proxy URL forwarded to the enrichment
        :class:`~findpapers.runners.get_runner.GetRunner`.
    ssl_verify : bool
        Whether to verify SSL certificates during enrichment.
        Defaults to ``True``.
    """

    def __init__(
        self,
        seed_papers: list[Paper] | Paper,
        *,
        max_depth: int = 1,
        direction: Literal["both", "backward", "forward"] = "both",
        top_n_per_level: int | None = None,
        openalex_api_key: str | None = None,
        email: str | None = None,
        semantic_scholar_api_key: str | None = None,
        num_workers: int = 1,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
        ieee_api_key: str | None = None,
        scopus_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        wos_api_key: str | None = None,
        databases: list[str] | None = None,
        enrichment_databases: list[str] | None = DEFAULT_ENRICHMENT_DATABASES,
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
        top_n_per_level : int | None
            When set, keep only the top-N most-cited papers per level.
        openalex_api_key : str | None
            OpenAlex API key.
        email : str | None
            Contact email for polite-pool access.
        semantic_scholar_api_key : str | None
            Semantic Scholar API key.
        num_workers : int
            Maximum parallel workers per paper expansion.
        since : datetime.date | None
            Lower-bound publication date filter for discovered papers.
        until : datetime.date | None
            Upper-bound publication date filter for discovered papers.
        ieee_api_key : str | None
            IEEE Xplore API key for enrichment.
        scopus_api_key : str | None
            Scopus API key for enrichment.
        pubmed_api_key : str | None
            PubMed API key for enrichment.
        wos_api_key : str | None
            Clarivate Web of Science API key for enrichment.
        databases : list[str] | None
            Citation database identifiers to use for snowballing.  ``None``
            uses all available citation databases.  Pass an explicit list to
            restrict which connectors are queried.  Accepted values:
            ``"crossref"``, ``"openalex"``, ``"semantic_scholar"``.
        enrichment_databases : list[str] | None
            Databases for post-snowball enrichment.  Defaults to
            ``DEFAULT_ENRICHMENT_DATABASES`` (``["crossref", "web_scraping"]``).
            Pass ``None`` or ``[]`` to disable enrichment.
        proxy : str | None
            Optional proxy URL for enrichment requests.
        ssl_verify : bool
            Whether to verify SSL certificates during enrichment.

        Raises
        ------
        InvalidParameterError
            If *max_depth* is less than 1, *top_n_per_level* is less than 1,
            *databases* is an empty list or contains unknown identifiers,
            or *enrichment_databases* contains unknown database names.
        """
        if max_depth < 1:
            raise InvalidParameterError(f"max_depth must be >= 1, got {max_depth}")
        if top_n_per_level is not None and top_n_per_level < 1:
            raise InvalidParameterError(
                f"top_n_per_level must be >= 1 when set, got {top_n_per_level}"
            )

        valid_citation_databases = {db.value for db in CITATION_REGISTRY}
        if databases is not None and len(databases) == 0:
            raise InvalidParameterError(
                "databases must not be an empty list. "
                "Pass None to use all available citation databases."
            )
        if databases is not None:
            unknown = [db for db in databases if db not in valid_citation_databases]
            if unknown:
                raise InvalidParameterError(
                    f"Unknown citation database(s): {', '.join(unknown)}. "
                    f"Accepted values: {', '.join(sorted(valid_citation_databases))}"
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

        if isinstance(seed_papers, Paper):
            seed_papers = [seed_papers]

        self._seed_papers = [p for p in seed_papers if p.doi]
        self._skipped_seeds = len(seed_papers) - len(self._seed_papers)
        self._max_depth = max_depth
        self._direction = direction
        self._top_n_per_level = top_n_per_level
        self._num_workers = max(num_workers, 1)
        self._graph: CitationGraph | None = None
        self._metrics: dict[str, int | float] = {}

        self._connectors = self._build_connectors(
            databases=databases,
            openalex_api_key=openalex_api_key,
            email=email,
            semantic_scholar_api_key=semantic_scholar_api_key,
        )
        # Populated by run() before any connector queries; empty dict means
        # show_progress=False or run() has not been called yet (bars are None).
        self._connector_bars: dict[str, tuple[tqdm | None, tqdm | None]] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, verbose: bool = False, show_progress: bool = True) -> CitationGraph:
        """Execute the snowball and return the citation graph.

        Can be called multiple times; each call resets previous results.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging.
        show_progress : bool
            When ``True`` (default), display tqdm progress bars for each
            snowball level while papers are being expanded.  Set to
            ``False`` to suppress progress output (e.g. in non-interactive
            environments or to keep log output clean).

        Returns
        -------
        CitationGraph
            The built citation graph.
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
            str(self._top_n_per_level) if self._top_n_per_level else "unlimited",
        )
        logger.debug("Connectors: %s", [c.name for c in self._connectors])
        logger.debug("Num workers: %d", self._num_workers)
        logger.debug("=====================================")

        start = perf_counter()

        graph = CitationGraph(
            seed_papers=self._seed_papers,
            max_depth=self._max_depth,
            direction=self._direction,
        )

        frontier = list(self._seed_papers)

        use_pool = self._num_workers > 1 and len(self._connectors) > 1
        pool: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(max_workers=min(self._num_workers, len(self._connectors)))
            if use_pool
            else None
        )

        self._connector_bars = {}
        with contextlib.ExitStack() as _bar_stack:
            self._setup_connector_bars(_bar_stack, show_progress)

            try:
                for level in range(1, self._max_depth + 1):
                    if not frontier:
                        break

                    logger.debug(
                        "Level %d/%d: processing %d papers.",
                        level,
                        self._max_depth,
                        len(frontier),
                    )

                    next_frontier = self._process_level(frontier, graph, level, pool, show_progress)
                    frontier = next_frontier

                    logger.debug(
                        "Level %d/%d complete: %d new papers discovered%s.",
                        level,
                        self._max_depth,
                        len(next_frontier),
                        f" (top {self._top_n_per_level} kept)" if self._top_n_per_level else "",
                    )
            finally:
                if pool is not None:
                    pool.shutdown(wait=True)
                for connector in self._connectors:
                    connector.close()

        elapsed = perf_counter() - start
        self._metrics = {
            "seed_papers": len(self._seed_papers),
            "skipped_seeds_without_doi": self._skipped_seeds,
            "max_depth": self._max_depth,
            "total_nodes": graph.node_count,
            "total_edges": graph.edge_count,
            "runtime_in_seconds": elapsed,
        }
        self._graph = graph

        # Enrich graph nodes via per-paper get() lookups.
        # enrichment_databases=None  → enrich with all available databases.
        # enrichment_databases=[]    → skip enrichment entirely.
        if not (
            isinstance(self._enrichment_databases, list) and len(self._enrichment_databases) == 0
        ):
            super()._enrich_papers(
                graph.nodes,
                verbose,
                show_progress=show_progress,
                num_workers=self._num_workers,
            )

        logger.debug("=== Snowball Results ===")
        logger.debug("Total nodes: %d", graph.node_count)
        logger.debug("Total edges: %d", graph.edge_count)
        logger.debug("Runtime: %.2f s", elapsed)
        logger.debug("========================")

        _root_logger.setLevel(_saved_log_level)
        return graph

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_connector_bars(self, bar_stack: contextlib.ExitStack, show_progress: bool) -> None:
        """Create persistent tqdm progress bars for all connectors.

        Bars are stored in ``self._connector_bars`` keyed by connector name.

        Parameters
        ----------
        bar_stack : contextlib.ExitStack
            Context manager stack that owns the bar lifetimes.
        show_progress : bool
            Whether progress bars should be visible.

        Returns
        -------
        None
        """
        _bar_pos = 0
        _connector_bar_positions: dict[str, tuple[int | None, int | None]] = {}
        for _c in self._connectors:
            _b_pos: int | None = None
            _f_pos: int | None = None
            if self._direction in ("both", "backward") and _c.supports_backward:
                _b_pos = _bar_pos
                _bar_pos += 1
            if self._direction in ("both", "forward") and _c.supports_forward:
                _f_pos = _bar_pos
                _bar_pos += 1
            _connector_bar_positions[_c.name] = (_b_pos, _f_pos)

        for _c in self._connectors:
            _b_pos, _f_pos = _connector_bar_positions[_c.name]
            _b_bar: tqdm | None = (
                bar_stack.enter_context(
                    make_progress_bar(
                        desc=f"{_c.name} backward",
                        total=None,
                        unit="paper",
                        disable=not show_progress,
                        leave=True,
                        position=_b_pos,
                    )
                )
                if _b_pos is not None
                else None
            )
            _f_bar: tqdm | None = (
                bar_stack.enter_context(
                    make_progress_bar(
                        desc=f"{_c.name} forward",
                        total=None,
                        unit="paper",
                        disable=not show_progress,
                        leave=True,
                        position=_f_pos,
                    )
                )
                if _f_pos is not None
                else None
            )
            self._connector_bars[_c.name] = (_b_bar, _f_bar)

    def _process_level(
        self,
        frontier: list[Paper],
        graph: CitationGraph,
        level: int,
        pool: ThreadPoolExecutor | None,
        show_progress: bool,
    ) -> list[Paper]:
        """Expand one BFS level and return the next frontier.

        Parameters
        ----------
        frontier : list[Paper]
            Papers to expand in this level.
        graph : CitationGraph
            The citation graph being built.
        level : int
            Current BFS depth (1-based).
        pool : ThreadPoolExecutor | None
            Thread pool for parallel connector calls, or ``None`` for serial.
        show_progress : bool
            Whether to update progress bar descriptions.

        Returns
        -------
        list[Paper]
            Newly discovered papers for the next frontier.
        """
        if self._top_n_per_level is None:
            return self._process_level_unlimited(frontier, graph, level, pool, show_progress)
        return self._process_level_limited(frontier, graph, level, pool, show_progress)

    def _process_level_unlimited(
        self,
        frontier: list[Paper],
        graph: CitationGraph,
        level: int,
        pool: ThreadPoolExecutor | None,
        show_progress: bool,
    ) -> list[Paper]:
        """Process a BFS level without any per-level paper limit.

        Parameters
        ----------
        frontier : list[Paper]
            Papers to expand in this level.
        graph : CitationGraph
            The citation graph being built.
        level : int
            Current BFS depth (1-based).
        pool : ThreadPoolExecutor | None
            Thread pool for parallel connector calls.
        show_progress : bool
            Whether to update progress bar descriptions.

        Returns
        -------
        list[Paper]
            All newly discovered papers.
        """
        next_frontier: list[Paper] = []
        for seed_i, paper in enumerate(frontier, 1):
            self._set_connector_bar_descs(level, len(frontier), seed_i)
            discovered = self._expand_paper(paper, graph, pool, show_progress=show_progress)
            next_frontier.extend(discovered)
        return next_frontier

    def _process_level_limited(
        self,
        frontier: list[Paper],
        graph: CitationGraph,
        level: int,
        pool: ThreadPoolExecutor | None,
        show_progress: bool,
    ) -> list[Paper]:
        """Process a BFS level keeping only top-N papers per level.

        Parameters
        ----------
        frontier : list[Paper]
            Papers to expand in this level.
        graph : CitationGraph
            The citation graph being built.
        level : int
            Current BFS depth (1-based).
        pool : ThreadPoolExecutor | None
            Thread pool for parallel connector calls.
        show_progress : bool
            Whether to update progress bar descriptions.

        Returns
        -------
        list[Paper]
            Top-N newly discovered papers sorted by citation count.
        """
        all_raw: list[tuple[Paper, Paper, bool]] = []
        for seed_i, paper in enumerate(frontier, 1):
            self._set_connector_bar_descs(level, len(frontier), seed_i)
            all_raw.extend(self._collect_candidates(paper, pool, show_progress=show_progress))

        best: dict[str, Paper] = {}
        edge_map: dict[str, list[tuple[Paper, bool]]] = {}
        for candidate, source, is_ref in all_raw:
            key = CitationGraph._paper_key(candidate)
            if key is None or graph.contains(candidate):
                continue
            if not self._matches_filters(candidate):
                continue
            if key not in best:
                best[key] = candidate
                edge_map[key] = []
            elif candidate.citations is not None and (
                best[key].citations is None or candidate.citations > (best[key].citations or 0)
            ):
                best[key] = candidate
            edge_map[key].append((source, is_ref))

        top_keys = sorted(
            best,
            key=lambda k: best[k].citations or 0,
            reverse=True,
        )[: self._top_n_per_level]

        next_frontier: list[Paper] = []
        for key in top_keys:
            paper_repr = best[key]
            first_source = edge_map[key][0][0]
            canonical = graph.add_node(paper_repr, discovered_from=first_source)
            for source, is_ref in edge_map[key]:
                if is_ref:
                    graph.add_edge(source, canonical)
                else:
                    graph.add_edge(canonical, source)
            next_frontier.append(canonical)
        return next_frontier

    def _set_connector_bar_descs(self, level: int, total_seeds: int, seed_i: int) -> None:
        """Update all connector progress bar descriptions with current phase context.

        Sets each bar's label to ``"Level L/N - seed S/T - direction: name"``
        so the user always knows which level, which seed paper, and which
        connector/direction is running.

        Parameters
        ----------
        level : int
            Current BFS level (1-based).
        total_seeds : int
            Total number of papers in the current frontier.
        seed_i : int
            1-based index of the paper currently being expanded.

        Returns
        -------
        None
        """
        prefix = f"Level {level}/{self._max_depth} - seed {seed_i}/{total_seeds}"
        for connector_name, (b_bar, f_bar) in self._connector_bars.items():
            if b_bar is not None:
                b_bar.set_description(f"{prefix} - backward - {connector_name}")
            if f_bar is not None:
                f_bar.set_description(f"{prefix} - forward - {connector_name}")

    def _build_connectors(
        self,
        *,
        databases: list[str] | None,
        openalex_api_key: str | None,
        email: str | None,
        semantic_scholar_api_key: str | None,
    ) -> list[CitationConnectorBase]:
        """Build citation connectors, optionally restricted to *databases*.

        Parameters
        ----------
        databases : list[str] | None
            Citation database identifiers to include.  ``None`` includes all
            connectors registered in :data:`~findpapers.connectors.CITATION_REGISTRY`.
        openalex_api_key : str | None
            OpenAlex API key.
        email : str | None
            Contact email.
        semantic_scholar_api_key : str | None
            Semantic Scholar API key.

        Returns
        -------
        list[CitationConnectorBase]
            Available citation connectors matching the *databases* filter.
        """
        # Per-connector constructor credentials.  Connectors with no entry
        # are constructed with no arguments.  The classes are looked up in
        # the central CITATION_REGISTRY so that this runner does not need
        # to import every concrete connector.
        _credentials: dict[Database, dict[str, str | None]] = {
            Database.OPENALEX: {"api_key": openalex_api_key, "email": email},
            Database.SEMANTIC_SCHOLAR: {"api_key": semantic_scholar_api_key},
            Database.CROSSREF: {"email": email},
        }

        allowed = {db.strip().lower() for db in databases} if databases is not None else None
        return [
            cls(**_credentials.get(name, {}))
            for name, cls in CITATION_REGISTRY.items()
            if allowed is None or name.value in allowed
        ]

    def _expand_paper(
        self,
        paper: Paper,
        graph: CitationGraph,
        pool: ThreadPoolExecutor | None = None,
        *,
        show_progress: bool = True,
    ) -> list[Paper]:
        """Expand one paper by fetching its references and/or citing papers.

        For each connector, fetches backward and/or forward citations,
        adds new papers to the graph and records edges.  The depth of
        discovered papers is automatically derived from the depth of
        *paper* in the graph.

        Parameters
        ----------
        paper : Paper
            The paper to expand.
        graph : CitationGraph
            The graph under construction.
        pool : ThreadPoolExecutor | None
            Optional shared thread pool for parallel connector queries.
            When ``None``, connectors are called sequentially.
        show_progress : bool
            When ``True``, display per-connector progress bars for
            long pagination operations.

        Returns
        -------
        list[Paper]
            Newly discovered papers (not previously in the graph) that
            should be expanded in the next level.
        """
        new_papers: list[Paper] = []

        for candidate, source, is_ref in self._collect_candidates(
            paper, pool, show_progress=show_progress
        ):
            if not self._matches_filters(candidate):
                continue
            is_new = not graph.contains(candidate)
            canonical = graph.add_node(candidate, discovered_from=source)
            if is_ref:
                graph.add_edge(source, canonical)
            else:
                graph.add_edge(canonical, source)
            if is_new:
                new_papers.append(canonical)

        return new_papers

    def _collect_candidates(
        self,
        paper: Paper,
        pool: ThreadPoolExecutor | None = None,
        *,
        show_progress: bool = True,
    ) -> list[tuple[Paper, Paper, bool]]:
        """Query connectors for *paper* and return raw candidates without modifying the graph.

        Parameters
        ----------
        paper : Paper
            The paper to query.
        pool : ThreadPoolExecutor | None
            Optional shared thread pool for parallel connector queries.
        show_progress : bool
            Display per-connector progress bars.

        Returns
        -------
        list[tuple[Paper, Paper, bool]]
            Each entry is ``(candidate, source, is_reference)``.  *is_reference*
            is ``True`` for backward citations (source cites candidate) and
            ``False`` for forward citations (candidate cites source).
        """
        candidates: list[tuple[Paper, Paper, bool]] = []

        for _name, references, citing in self._query_connectors(
            paper, pool, show_progress=show_progress
        ):
            if references is not None:
                for ref_paper in references:
                    candidates.append((ref_paper, paper, True))
            if citing is not None:
                for citing_paper in citing:
                    candidates.append((citing_paper, paper, False))

        return candidates

    def _query_single_connector(
        self,
        connector: CitationConnectorBase,
        paper: Paper,
        *,
        show_progress: bool = True,
    ) -> tuple[str, list[Paper] | None, list[Paper] | None]:
        """Query a single connector for references and/or citing papers.

        Pre-created progress bars stored in ``self._connector_bars`` are reset
        and reused for each paper so they remain visible at fixed terminal
        positions in both serial and parallel modes.

        Parameters
        ----------
        connector : CitationConnectorBase
            The connector to query.
        paper : Paper
            The paper to look up.
        show_progress : bool
            Display per-connector progress bars for long pagination.

        Returns
        -------
        tuple[str, list[Paper] | None, list[Paper] | None]
            A ``(connector_name, references, citing)`` tuple.  Either list
            may be ``None`` if the corresponding direction was not requested.
        """
        references: list[Paper] | None = None
        citing: list[Paper] | None = None

        backward_bar, forward_bar = self._connector_bars.get(connector.name, (None, None))

        def _pbar_callback(pbar: tqdm | None) -> Callable[[int], None]:
            """Return a callback that increments *pbar* when it is not ``None``."""

            def _cb(n: int) -> None:
                if pbar is not None:
                    pbar.update(n)

            return _cb

        def _finalize_bar(pbar: tqdm | None) -> None:
            """Reconcile bar total with actual count so it always shows 100%.

            The expected count (from metadata) can differ from the actual
            number of items returned by the API.  Setting ``total = n``
            after fetching ensures the bar reaches 100% regardless.
            """
            if pbar is not None and pbar.total is not None and pbar.n != pbar.total:
                pbar.total = pbar.n
                pbar.refresh()

        # Fetch expected counts for determinate progress bars.
        cit_count: int | None = None
        ref_count: int | None = None
        if show_progress and (backward_bar is not None or forward_bar is not None):
            with contextlib.suppress(Exception):
                cit_count, ref_count = connector.get_expected_counts(paper)

        if self._direction in ("both", "backward") and connector.supports_backward:
            if backward_bar is not None:
                backward_bar.reset(total=ref_count)
            try:
                references = connector.fetch_references(
                    paper,
                    progress_callback=_pbar_callback(backward_bar),
                )
            except Exception:
                logger.warning(
                    "Error fetching references from %s for '%s'.",
                    connector.name,
                    paper.title,
                )
                references = []
            _finalize_bar(backward_bar)

        if self._direction in ("both", "forward") and connector.supports_forward:
            if forward_bar is not None:
                forward_bar.reset(total=cit_count)
            try:
                citing = connector.fetch_cited_by(
                    paper,
                    progress_callback=_pbar_callback(forward_bar),
                )
            except Exception:
                logger.warning(
                    "Error fetching cited-by from %s for '%s'.",
                    connector.name,
                    paper.title,
                )
                citing = []
            _finalize_bar(forward_bar)

        return connector.name, references, citing

    def _query_connectors(
        self,
        paper: Paper,
        pool: ThreadPoolExecutor | None = None,
        *,
        show_progress: bool = True,
    ) -> list[tuple[str, list[Paper] | None, list[Paper] | None]]:
        """Query all connectors, optionally in parallel.

        When *pool* is ``None`` the connectors are called sequentially.
        Otherwise connectors are queried concurrently using the shared
        thread pool.

        Parameters
        ----------
        paper : Paper
            The paper to look up.
        pool : ThreadPoolExecutor | None
            Optional shared thread pool.  When ``None``, connectors are
            called sequentially.
        show_progress : bool
            Display per-connector progress bars.

        Returns
        -------
        list[tuple[str, list[Paper] | None, list[Paper] | None]]
            Results from each connector.
        """
        if pool is None:
            return [
                self._query_single_connector(
                    connector,
                    paper,
                    show_progress=show_progress,
                )
                for connector in self._connectors
            ]

        results: list[tuple[str, list[Paper] | None, list[Paper] | None]] = []
        futures = {
            pool.submit(
                self._query_single_connector,
                connector,
                paper,
                show_progress=show_progress,
            ): connector
            for connector in self._connectors
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                connector = futures[future]
                logger.warning(
                    "Unexpected error querying %s for '%s'.",
                    connector.name,
                    paper.title,
                )
        return results
