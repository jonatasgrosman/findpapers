from __future__ import annotations

from .base import SearcherBase


class ArxivSearcher(SearcherBase):
    """Minimal arXiv searcher placeholder for the new OO pipeline."""

    def __init__(self, query: str | None = None) -> None:
        self._query = query

    @property
    def name(self) -> str:
        return "arxiv"

    def search(self) -> list:
        # Stage 2 placeholder: real implementation will be migrated from findpapers_old.
        return []
