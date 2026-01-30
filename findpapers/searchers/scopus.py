from __future__ import annotations

from .base import SearcherBase


class ScopusSearcher(SearcherBase):
    """Minimal Scopus searcher placeholder for the new OO pipeline."""

    def __init__(self, query: str | None = None) -> None:
        """Create a Scopus searcher placeholder.

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
        return "scopus"

    def search(self) -> list:
        """Execute the search and return a list of papers.

        Returns
        -------
        list
            List of paper objects.
        """
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return []
