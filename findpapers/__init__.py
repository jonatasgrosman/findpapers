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
        publication_types: list[str] | None = None,
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
            "publication_types": publication_types,
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
            "stage.filter.runtime_seconds": 0.0,
            "stage.dedupe.runtime_seconds": 0.0,
            "count.before_filter": 0,
            "count.after_filter": 0,
            "count.after_dedupe": 0,
        }
        self._fetch_searchers(metrics)
        self._filter_by_publication_types(metrics)
        self._dedupe_and_merge(metrics)

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

    def _filter_by_publication_types(self, metrics: dict[str, int | float]) -> None:
        filter_start = perf_counter()
        metrics["count.before_filter"] = len(self._results)
        publication_types = self._config.get("publication_types") or []
        if publication_types:
            allowed = {ptype.strip().lower() for ptype in publication_types}
            self._results = [
                item for item in self._results if self._publication_type_allowed(item, allowed)
            ]
        metrics["count.after_filter"] = len(self._results)
        metrics["stage.filter.runtime_seconds"] = perf_counter() - filter_start

    def _publication_type_allowed(self, item: object, allowed: set[str]) -> bool:
        category = None
        if isinstance(item, dict):
            publication = item.get("publication")
            if isinstance(publication, dict):
                category = publication.get("category")
            elif publication is not None:
                category = getattr(publication, "category", None)
            if category is None:
                category = item.get("publication_category")
        else:
            publication = getattr(item, "publication", None)
            if publication is not None:
                category = getattr(publication, "category", None)
            if category is None:
                category = getattr(item, "publication_category", None)

        if category is None:
            return False

        return str(category).strip().lower() in allowed

    def _dedupe_and_merge(self, metrics: dict[str, int | float]) -> None:
        dedupe_start = perf_counter()
        merged: dict[str, object] = {}
        for item in self._results:
            key = self._dedupe_key(item)
            if key in merged:
                merged[key] = self._merge_items(merged[key], item)
            else:
                merged[key] = item
        self._results = list(merged.values())
        metrics["count.after_dedupe"] = len(self._results)
        metrics["stage.dedupe.runtime_seconds"] = perf_counter() - dedupe_start

    def _dedupe_key(self, item: object) -> str:
        if isinstance(item, dict):
            doi = item.get("doi")
            title = item.get("title")
            year = self._publication_year(item.get("publication_date"))
        else:
            doi = getattr(item, "doi", None)
            title = getattr(item, "title", None)
            year = self._publication_year(getattr(item, "publication_date", None))

        if doi:
            return f"doi:{str(doi).strip().lower()}"
        if title and year:
            return f"title:{str(title).strip().lower()}|year:{year}"
        if title:
            return f"title:{str(title).strip().lower()}"
        return f"object:{id(item)}"

    def _publication_year(self, publication_date: object) -> int | None:
        if publication_date is None:
            return None
        year = getattr(publication_date, "year", None)
        if isinstance(year, int):
            return year
        return None

    def _merge_items(self, base: object, incoming: object) -> object:
        if isinstance(base, dict) and isinstance(incoming, dict):
            return self._merge_dicts(base, incoming)
        if hasattr(base, "__dict__") and hasattr(incoming, "__dict__"):
            merged = self._merge_dicts(vars(base), vars(incoming))
            for key, value in merged.items():
                setattr(base, key, value)
            return base
        return base

    def _merge_dicts(self, base: dict, incoming: dict) -> dict:
        merged = dict(base)
        for key in set(base.keys()) | set(incoming.keys()):
            merged[key] = self._merge_values(base.get(key), incoming.get(key))
        return merged

    def _merge_values(self, base: object, incoming: object) -> object:
        if base is None:
            return incoming
        if incoming is None:
            return base
        if isinstance(base, str) and isinstance(incoming, str):
            return base if len(base) >= len(incoming) else incoming
        if isinstance(base, (int, float)) and isinstance(incoming, (int, float)):
            return base if base >= incoming else incoming
        if isinstance(base, set) and isinstance(incoming, set):
            return base | incoming
        if isinstance(base, list) and isinstance(incoming, list):
            return list({*base, *incoming})
        if isinstance(base, tuple) and isinstance(incoming, tuple):
            return tuple({*base, *incoming})
        if isinstance(base, dict) and isinstance(incoming, dict):
            return self._merge_dicts(base, incoming)
        return base


__all__ = ["SearchRunner", "SearchRunnerNotExecutedError"]
