from __future__ import annotations

import datetime
from typing import List, Optional

from ..utils.search_export_util import (
    export_search_to_bibtex,
    export_search_to_csv,
    export_search_to_json,
)
from ..utils.version_util import package_version
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
        metrics: Optional[dict[str, int | float]] = None,
        timeout: Optional[float] = None,
        runtime_seconds: Optional[float] = None,
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
        metrics : dict[str, int | float] | None
            Numeric metrics snapshot.
        timeout : float | None
            Global timeout used for the run.
        runtime_seconds : float | None
            Total runtime of the search pipeline.
        """
        self.query = query
        self.since = since
        self.until = until
        self.limit = limit
        self.limit_per_database = limit_per_database
        processed_at = (
            processed_at
            if processed_at is not None
            else datetime.datetime.now(datetime.timezone.utc)
        )
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=datetime.timezone.utc)
        self.processed_at = processed_at
        self.databases = databases
        self.publication_types = publication_types
        self.papers: List[Paper] = papers or []
        self.metrics: dict[str, int | float] = dict(metrics or {})
        self.timeout = timeout
        self.runtime_seconds = runtime_seconds

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

    def to_dict(self) -> dict[str, object]:
        """Serialize search to a dictionary representation.

        Returns
        -------
        dict[str, object]
            Dictionary representation of the search.
        """
        limits = None
        if self.limit is not None or self.limit_per_database is not None:
            limits = {
                "limit": self.limit,
                "limit_per_database": self.limit_per_database,
            }
        metadata = {
            "query": self.query,
            "databases": self.databases,
            "limits": limits,
            "timeout": self.timeout,
            "timestamp": self.processed_at.astimezone(datetime.timezone.utc).isoformat(),
            "version": package_version(),
            "runtime_seconds": self.runtime_seconds,
        }
        return {
            "metadata": metadata,
            "papers": [Paper.to_dict(paper) for paper in self.papers],
            "metrics": dict(self.metrics),
        }

    def to_json(self, path: str) -> None:
        """Export search results to a JSON file.

        Parameters
        ----------
        path : str
            Output path for JSON export.

        Returns
        -------
        None
        """
        export_search_to_json(self, path)

    def to_csv(self, path: str) -> None:
        """Export search results to a CSV file.

        Parameters
        ----------
        path : str
            Output path for CSV export.

        Returns
        -------
        None
        """
        export_search_to_csv(self, path)

    def to_bibtex(self, path: str) -> None:
        """Export search results to a BibTeX file.

        Parameters
        ----------
        path : str
            Output path for BibTeX export.

        Returns
        -------
        None
        """
        export_search_to_bibtex(self, path)
