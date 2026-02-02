from __future__ import annotations

from typing import TYPE_CHECKING

from .rxiv import RxivSearcher

if TYPE_CHECKING:
    from findpapers.models import Query


class BiorxivSearcher(RxivSearcher):
    """Minimal bioRxiv searcher placeholder for the new OO pipeline."""

    def __init__(self, query: "Query | None" = None) -> None:
        """Create a bioRxiv searcher placeholder.

        Parameters
        ----------
        query : Query | None
            Parsed query object.
        """
        super().__init__(query=query, database="biorxiv")
