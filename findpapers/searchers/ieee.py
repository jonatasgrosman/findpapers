from __future__ import annotations

from collections.abc import Iterator

from .base import SearcherBase


class IeeeSearcher(SearcherBase):
    """Minimal IEEE searcher placeholder for the new OO pipeline."""

    def __init__(self, query: str | None = None) -> None:
        """Create an IEEE searcher placeholder.

        Parameters
        ----------
        query : str | None
            Raw query string.
        """
        self._query = query

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database identifier.
        """
        return "ieee"

    def iter_search(self) -> tuple[Iterator[list], int, int, int]:
        """Return an empty iterator for the placeholder implementation.

        Returns
        -------
        tuple
            Empty iterator, zero steps, zero papers per step, zero total papers.
        """
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return self._empty_search_result()
