from __future__ import annotations

from .exceptions import SearchRunnerNotExecutedError


class SearchRunner:
    """Public API placeholder for the refactor."""

    def __init__(self, *args, **kwargs) -> None:
        self._executed = False

    def run(self, verbose: bool = False) -> None:  # noqa: ARG002 - placeholder
        self._executed = True

    def get_results(self):
        self._ensure_executed()
        return []

    def get_metrics(self):
        self._ensure_executed()
        return {}

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
