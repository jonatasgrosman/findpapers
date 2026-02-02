from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from .base import SearcherBase

if TYPE_CHECKING:
    from findpapers.models import Query


class PubmedSearcher(SearcherBase):
    """Minimal PubMed searcher placeholder for the new OO pipeline."""

    def __init__(self, query: "Query | None" = None) -> None:
        """Create a PubMed searcher placeholder.

        Parameters
        ----------
        query : Query | None
            Parsed query object.
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
        return "pubmed"

    def iter_search(self) -> tuple[Iterator[list], int, int, int]:
        """Return an empty iterator for the placeholder implementation.

        Returns
        -------
        tuple
            Empty iterator, zero steps, zero papers per step, zero total papers.
        """
        # Stage 2.2 placeholder: real implementation will be migrated from findpapers_old.
        return self._empty_search_result()
