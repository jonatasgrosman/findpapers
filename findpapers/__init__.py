from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

from .exceptions import SearchRunnerNotExecutedError
from .models import Paper, Publication, Search
from .searchers import (
    ArxivSearcher,
    BiorxivSearcher,
    IeeeSearcher,
    MedrxivSearcher,
    PubmedSearcher,
    ScopusSearcher,
    SearcherBase,
)
from .utils import enrichment_util
from .utils.predatory_util import is_predatory_publication


class SearchRunner:
    """Public API entry point for running searches."""

    def __init__(
        self,
        *args,
        databases: list[str] | None = None,
        publication_types: list[str] | None = None,
        enrich: bool = True,
        max_workers: int | None = None,
        timeout: float = 10.0,
        **kwargs,
    ) -> None:
        """Initialize a search run configuration without executing it.

        Parameters
        ----------
        databases : list[str] | None
            List of database identifiers to query.
        publication_types : list[str] | None
            Allowed publication categories for filtering.
        enrich : bool
            Whether to enable enrichment stage (placeholder).
        max_workers : int | None
            Maximum workers for parallelism (placeholder).
        timeout : float
            Global timeout in seconds (placeholder).
        """
        self._executed = False
        self._results: list[Paper] = []
        self._metrics: dict[str, int | float] = {}
        self._searchers = self._build_searchers(databases)
        self._publication_types = publication_types
        self._config = {
            "enrich": enrich,
            "max_workers": max_workers,
            "timeout": timeout,
        }

    def run(self, verbose: bool = False) -> None:  # noqa: ARG002 - placeholder
        """Execute the configured pipeline once, resetting previous results.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging (placeholder).

        Returns
        -------
        None
        """
        start = perf_counter()
        self._results = []
        # Metrics are numeric-only to keep them export-friendly.
        metrics: dict[str, int | float] = {
            "papers_count": 0,
            "runtime_seconds": 0.0,
            "errors_total": 0,
            "searchers_total": len(self._searchers),
            "stage.fetch.runtime_seconds": 0.0,
            "stage.filter.runtime_seconds": 0.0,
            "stage.dedupe.runtime_seconds": 0.0,
            "stage.flag.runtime_seconds": 0.0,
            "stage.enrich.runtime_seconds": 0.0,
            "count.before_filter": 0,
            "count.after_filter": 0,
            "count.after_dedupe": 0,
            "count.predatory": 0,
            "count.enriched": 0,
            "errors.enrich": 0,
        }
        self._fetch_searchers(metrics)
        self._filter_by_publication_types(metrics)
        self._dedupe_and_merge(metrics)
        self._flag_predatory_publications(metrics)
        if self._config.get("enrich"):
            self._enrich_results(metrics)

        metrics["papers_count"] = len(self._results)
        metrics["runtime_seconds"] = perf_counter() - start
        self._metrics = metrics
        self._executed = True

    def get_results(self) -> list[Paper]:
        """Return a shallow copy of the results list after `run()`.

        Returns
        -------
        list[Paper]
            Copy of the current results.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        self._ensure_executed()
        return list(self._results)

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

    def to_json(self, path) -> None:  # noqa: ANN001 - placeholder
        """Export results to JSON after `run()` (placeholder).

        Parameters
        ----------
        path : Any
            Output path for JSON export.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        self._ensure_executed()

    def to_csv(self, path) -> None:  # noqa: ANN001 - placeholder
        """Export results to CSV after `run()` (placeholder).

        Parameters
        ----------
        path : Any
            Output path for CSV export.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        self._ensure_executed()

    def to_bibtex(self, path) -> None:  # noqa: ANN001 - placeholder
        """Export results to BibTeX after `run()` (placeholder).

        Parameters
        ----------
        path : Any
            Output path for BibTeX export.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        self._ensure_executed()

    def _ensure_executed(self) -> None:
        """Guard against accessing results before `run()`.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        if not self._executed:
            raise SearchRunnerNotExecutedError("SearchRunner has not been executed yet.")

    def _build_searchers(self, databases: list[str] | None) -> list[SearcherBase]:
        """Instantiate internal searchers from the user-provided database list.

        Parameters
        ----------
        databases : list[str] | None
            List of database identifiers.

        Returns
        -------
        list[SearcherBase]
            Instantiated searchers.

        Raises
        ------
        ValueError
            If any database identifier is unknown.
        """
        if not databases:
            return []
        searchers: list[SearcherBase] = []
        for database in databases:
            key = database.strip().lower()
            if key == "arxiv":
                searchers.append(ArxivSearcher())
            elif key == "biorxiv":
                searchers.append(BiorxivSearcher())
            elif key == "ieee":
                searchers.append(IeeeSearcher())
            elif key == "medrxiv":
                searchers.append(MedrxivSearcher())
            elif key == "pubmed":
                searchers.append(PubmedSearcher())
            elif key == "scopus":
                searchers.append(ScopusSearcher())
            else:
                raise ValueError(f"Unknown database: {database}")
        return searchers

    def _fetch_searchers(self, metrics: dict[str, int | float]) -> None:
        """Fetch results from all configured searchers, capturing per-searcher metrics.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        fetch_start = perf_counter()
        for searcher in self._searchers:
            searcher_start = perf_counter()
            count = 0
            errors = 0
            try:
                papers = searcher.search() or []
                count = len(papers)
                self._results.extend(papers)
            except Exception:
                errors = 1
            metrics[f"searcher.{searcher.name}.runtime_seconds"] = perf_counter() - searcher_start
            metrics[f"searcher.{searcher.name}.count"] = count
            metrics[f"searcher.{searcher.name}.errors"] = errors
            metrics["errors_total"] += errors
        metrics["stage.fetch.runtime_seconds"] = perf_counter() - fetch_start

    def _filter_by_publication_types(self, metrics: dict[str, int | float]) -> None:
        """Filter results by allowed publication categories.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        filter_start = perf_counter()
        metrics["count.before_filter"] = len(self._results)
        publication_types = self._publication_types or []
        if publication_types:
            allowed = {ptype.strip().lower() for ptype in publication_types}
            # Filter based on the publication category stored in each Paper.
            self._results = [
                paper for paper in self._results if self._publication_type_allowed(paper, allowed)
            ]
        metrics["count.after_filter"] = len(self._results)
        metrics["stage.filter.runtime_seconds"] = perf_counter() - filter_start

    def _publication_type_allowed(self, paper: Paper, allowed: set[str]) -> bool:
        """Return whether a paper belongs to an allowed publication category.

        Parameters
        ----------
        paper : Paper
            Result paper.
        allowed : set[str]
            Allowed category names.

        Returns
        -------
        bool
            True if the paper matches an allowed category.
        """
        category = None
        publication = paper.publication
        if publication is not None:
            category = publication.category
        if category is None:
            return False

        return str(category).strip().lower() in allowed

    def _dedupe_and_merge(self, metrics: dict[str, int | float]) -> None:
        """Deduplicate results and merge using the most-complete rule.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        dedupe_start = perf_counter()
        # Merge by stable keys (DOI, then title/year) to collapse duplicates.
        merged: dict[str, Paper] = {}
        for paper in self._results:
            key = self._dedupe_key(paper)
            if key in merged:
                merged[key].merge(paper)
            else:
                merged[key] = paper
        self._results = list(merged.values())
        metrics["count.after_dedupe"] = len(self._results)
        metrics["stage.dedupe.runtime_seconds"] = perf_counter() - dedupe_start

    def _flag_predatory_publications(self, metrics: dict[str, int | float]) -> None:
        """Flag potentially predatory publications in results.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        flag_start = perf_counter()
        flagged_count = 0
        for paper in self._results:
            publication = paper.publication
            if is_predatory_publication(publication):
                if publication is not None:
                    publication.is_potentially_predatory = True
                flagged_count += 1
        metrics["count.predatory"] = flagged_count
        metrics["stage.flag.runtime_seconds"] = perf_counter() - flag_start

    def _enrich_results(self, metrics: dict[str, int | float]) -> None:
        """Enrich results as the final stage.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        enrich_start = perf_counter()
        max_workers_value = self._config.get("max_workers")
        max_workers = max_workers_value if isinstance(max_workers_value, int) else None
        timeout = self._config.get("timeout")
        enriched = 0
        errors = 0

        if not self._results:
            metrics["stage.enrich.runtime_seconds"] = perf_counter() - enrich_start
            return

        if max_workers is None or max_workers <= 1:
            for paper in self._results:
                if timeout is not None and (perf_counter() - enrich_start) > timeout:
                    errors += 1
                    break
                try:
                    if self._enrich_paper(paper, timeout=timeout):
                        enriched += 1
                except Exception:
                    errors += 1
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._enrich_paper, paper, timeout=timeout): paper
                    for paper in self._results
                }
                remaining = (
                    None if timeout is None else max(timeout - (perf_counter() - enrich_start), 0)
                )
                try:
                    for future in as_completed(futures, timeout=remaining):
                        try:
                            if future.result():
                                enriched += 1
                        except Exception:
                            errors += 1
                except Exception:
                    errors += len([f for f in futures if not f.done()])

        metrics["count.enriched"] = enriched
        metrics["errors.enrich"] = errors
        metrics["stage.enrich.runtime_seconds"] = perf_counter() - enrich_start

    def _enrich_paper(self, paper: Paper, timeout: float | None = None) -> bool:
        """Enrich a single paper.

        Parameters
        ----------
        paper : Paper
            Result paper to enrich.

        Returns
        -------
        bool
            True if the paper was enriched, False otherwise.
        """
        urls = [str(url) for url in paper.urls if url]
        if not urls:
            return False
        enriched = enrichment_util.enrich_from_sources(urls=urls, timeout=timeout)
        if enriched is None:
            return False
        paper.merge(enriched)
        return True

    def _dedupe_key(self, paper: Paper) -> str:
        """Build a stable key based on DOI/title/year for deduplication.

        Parameters
        ----------
        paper : Paper
            Result paper.

        Returns
        -------
        str
            Stable dedupe key.
        """
        doi = paper.doi
        title = paper.title
        year = self._publication_year(paper.publication_date)

        if doi:
            return f"doi:{str(doi).strip().lower()}"
        if title and year:
            return f"title:{str(title).strip().lower()}|year:{year}"
        if title:
            return f"title:{str(title).strip().lower()}"
        return f"object:{id(paper)}"

    def _publication_year(self, publication_date: object) -> int | None:
        """Extract the year from a publication date object if present.

        Parameters
        ----------
        publication_date : object
            Publication date object.

        Returns
        -------
        int | None
            Year if available.
        """
        if publication_date is None:
            return None
        year = getattr(publication_date, "year", None)
        if isinstance(year, int):
            return year
        return None


__all__ = [
    "Paper",
    "Publication",
    "Search",
    "SearchRunner",
    "SearchRunnerNotExecutedError",
]
