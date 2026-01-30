from __future__ import annotations

from time import perf_counter

from .exceptions import SearchRunnerNotExecutedError


class SearchRunner:
    """Public API placeholder for the refactor."""

    def __init__(
        self,
        *args,
        enrich: bool = True,
        max_workers: int | None = None,
        timeout: float = 10.0,
        **kwargs,
    ) -> None:
        self._executed = False
        self._results: list = []
        self._metrics: dict[str, int | float] = {}
        self._config = {
            "enrich": enrich,
            "max_workers": max_workers,
            "timeout": timeout,
        }

    def run(self, verbose: bool = False) -> None:  # noqa: ARG002 - placeholder
        start = perf_counter()
        self._results = []
        self._metrics = {
            "papers_count": 0,
            "runtime_seconds": 0.0,
        }
        self._metrics["runtime_seconds"] = perf_counter() - start
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


__all__ = ["SearchRunner", "SearchRunnerNotExecutedError"]
