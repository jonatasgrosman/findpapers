"""SimilarResult: container for a single-hop content-similarity lookup."""

from __future__ import annotations

import contextlib
import datetime
from typing import Any

from ..utils.version import package_version
from .paper import Paper


class SimilarResult:
    """Represents a content-similarity lookup around a single seed paper.

    Unlike :class:`~findpapers.core.snowball_result.SnowballResult`, which
    covers a multi-level BFS citation-graph traversal over one or more seed
    papers, this holds the result of a single-hop lookup around exactly one
    seed paper: papers judged topically/semantically similar by each queried
    source's own signal (Semantic Scholar SPECTER-based recommendations,
    PubMed's PMRA related-articles score, OpenAlex's ``related_works``).

    Parameters
    ----------
    seed_paper : Paper
        The paper the similarity lookup was performed around.
    databases : list[str] | None
        Sources that were requested, in priority order.  ``None`` means all
        available sources were requested.
    max_papers_per_database : int | None
        Cap on the number of related papers requested/kept from each source
        before merging.  ``None`` means each source's own natural default
        was used.
    papers : list[Paper] | None
        Related papers found, deduplicated and merged across sources.  The
        seed paper itself is never included.  ``None`` is treated as an
        empty list.
    processed_at : datetime.datetime | None
        Timestamp at which the lookup was executed.  Defaults to
        :func:`datetime.datetime.now` (UTC).
    runtime_seconds : float | None
        Wall-clock runtime of the lookup.
    failed_databases : list[str] | None
        Sources that were queried but raised an error.  ``None`` is treated
        as an empty list.
    skipped_databases : list[str] | None
        Sources that were not queried because they do not apply to this seed
        paper (e.g. PubMed when no PMID could be resolved, or every source
        when the seed paper has no DOI).  Distinct from *failed_databases*:
        a skip is an expected outcome, not an error.  ``None`` is treated as
        an empty list.
    """

    def __init__(
        self,
        seed_paper: Paper,
        databases: list[str] | None = None,
        max_papers_per_database: int | None = None,
        papers: list[Paper] | None = None,
        processed_at: datetime.datetime | None = None,
        runtime_seconds: float | None = None,
        failed_databases: list[str] | None = None,
        skipped_databases: list[str] | None = None,
    ) -> None:
        """Create a SimilarResult instance.

        Parameters
        ----------
        seed_paper : Paper
            The paper the similarity lookup was performed around.
        databases : list[str] | None
            Sources that were requested, in priority order.
        max_papers_per_database : int | None
            Cap on the number of related papers kept from each source.
        papers : list[Paper] | None
            Related papers found (seed excluded).
        processed_at : datetime.datetime | None
            Execution timestamp.  Defaults to now (UTC).
        runtime_seconds : float | None
            Wall-clock runtime.
        failed_databases : list[str] | None
            Sources that were queried but raised an error.
        skipped_databases : list[str] | None
            Sources that were not applicable to this seed paper.
        """
        self.seed_paper = seed_paper
        self.databases = databases
        self.max_papers_per_database = max_papers_per_database
        self.papers: list[Paper] = list(papers) if papers is not None else []
        self.runtime_seconds = runtime_seconds
        self.failed_databases: list[str] = list(failed_databases) if failed_databases else []
        self.skipped_databases: list[str] = list(skipped_databases) if skipped_databases else []

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
        """Serialize the similar result to a dictionary.

        Returns
        -------
        dict[str, Any]
            Dictionary with ``"metadata"`` and ``"papers"`` keys, suitable
            for JSON serialization.
        """
        return {
            "metadata": {
                "seed_paper": {"doi": self.seed_paper.doi, "title": self.seed_paper.title},
                "databases": self.databases,
                "max_papers_per_database": self.max_papers_per_database,
                "failed_databases": self.failed_databases,
                "skipped_databases": self.skipped_databases,
                "timestamp": self.processed_at.astimezone(datetime.UTC).isoformat(),
                "version": package_version(),
                "runtime_seconds": self.runtime_seconds,
            },
            "papers": [paper.to_dict() for paper in self.papers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SimilarResult:
        """Reconstruct a SimilarResult from a dictionary.

        Accepts the format produced by :meth:`to_dict`.

        Parameters
        ----------
        data : dict
            Dictionary with ``"metadata"`` and ``"papers"`` keys.

        Returns
        -------
        SimilarResult
            Reconstructed instance.
        """
        metadata = data.get("metadata", {})
        raw_papers = data.get("papers", [])

        processed_at: datetime.datetime | None = None
        ts = metadata.get("timestamp")
        if isinstance(ts, str):
            with contextlib.suppress(ValueError):
                processed_at = datetime.datetime.fromisoformat(ts)

        # Reconstruct a minimal seed Paper object from the stored summary.
        seed_data = metadata.get("seed_paper") or {}
        doi = seed_data.get("doi")
        title = seed_data.get("title") or ""
        seed_paper = Paper(
            title=title or "(unknown seed paper)",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            doi=doi,
        )

        return cls(
            seed_paper=seed_paper,
            databases=metadata.get("databases"),
            max_papers_per_database=metadata.get("max_papers_per_database"),
            papers=[Paper.from_dict(p) for p in raw_papers],
            processed_at=processed_at,
            runtime_seconds=metadata.get("runtime_seconds"),
            failed_databases=metadata.get("failed_databases"),
            skipped_databases=metadata.get("skipped_databases"),
        )
