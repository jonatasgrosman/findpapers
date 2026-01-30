from __future__ import annotations

from .rxiv import RxivSearcher


class BiorxivSearcher(RxivSearcher):
    """Minimal bioRxiv searcher placeholder for the new OO pipeline."""

    def __init__(self, query: str | None = None) -> None:
        super().__init__(query=query, database="biorxiv")
