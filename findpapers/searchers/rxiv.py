from __future__ import annotations

from .base import SearcherBase


class RxivSearcher(SearcherBase):
    """Base rxiv searcher placeholder shared by bioRxiv and medRxiv."""

    def __init__(self, query: str | None = None, database: str = "rxiv") -> None:
        """Create a shared rxiv searcher placeholder for a specific database.

        Parameters
        ----------
        query : str | None
            Raw query string.
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

    def search(self) -> list:
        """Execute the search and return a list of papers.

        Returns
        -------
        list
            List of paper objects.
        """
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return []
