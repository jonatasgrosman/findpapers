"""Search result container that aggregates papers from multiple databases."""

from __future__ import annotations

import contextlib
import datetime
from typing import Any

from ..utils.version import package_version
from .paper import Paper


class SearchResult:
    """Represents a search configuration and results."""

    def __init__(
        self,
        query: str,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
        max_papers_per_database: int | None = None,
        processed_at: datetime.datetime | None = None,
        databases: list[str] | None = None,
        papers: list[Paper] | None = None,
        runtime_seconds: float | None = None,
        runtime_seconds_per_database: dict[str, float] | None = None,
        failed_databases: list[str] | None = None,
        enrichment_databases: list[str] | None = None,
        max_cited_by: int | None = None,
    ) -> None:
        """Create a SearchResult instance.

        Parameters
        ----------
        query : str
            Search query.
        since : datetime.date | None
            Lower bound date.
        until : datetime.date | None
            Upper bound date.
        max_papers_per_database : int | None
            Maximum papers per database.
        processed_at : datetime.datetime | None
            Processing timestamp.
        databases : list[str] | None
            Database identifiers.
        papers : list[Paper] | None
            Initial papers.
        runtime_seconds : float | None
            Total runtime of the search pipeline.
        runtime_seconds_per_database : dict[str, float] | None
            Runtime in seconds for each database.
        failed_databases : list[str] | None
            Database identifiers that failed during search (network error,
            connector error, etc.).  ``None`` means the information was not
            recorded (e.g. loaded from an older save).
        enrichment_databases : list[str] | None
            Databases used for post-search paper enrichment.
        max_cited_by : int | None
            Maximum number of citing-paper DOIs collected per paper during
            enrichment.
        """
        self.query = query
        self.since = since
        self.until = until
        self.max_papers_per_database = max_papers_per_database
        processed_at = (
            processed_at if processed_at is not None else datetime.datetime.now(datetime.UTC)
        )
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=datetime.UTC)
        self.processed_at = processed_at
        self.databases = databases
        self.papers: list[Paper] = papers or []
        self.runtime_seconds = runtime_seconds
        self.runtime_seconds_per_database: dict[str, float] = dict(
            runtime_seconds_per_database or {}
        )
        self.failed_databases: list[str] = list(failed_databases or [])
        self.enrichment_databases = enrichment_databases
        self.max_cited_by = max_cited_by

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize search to a dictionary representation.

        Returns
        -------
        dict[str, Any]
            Dictionary representation of the search.
        """
        metadata = {
            "query": self.query,
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "databases": self.databases,
            "max_papers_per_database": self.max_papers_per_database,
            "enrichment_databases": self.enrichment_databases,
            "max_cited_by": self.max_cited_by,
            "timestamp": self.processed_at.astimezone(datetime.UTC).isoformat(),
            "version": package_version(),
            "runtime_seconds": self.runtime_seconds,
            "runtime_seconds_per_database": dict(self.runtime_seconds_per_database),
            "failed_databases": self.failed_databases,
        }
        return {
            "metadata": metadata,
            "papers": [paper.to_dict() for paper in self.papers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SearchResult:
        """Reconstruct a SearchResult from a dictionary.

        Accepts the format produced by :meth:`to_dict` (and by
        :func:`~findpapers.utils.persistence.save_to_json`).

        Parameters
        ----------
        data : dict
            Dictionary with ``"metadata"`` and ``"papers"`` keys.

        Returns
        -------
        SearchResult
            Reconstructed instance.
        """
        metadata = data.get("metadata", {})
        raw_papers = data.get("papers", [])

        processed_at: datetime.datetime | None = None
        ts = metadata.get("timestamp")
        if isinstance(ts, str):
            with contextlib.suppress(ValueError):
                processed_at = datetime.datetime.fromisoformat(ts)

        since: datetime.date | None = None
        since_str = metadata.get("since")
        if isinstance(since_str, str):
            with contextlib.suppress(ValueError):
                since = datetime.date.fromisoformat(since_str)

        until: datetime.date | None = None
        until_str = metadata.get("until")
        if isinstance(until_str, str):
            with contextlib.suppress(ValueError):
                until = datetime.date.fromisoformat(until_str)

        return cls(
            query=metadata.get("query", ""),
            since=since,
            until=until,
            databases=metadata.get("databases"),
            max_papers_per_database=metadata.get("max_papers_per_database"),
            processed_at=processed_at,
            papers=[Paper.from_dict(p) for p in raw_papers],
            runtime_seconds=metadata.get("runtime_seconds"),
            runtime_seconds_per_database=metadata.get("runtime_seconds_per_database"),
            failed_databases=metadata.get("failed_databases"),
            enrichment_databases=metadata.get("enrichment_databases"),
            max_cited_by=metadata.get("max_cited_by"),
        )
