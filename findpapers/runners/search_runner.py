from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from time import perf_counter

from tqdm import tqdm

from findpapers.exceptions import SearchRunnerNotExecutedError
from findpapers.models import Paper
from findpapers.searchers import (
    ArxivSearcher,
    BiorxivSearcher,
    Database,
    IeeeSearcher,
    MedrxivSearcher,
    PubmedSearcher,
    ScopusSearcher,
    SearcherBase,
)
from findpapers.utils.predatory_util import is_predatory_publication


class SearchRunner:
    """Public API entry point for running searches."""

    def __init__(
        self,
        *args,
        databases: list[str | Database] | None = None,
        publication_types: list[str] | None = None,
        parallel_search: bool = True,
        **kwargs,
    ) -> None:
        """Initialize a search run configuration without executing it.

        Parameters
        ----------
        databases : list[str] | None
            List of database identifiers to query.
        publication_types : list[str] | None
            Allowed publication categories for filtering.
        parallel_search : bool
            Whether to execute database searches in parallel.
        """
        self._executed = False
        self._results: list[Paper] = []
        self._metrics: dict[str, int | float] = {}
        self._searchers = self._build_searchers(databases)
        self._publication_types = publication_types
        self._parallel_search = parallel_search

    def run(self, verbose: bool = False) -> list[Paper]:  # noqa: ARG002 - placeholder
        """Execute the configured pipeline once, resetting previous results.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging (placeholder).

        Returns
        -------
        list[Paper]
            Results from the search pipeline.
        """
        start = perf_counter()
        self._results = []
        metrics: dict[str, int | float] = {
            "total_papers": 0,
            "runtime_in_seconds": 0.0,
            "total_papers_from_predatory_publication": 0,
        }
        self._fetch_searchers(metrics)
        self._filter_by_publication_types(metrics)
        self._dedupe_and_merge(metrics)
        self._flag_predatory_publications(metrics)

        metrics["total_papers"] = len(self._results)
        metrics["runtime_in_seconds"] = perf_counter() - start
        self._metrics = metrics
        self._executed = True
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

    def _ensure_executed(self) -> None:
        """Guard against accessing results before `run()`.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        if not self._executed:
            raise SearchRunnerNotExecutedError("SearchRunner has not been executed yet.")

    def _build_searchers(self, databases: list[str | Database] | None) -> list[SearcherBase]:
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
            databases = [
                Database.ARXIV,
                Database.BIORXIV,
                Database.IEEE,
                Database.MEDRXIV,
                Database.PUBMED,
                Database.SCOPUS,
            ]
        searchers: list[SearcherBase] = []
        for database in databases:
            if isinstance(database, Database):
                key = database.value
            else:
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
        """Fetch results from all configured searchers, capturing per-searcher counts.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        plans: list[tuple[SearcherBase, Iterator[list[Paper]], int, int, int]] = []
        for searcher in self._searchers:
            try:
                iterator, _steps, _papers_per_step, total_papers = searcher.iter_search()
                plans.append((searcher, iterator, _steps, _papers_per_step, total_papers))
            except Exception:
                metrics[f"total_papers_from_{searcher.name}"] = 0

        total_papers = sum(plan[4] for plan in plans)
        lock = Lock()

        def process_plan(searcher: SearcherBase, iterator: Iterator[list[Paper]]) -> None:
            """Collect papers for a single searcher, updating metrics and progress.

            Parameters
            ----------
            searcher : SearcherBase
                Searcher instance being executed.
            iterator : Iterator[list[Paper]]
                Iterator yielding lists of papers.

            Returns
            -------
            None
            """
            count = 0
            papers: list[Paper] = []
            try:
                for batch in iterator:
                    if batch:
                        papers.extend(batch)
                        count += len(batch)
                        progress.update(len(batch))
            except Exception:
                count = 0
                papers = []
            with lock:
                self._results.extend(papers)
                metrics[f"total_papers_from_{searcher.name}"] = count

        with tqdm(total=total_papers, unit="paper") as progress:
            if self._parallel_search and len(plans) > 1:
                with ThreadPoolExecutor(max_workers=len(plans)) as executor:
                    futures = [executor.submit(process_plan, plan[0], plan[1]) for plan in plans]
                    for future in as_completed(futures):
                        future.result()
            else:
                for plan in plans:
                    process_plan(plan[0], plan[1])

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
        publication_types = self._publication_types or []
        if publication_types:
            allowed = {ptype.strip().lower() for ptype in publication_types}
            # Filter based on the publication category stored in each Paper.
            self._results = [
                paper for paper in self._results if self._publication_type_allowed(paper, allowed)
            ]

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
        # Merge by stable keys (DOI, then title/year) to collapse duplicates.
        merged: dict[str, Paper] = {}
        for paper in self._results:
            key = self._dedupe_key(paper)
            if key in merged:
                merged[key].merge(paper)
            else:
                merged[key] = paper
        self._results = list(merged.values())

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
        flagged_count = 0
        for paper in self._results:
            publication = paper.publication
            if is_predatory_publication(publication):
                if publication is not None:
                    publication.is_potentially_predatory = True
                flagged_count += 1
        metrics["total_papers_from_predatory_publication"] = flagged_count

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
