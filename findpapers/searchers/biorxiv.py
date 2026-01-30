from __future__ import annotations

from .rxiv import RxivSearcher


class BiorxivSearcher(RxivSearcher):
    """Minimal bioRxiv searcher placeholder for the new OO pipeline."""

    def __init__(self, query: str | None = None) -> None:
        """Create a bioRxiv searcher placeholder.

        Parameters
        ----------
        query : str | None
            Raw query string.
        """
        super().__init__(query=query, database="biorxiv")
