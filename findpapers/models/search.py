from __future__ import annotations

import datetime
from typing import List, Optional

from .paper import Paper


class Search:
    """Represents a search configuration and results."""

    def __init__(
        self,
        query: str,
        since: Optional[datetime.date] = None,
        until: Optional[datetime.date] = None,
        limit: Optional[int] = None,
        limit_per_database: Optional[int] = None,
        processed_at: Optional[datetime.datetime] = None,
        databases: Optional[List[str]] = None,
        publication_types: Optional[List[str]] = None,
        papers: Optional[List[Paper]] = None,
    ) -> None:
        """Create a Search instance.

        Parameters
        ----------
        query : str
            Search query.
        since : datetime.date | None
            Lower bound date.
        until : datetime.date | None
            Upper bound date.
        limit : int | None
            Global limit.
        limit_per_database : int | None
            Per-database limit.
        processed_at : datetime.datetime | None
            Processing timestamp.
        databases : list[str] | None
            Database identifiers.
        publication_types : list[str] | None
            Publication types filter.
        papers : list[Paper] | None
            Initial papers.
        """
        self.query = query
        self.since = since
        self.until = until
        self.limit = limit
        self.limit_per_database = limit_per_database
        self.processed_at = processed_at if processed_at is not None else datetime.datetime.utcnow()
        self.databases = databases
        self.publication_types = publication_types
        self.papers: List[Paper] = papers or []

    def add_paper(self, paper: Paper) -> None:
        """Add a paper to the results.

        Parameters
        ----------
        paper : Paper
            Paper to add.
        """
        self.papers.append(paper)

    def remove_paper(self, paper: Paper) -> None:
        """Remove a paper from results.

        Parameters
        ----------
        paper : Paper
            Paper to remove.
        """
        if paper in self.papers:
            self.papers.remove(paper)
