"""Unit tests for SnowballResult."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from findpapers.core.paper import Paper
from findpapers.core.snowball_result import SnowballResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_result(**kwargs) -> SnowballResult:
    """Create a SnowballResult with sensible defaults for testing.

    Parameters
    ----------
    **kwargs : object
        Keyword arguments forwarded to SnowballResult.

    Returns
    -------
    SnowballResult
        Instance with defaults for unspecified fields.
    """
    defaults: dict = {
        "seed_papers": [],
        "max_depth": 1,
        "direction": "both",
    }
    defaults.update(kwargs)
    return SnowballResult(**defaults)


# ---------------------------------------------------------------------------
# TestSnowballResultInit
# ---------------------------------------------------------------------------


class TestSnowballResultInit:
    """Tests for SnowballResult.__init__."""

    def test_defaults(self) -> None:
        """Unspecified optional fields get sensible defaults."""
        result = _make_result()

        assert result.since is None
        assert result.until is None
        assert result.databases is None
        assert result.max_per_level is None
        assert result.max_expansion_per_level is None
        assert result.papers == []
        assert result.runtime_seconds is None
        assert result.skipped_seeds_without_doi == 0

    def test_processed_at_defaults_to_now_utc(self) -> None:
        """processed_at defaults to a UTC-aware datetime close to now."""
        before = datetime.datetime.now(datetime.UTC)
        result = _make_result()
        after = datetime.datetime.now(datetime.UTC)

        assert result.processed_at.tzinfo is not None
        assert before <= result.processed_at <= after

    def test_processed_at_naive_becomes_utc(self) -> None:
        """A naive processed_at is given UTC tzinfo."""
        naive = datetime.datetime(2024, 1, 1, 12, 0, 0)
        result = _make_result(processed_at=naive)
        assert result.processed_at.tzinfo is not None

    def test_processed_at_aware_is_kept_unchanged(self) -> None:
        """An already-aware processed_at is stored as-is."""
        aware = datetime.datetime(2024, 6, 15, 10, 0, 0, tzinfo=datetime.UTC)
        result = _make_result(processed_at=aware)
        assert result.processed_at == aware

    def test_papers_none_becomes_empty_list(self) -> None:
        """Passing papers=None yields an empty list."""
        result = _make_result(papers=None)
        assert result.papers == []

    def test_seed_papers_are_copied(self) -> None:
        """seed_papers input list is copied (mutations do not affect result)."""
        seeds = [_make_paper("S", doi="10.0/s")]
        result = _make_result(seed_papers=seeds)
        seeds.append(_make_paper("Extra"))
        assert len(result.seed_papers) == 1

    def test_papers_list_is_copied(self) -> None:
        """papers input list is copied (mutations do not affect result)."""
        papers = [_make_paper("P", doi="10.0/p")]
        result = _make_result(papers=papers)
        papers.append(_make_paper("Extra"))
        assert len(result.papers) == 1


# ---------------------------------------------------------------------------
# TestAddRemovePaper
# ---------------------------------------------------------------------------


class TestAddRemovePaper:
    """Tests for add_paper() and remove_paper()."""

    def test_add_paper_appends_to_papers(self) -> None:
        """add_paper() appends the paper to the papers list."""
        result = _make_result()
        paper = _make_paper("P", doi="10.0/p")
        result.add_paper(paper)
        assert paper in result.papers

    def test_remove_paper_removes_existing(self) -> None:
        """remove_paper() removes a present paper."""
        paper = _make_paper("P", doi="10.0/p")
        result = _make_result(papers=[paper])
        result.remove_paper(paper)
        assert paper not in result.papers

    def test_remove_paper_not_present_is_noop(self) -> None:
        """remove_paper() does not raise when the paper is absent."""
        result = _make_result()
        paper = _make_paper("Absent", doi="10.0/absent")
        result.remove_paper(paper)  # Must not raise.
        assert result.papers == []


# ---------------------------------------------------------------------------
# TestToDict
# ---------------------------------------------------------------------------


class TestToDict:
    """Tests for SnowballResult.to_dict()."""

    def test_returns_dict(self) -> None:
        """to_dict() returns a dict."""
        result = _make_result()
        assert isinstance(result.to_dict(), dict)

    def test_top_level_keys(self) -> None:
        """to_dict() always has 'metadata' and 'papers' keys."""
        data = _make_result().to_dict()
        assert "metadata" in data
        assert "papers" in data

    def test_metadata_fields(self) -> None:
        """Metadata contains expected sub-fields."""
        seed = _make_paper("Seed", doi="10.0/seed")
        result = SnowballResult(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
            since=datetime.date(2020, 1, 1),
            until=datetime.date(2023, 12, 31),
            databases=["crossref"],
            max_per_level=5,
            max_expansion_per_level=10,
            skipped_seeds_without_doi=1,
            runtime_seconds=1.23,
        )
        meta = result.to_dict()["metadata"]

        assert meta["max_depth"] == 2
        assert meta["direction"] == "backward"
        assert meta["since"] == "2020-01-01"
        assert meta["until"] == "2023-12-31"
        assert meta["databases"] == ["crossref"]
        assert meta["max_per_level"] == 5
        assert meta["max_expansion_per_level"] == 10
        assert meta["skipped_seeds_without_doi"] == 1
        assert meta["runtime_seconds"] == pytest.approx(1.23)  # type: ignore[attr-defined]
        assert "timestamp" in meta
        assert "version" in meta

    def test_seed_papers_in_metadata(self) -> None:
        """Seed papers are serialized as doi/title dicts in metadata."""
        seed = _make_paper("My Seed", doi="10.0/myseed")
        data = _make_result(seed_papers=[seed]).to_dict()
        seeds = data["metadata"]["seed_papers"]
        assert any(s["doi"] == "10.0/myseed" for s in seeds)

    def test_papers_serialized(self) -> None:
        """Discovered papers are included in the 'papers' key."""
        paper = _make_paper("Discovered", doi="10.0/disc")
        data = _make_result(papers=[paper]).to_dict()
        assert len(data["papers"]) == 1

    def test_none_since_until_serialized_as_none(self) -> None:
        """since=None and until=None appear as null in metadata."""
        data = _make_result().to_dict()
        assert data["metadata"]["since"] is None
        assert data["metadata"]["until"] is None


# ---------------------------------------------------------------------------
# TestFromDict
# ---------------------------------------------------------------------------


class TestFromDict:
    """Tests for SnowballResult.from_dict()."""

    def test_round_trip(self) -> None:
        """to_dict → from_dict produces an equivalent SnowballResult."""
        seed = _make_paper("Seed", doi="10.0/seed")
        paper = _make_paper("Paper", doi="10.0/p")
        original = SnowballResult(
            seed_papers=[seed],
            max_depth=2,
            direction="forward",
            since=datetime.date(2021, 1, 1),
            until=datetime.date(2023, 12, 31),
            databases=["openalex"],
            max_per_level=3,
            max_expansion_per_level=7,
            papers=[paper],
            runtime_seconds=0.5,
            skipped_seeds_without_doi=2,
        )
        data = original.to_dict()
        restored = SnowballResult.from_dict(data)

        assert restored.max_depth == original.max_depth
        assert restored.direction == original.direction
        assert restored.since == original.since
        assert restored.until == original.until
        assert restored.databases == original.databases
        assert restored.max_per_level == original.max_per_level
        assert restored.max_expansion_per_level == original.max_expansion_per_level
        assert restored.skipped_seeds_without_doi == original.skipped_seeds_without_doi
        assert restored.runtime_seconds == pytest.approx(original.runtime_seconds)  # type: ignore[attr-defined]
        assert len(restored.papers) == 1

    def test_missing_metadata_uses_defaults(self) -> None:
        """from_dict with empty metadata falls back to defaults."""
        data: dict[str, Any] = {"metadata": {}, "papers": []}
        result = SnowballResult.from_dict(data)
        assert result.max_depth == 1
        assert result.direction == "both"
        assert result.papers == []

    def test_invalid_since_is_ignored(self) -> None:
        """A malformed since date string is silently ignored."""
        data = {"metadata": {"since": "not-a-date"}, "papers": []}
        result = SnowballResult.from_dict(data)
        assert result.since is None

    def test_invalid_until_is_ignored(self) -> None:
        """A malformed until date string is silently ignored."""
        data = {"metadata": {"until": "bad"}, "papers": []}
        result = SnowballResult.from_dict(data)
        assert result.until is None

    def test_processed_at_parsed_from_timestamp(self) -> None:
        """A valid timestamp string is parsed into a datetime."""
        ts = "2024-05-01T10:00:00+00:00"
        data = {"metadata": {"timestamp": ts}, "papers": []}
        result = SnowballResult.from_dict(data)
        assert result.processed_at is not None
        assert result.processed_at.year == 2024

    def test_invalid_timestamp_yields_default(self) -> None:
        """An invalid timestamp falls back to now."""
        data = {"metadata": {"timestamp": "garbage"}, "papers": []}
        before = datetime.datetime.now(datetime.UTC)
        result = SnowballResult.from_dict(data)
        after = datetime.datetime.now(datetime.UTC)
        assert before <= result.processed_at <= after

    def test_seed_papers_reconstructed(self) -> None:
        """Seed papers saved as doi/title pairs are reconstructed as Papers."""
        data = {
            "metadata": {
                "seed_papers": [{"doi": "10.0/s", "title": "Seed"}],
            },
            "papers": [],
        }
        result = SnowballResult.from_dict(data)
        assert len(result.seed_papers) == 1
        assert result.seed_papers[0].doi == "10.0/s"
