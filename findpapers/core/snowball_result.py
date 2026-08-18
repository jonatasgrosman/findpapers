"""SnowballResult: container for snowballing metadata and discovered papers."""

from __future__ import annotations

import contextlib
import datetime
from typing import Any, Literal

from ..utils.version import package_version
from .paper import Paper


class SnowballResult:
    """Represents a snowball configuration and its discovered papers.

    Holds the seed paper reference, traversal settings, and the flat list of
    :class:`~findpapers.core.paper.Paper` objects *discovered* during the BFS
    traversal.  The seed paper is **not** included in :attr:`papers`: it is
    accessible via :attr:`seed_paper`.  Citation relationships are encoded
    directly on each paper via
    :attr:`~findpapers.core.paper.Paper.references` and
    :attr:`~findpapers.core.paper.Paper.cited_by`.

    Parameters
    ----------
    seed_paper : Paper
        Enriched seed paper (fetched via GetRunner; original used as fallback
        when lookup fails).  It is **not** duplicated in :attr:`papers`.
    max_depth : int
        Maximum BFS traversal depth used.
    direction : Literal["both", "backward", "forward"]
        Snowball direction(s) used.
    since : datetime.date | None
        Lower-bound publication date filter applied to discovered papers.
    until : datetime.date | None
        Upper-bound publication date filter applied to discovered papers.
    databases : list[str] | None
        Database identifiers passed to
        :class:`~findpapers.runners.get_runner.GetRunner` for each lookup.
        ``None`` means all available databases were used.
    max_papers_per_level : int | None
        Per-level result cap.  Only the *top N* most-cited papers discovered
        at each level are kept in the final result.  Seed papers are never
        filtered.  ``None`` means no cap was applied.
    max_expansion_per_level : int | None
        Per-level frontier cap.  Only the *top N* most-cited papers from each
        level are used as seeds for the next BFS round.  All papers already
        added to the result are unaffected.  ``None`` means no cap.
    papers : list[Paper] | None
        Papers *discovered* during BFS traversal (seed excluded).
        ``None`` is treated as an empty list.
    processed_at : datetime.datetime | None
        Timestamp at which the snowball was executed.  Defaults to
        :func:`datetime.datetime.now`.
    runtime_seconds : float | None
        Wall-clock runtime of the snowball pipeline.
    """

    def __init__(
        self,
        seed_paper: Paper,
        max_depth: int,
        direction: Literal["both", "backward", "forward"],
        since: datetime.date | None = None,
        until: datetime.date | None = None,
        databases: list[str] | None = None,
        max_papers_per_level: int | None = None,
        max_expansion_per_level: int | None = None,
        papers: list[Paper] | None = None,
        processed_at: datetime.datetime | None = None,
        runtime_seconds: float | None = None,
        enrichment_databases: list[str] | None = None,
        max_cited_by: int | None = None,
    ) -> None:
        """Create a SnowballResult instance.

        Parameters
        ----------
        seed_paper : Paper
            Enriched seed paper used as the BFS starting point.
        max_depth : int
            Maximum BFS traversal depth.
        direction : Literal["both", "backward", "forward"]
            Snowball direction(s).
        since : datetime.date | None
            Lower-bound publication date filter.
        until : datetime.date | None
            Upper-bound publication date filter.
        databases : list[str] | None
            Database identifiers used for each lookup.
        max_papers_per_level : int | None
            Per-level result cap (top-N most-cited papers kept per level).
        max_expansion_per_level : int | None
            Per-level frontier cap (top-N most-cited papers used as next-level seeds).
        papers : list[Paper] | None
            Discovered papers (seed excluded).
        processed_at : datetime.datetime | None
            Execution timestamp.  Defaults to now (UTC).
        runtime_seconds : float | None
            Wall-clock runtime.
        enrichment_databases : list[str] | None
            Databases used for the final post-BFS enrichment pass on discovered
            papers.
        max_cited_by : int | None
            Maximum number of citing-paper DOIs collected per paper during
            forward snowball expansion.
        """
        self.seed_paper: Paper = seed_paper
        self.max_depth = max_depth
        self.direction = direction
        self.since = since
        self.until = until
        self.databases = databases
        self.max_papers_per_level = max_papers_per_level
        self.max_expansion_per_level = max_expansion_per_level
        self.papers: list[Paper] = list(papers) if papers is not None else []
        self.runtime_seconds = runtime_seconds
        self.enrichment_databases = enrichment_databases
        self.max_cited_by = max_cited_by

        if processed_at is None:
            processed_at = datetime.datetime.now(datetime.UTC)
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=datetime.UTC)
        self.processed_at = processed_at

    def add_paper(self, paper: Paper) -> None:
        """Append a paper to the result.

        Parameters
        ----------
        paper : Paper
            Paper to add.

        Returns
        -------
        None
        """
        self.papers.append(paper)

    def remove_paper(self, paper: Paper) -> None:
        """Remove a paper from the result if present.

        Parameters
        ----------
        paper : Paper
            Paper to remove.

        Returns
        -------
        None
        """
        if paper in self.papers:
            self.papers.remove(paper)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snowball result to a dictionary.

        Returns
        -------
        dict[str, Any]
            Dictionary with ``"metadata"`` and ``"papers"`` keys, suitable
            for JSON serialization.
        """
        return {
            "metadata": {
                "seed_paper": {"doi": self.seed_paper.doi, "title": self.seed_paper.title},
                "max_depth": self.max_depth,
                "direction": self.direction,
                "since": self.since.isoformat() if self.since else None,
                "until": self.until.isoformat() if self.until else None,
                "databases": self.databases,
                "enrichment_databases": self.enrichment_databases,
                "max_cited_by": self.max_cited_by,
                "max_papers_per_level": self.max_papers_per_level,
                "max_expansion_per_level": self.max_expansion_per_level,
                "timestamp": self.processed_at.astimezone(datetime.UTC).isoformat(),
                "version": package_version(),
                "runtime_seconds": self.runtime_seconds,
            },
            "papers": [paper.to_dict() for paper in self.papers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SnowballResult:
        """Reconstruct a SnowballResult from a dictionary.

        Accepts the format produced by :meth:`to_dict`.

        Parameters
        ----------
        data : dict
            Dictionary with ``"metadata"`` and ``"papers"`` keys.

        Returns
        -------
        SnowballResult
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

        # Reconstruct a minimal seed Paper object from the stored summary.
        seed_data = metadata.get("seed_paper") or {}
        seed_paper = Paper(
            title=seed_data.get("title") or "(unknown seed paper)",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            doi=seed_data.get("doi"),
        )

        return cls(
            seed_paper=seed_paper,
            max_depth=metadata.get("max_depth", 1),
            direction=metadata.get("direction", "both"),
            since=since,
            until=until,
            databases=metadata.get("databases"),
            max_papers_per_level=metadata.get("max_papers_per_level"),
            max_expansion_per_level=metadata.get("max_expansion_per_level"),
            papers=[Paper.from_dict(p) for p in raw_papers],
            processed_at=processed_at,
            runtime_seconds=metadata.get("runtime_seconds"),
            enrichment_databases=metadata.get("enrichment_databases"),
            max_cited_by=metadata.get("max_cited_by"),
        )
