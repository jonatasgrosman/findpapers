"""Unit tests for SimilarResult."""

from __future__ import annotations

import datetime

from findpapers.core.paper import Paper
from findpapers.core.similar_result import SimilarResult


def _make_paper(title: str = "Test", doi: str | None = None) -> Paper:
    """Create a minimal Paper for testing.

    Parameters
    ----------
    title : str
        Paper title.
    doi : str | None
        Optional DOI.

    Returns
    -------
    Paper
        A minimal paper instance.
    """
    return Paper(
        title=title,
        abstract="Abstract",
        authors=[],
        source=None,
        publication_date=datetime.date(2024, 1, 1),
        doi=doi,
    )


class TestSimilarResultConstruction:
    """Tests for SimilarResult construction defaults."""

    def test_defaults(self) -> None:
        """None inputs default to empty collections; processed_at defaults to now."""
        seed = _make_paper("Seed", doi="10.1000/seed")
        result = SimilarResult(seed_paper=seed)

        assert result.seed_paper is seed
        assert result.papers == []
        assert result.failed_databases == []
        assert result.skipped_databases == []
        assert result.processed_at.tzinfo is not None

    def test_explicit_values_preserved(self) -> None:
        """Explicitly passed values are stored as-is."""
        seed = _make_paper("Seed", doi="10.1000/seed")
        related = [_make_paper("Related", doi="10.1000/related")]
        result = SimilarResult(
            seed_paper=seed,
            databases=["semantic_scholar"],
            max_papers_per_database=10,
            papers=related,
            runtime_seconds=1.5,
            failed_databases=["openalex"],
            skipped_databases=["pubmed"],
        )

        assert result.databases == ["semantic_scholar"]
        assert result.max_papers_per_database == 10
        assert result.papers == related
        assert result.runtime_seconds == 1.5
        assert result.failed_databases == ["openalex"]
        assert result.skipped_databases == ["pubmed"]


class TestSimilarResultMutation:
    """Tests for add_paper / remove_paper."""

    def test_add_paper(self) -> None:
        """add_paper appends to the papers list."""
        result = SimilarResult(seed_paper=_make_paper(doi="10.1000/seed"))
        paper = _make_paper("New", doi="10.1000/new")

        result.add_paper(paper)

        assert result.papers == [paper]

    def test_remove_paper(self) -> None:
        """remove_paper removes an existing paper; no-op when absent."""
        paper = _make_paper("Existing", doi="10.1000/existing")
        result = SimilarResult(seed_paper=_make_paper(doi="10.1000/seed"), papers=[paper])

        result.remove_paper(paper)
        assert result.papers == []

        # Removing again is a no-op, not an error.
        result.remove_paper(paper)
        assert result.papers == []


class TestSimilarResultRoundTrip:
    """Tests for to_dict / from_dict round-tripping."""

    def test_round_trip_preserves_key_fields(self) -> None:
        """to_dict -> from_dict preserves seed identity, metadata, and papers."""
        seed = _make_paper("Seed Paper", doi="10.1000/seed")
        related = [
            _make_paper("Related One", doi="10.1000/one"),
            _make_paper("Related Two", doi="10.1000/two"),
        ]
        original = SimilarResult(
            seed_paper=seed,
            databases=["semantic_scholar", "openalex"],
            max_papers_per_database=20,
            papers=related,
            runtime_seconds=3.2,
            failed_databases=["pubmed"],
            skipped_databases=[],
        )

        data = original.to_dict()
        assert data["metadata"]["seed_paper"] == {"doi": "10.1000/seed", "title": "Seed Paper"}
        assert "papers" in data

        restored = SimilarResult.from_dict(data)

        assert restored.seed_paper.doi == seed.doi
        assert restored.seed_paper.title == seed.title
        assert restored.databases == ["semantic_scholar", "openalex"]
        assert restored.max_papers_per_database == 20
        assert restored.runtime_seconds == 3.2
        assert restored.failed_databases == ["pubmed"]
        assert restored.skipped_databases == []
        assert len(restored.papers) == 2
        assert {p.doi for p in restored.papers} == {"10.1000/one", "10.1000/two"}

    def test_from_dict_with_missing_metadata_defaults_gracefully(self) -> None:
        """Missing/partial metadata does not raise; falls back to safe defaults."""
        result = SimilarResult.from_dict({"metadata": {}, "papers": []})

        assert result.seed_paper.title == "(unknown seed paper)"
        assert result.seed_paper.doi is None
        assert result.papers == []
        assert result.failed_databases == []
        assert result.skipped_databases == []
