from __future__ import annotations

from time import perf_counter

from .exceptions import SearchRunnerNotExecutedError
from .searchers import (
    ArxivSearcher,
    BiorxivSearcher,
    IeeeSearcher,
    MedrxivSearcher,
    PubmedSearcher,
    ScopusSearcher,
    SearcherBase,
)


class SearchRunner:
    """Public API placeholder for the refactor."""

    def __init__(
        self,
        *args,
        databases: list[str] | None = None,
        enrich: bool = True,
        max_workers: int | None = None,
        timeout: float = 10.0,
        **kwargs,
    ) -> None:
        self._executed = False
        self._results: list = []
        self._metrics: dict[str, int | float] = {}
        self._searchers = self._build_searchers(databases)
        self._config = {
            "enrich": enrich,
            "max_workers": max_workers,
            "timeout": timeout,
        }

    def run(self, verbose: bool = False) -> None:  # noqa: ARG002 - placeholder
        start = perf_counter()
        self._results = []
        metrics: dict[str, int | float] = {
            "papers_count": 0,
            "runtime_seconds": 0.0,
            "errors_total": 0,
            "searchers_total": len(self._searchers),
            "stage.fetch.runtime_seconds": 0.0,
        }
        self._fetch_searchers(metrics)

        metrics["papers_count"] = len(self._results)
        metrics["runtime_seconds"] = perf_counter() - start
        self._metrics = metrics
        self._executed = True

    def get_results(self):
        self._ensure_executed()
        return list(self._results)

    def get_metrics(self):
        self._ensure_executed()
        return dict(self._metrics)

    def to_json(self, path) -> None:  # noqa: ANN001 - placeholder
        self._ensure_executed()

    def to_csv(self, path) -> None:  # noqa: ANN001 - placeholder
        self._ensure_executed()

    def to_bibtex(self, path) -> None:  # noqa: ANN001 - placeholder
        self._ensure_executed()

    def _ensure_executed(self) -> None:
        if not self._executed:
            raise SearchRunnerNotExecutedError("SearchRunner has not been executed yet.")

    def _build_searchers(self, databases: list[str] | None) -> list[SearcherBase]:
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
        fetch_start = perf_counter()
        for searcher in self._searchers:
            searcher_start = perf_counter()
            count = 0
            errors = 0
            try:
                results = searcher.search() or []
                count = len(results)
                self._results.extend(results)
            except Exception:
                errors = 1
            metrics[f"searcher.{searcher.name}.runtime_seconds"] = perf_counter() - searcher_start
            metrics[f"searcher.{searcher.name}.count"] = count
            metrics[f"searcher.{searcher.name}.errors"] = errors
            metrics["errors_total"] += errors
        metrics["stage.fetch.runtime_seconds"] = perf_counter() - fetch_start


__all__ = ["SearchRunner", "SearchRunnerNotExecutedError"]
