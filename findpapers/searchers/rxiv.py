from __future__ import annotations

from .base import SearcherBase


class RxivSearcher(SearcherBase):
    """Base rxiv searcher placeholder shared by bioRxiv and medRxiv."""

    def __init__(self, query: str | None = None, database: str = "rxiv") -> None:
        self._query = query
        self._database = database

    @property
    def name(self) -> str:
        return self._database

    def search(self) -> list:
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return []
