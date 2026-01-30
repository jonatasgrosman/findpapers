from __future__ import annotations

from .base import SearcherBase


class ScopusSearcher(SearcherBase):
    """Minimal Scopus searcher placeholder for the new OO pipeline."""

    def __init__(self, query: str | None = None) -> None:
        self._query = query

    @property
    def name(self) -> str:
        return "scopus"

    def search(self) -> list:
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return []
