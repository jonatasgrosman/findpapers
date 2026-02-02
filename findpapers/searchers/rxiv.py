from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from .base import SearcherBase

if TYPE_CHECKING:
    from findpapers.models import Query


class RxivSearcher(SearcherBase):
    """Base rxiv searcher placeholder shared by bioRxiv and medRxiv."""

    def __init__(self, query: "Query | None" = None, database: str = "rxiv") -> None:
        """Create a shared rxiv searcher placeholder for a specific database.

        Parameters
        ----------
        query : Query | None
            Parsed query object.
        database : str
            Target database identifier.
        """
        self._query = query
        self._database = database

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database identifier.
        """
        return self._database

    def iter_search(self) -> tuple[Iterator[list], int, int, int]:
        """Return an empty iterator for the placeholder implementation.

        Returns
        -------
        tuple
            Empty iterator, zero steps, zero papers per step, zero total papers.
        """
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return self._empty_search_result()
