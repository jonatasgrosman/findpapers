"""Dedicated tests for :class:`SearchResult`."""

from __future__ import annotations

import datetime

import pytest

from findpapers.core.paper import Database
from findpapers.core.search_result import SearchResult
from findpapers.core.source import Source

# ---------------------------------------------------------------------------
# Database enum
# ---------------------------------------------------------------------------


class TestDatabase:
    """Tests for the Database enum."""

    def test_members_match_string_values(self) -> None:
        """Each enum member is equal to its raw string value."""
        assert Database.ARXIV == "arxiv"
        assert Database.CROSSREF == "crossref"
        assert Database.IEEE == "ieee"
        assert Database.OPENALEX == "openalex"
        assert Database.PUBMED == "pubmed"
        assert Database.SCOPUS == "scopus"
        assert Database.SEMANTIC_SCHOLAR == "semantic_scholar"

    def test_all_members_present(self) -> None:
        """Eight databases are defined."""
        assert len(Database) == 8


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestSearchResultInit:
    """Tests for SearchResult construction defaults."""

    def test_defaults(self) -> None:
        """Minimal construction populates defaults correctly."""
        sr = SearchResult(query="[test]")
        assert sr.query == "[test]"
        assert sr.since is None
        assert sr.until is None
        assert sr.max_papers_per_database is None
        assert sr.databases is None
        assert sr.papers == []
        assert sr.runtime_seconds is None
        assert sr.runtime_seconds_per_database == {}

    def test_processed_at_auto_utc(self) -> None:
        """When processed_at is omitted, a UTC timestamp is generated."""
        sr = SearchResult(query="[q]")
        assert sr.processed_at.tzinfo is not None

    def test_naive_processed_at_gets_utc(self) -> None:
        """A naive datetime is upgraded to UTC."""
        naive = datetime.datetime(2024, 6, 15, 12, 0, 0)
        sr = SearchResult(query="[q]", processed_at=naive)
        assert sr.processed_at.tzinfo == datetime.timezone.utc

    def test_aware_processed_at_kept(self) -> None:
        """An already-aware datetime is left unchanged."""
        aware = datetime.datetime(2024, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sr = SearchResult(query="[q]", processed_at=aware)
        assert sr.processed_at == aware

    def test_initial_papers(self, make_paper) -> None:
        """Papers passed at construction are stored."""
        p = make_paper(title="Init Paper")
        sr = SearchResult(query="[q]", papers=[p])
        assert len(sr.papers) == 1
        assert sr.papers[0].title == "Init Paper"


# ---------------------------------------------------------------------------
# add_paper / remove_paper
# ---------------------------------------------------------------------------


class TestAddRemovePaper:
    """Tests for add_paper and remove_paper."""

    def test_add_paper(self, make_paper) -> None:
        """add_paper appends to the list."""
        sr = SearchResult(query="[q]")
        p = make_paper()
        sr.add_paper(p)
        assert len(sr.papers) == 1

    def test_remove_paper(self, make_paper) -> None:
        """remove_paper deletes a paper that is present."""
        sr = SearchResult(query="[q]")
        p = make_paper()
        sr.add_paper(p)
        sr.remove_paper(p)
        assert len(sr.papers) == 0

    def test_remove_paper_not_present(self, make_paper) -> None:
        """remove_paper on a missing paper is a no-op."""
        sr = SearchResult(query="[q]")
        p = make_paper()
        sr.remove_paper(p)  # should not raise
        assert len(sr.papers) == 0


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSearchResultSerialization:
    """Tests for to_dict / from_dict."""

    @pytest.fixture
    def full_search(self, make_paper) -> SearchResult:
        """A SearchResult with representative field values."""
        p = make_paper(
            title="Serialize Me",
            doi="10.1234/test",
            source=Source(title="Journal"),
        )
        return SearchResult(
            query="[serialize]",
            since=datetime.date(2022, 1, 1),
            until=datetime.date(2023, 12, 31),
            max_papers_per_database=100,
            databases=["arxiv", "scopus"],
            papers=[p],
            runtime_seconds=12.5,
            runtime_seconds_per_database={"arxiv": 7.0, "scopus": 5.5},
        )

    def test_to_dict_structure(self, full_search: SearchResult) -> None:
        """to_dict returns metadata + papers keys."""
        d = full_search.to_dict()
        assert "metadata" in d
        assert "papers" in d
        assert isinstance(d["papers"], list)

    def test_round_trip_preserves_query(self, full_search: SearchResult) -> None:
        """query survives serialization round-trip."""
        restored = SearchResult.from_dict(full_search.to_dict())
        assert restored.query == "[serialize]"

    def test_round_trip_preserves_dates(self, full_search: SearchResult) -> None:
        """since / until survive serialization round-trip."""
        restored = SearchResult.from_dict(full_search.to_dict())
        assert restored.since == datetime.date(2022, 1, 1)
        assert restored.until == datetime.date(2023, 12, 31)

    def test_round_trip_preserves_papers(self, full_search: SearchResult) -> None:
        """Papers survive serialization round-trip."""
        restored = SearchResult.from_dict(full_search.to_dict())
        assert len(restored.papers) == 1
        assert restored.papers[0].title == "Serialize Me"

    def test_round_trip_preserves_databases(self, full_search: SearchResult) -> None:
        """databases list survives serialization round-trip."""
        restored = SearchResult.from_dict(full_search.to_dict())
        assert restored.databases == ["arxiv", "scopus"]

    def test_round_trip_preserves_runtime(self, full_search: SearchResult) -> None:
        """Runtime fields survive serialization round-trip."""
        restored = SearchResult.from_dict(full_search.to_dict())
        assert restored.runtime_seconds == 12.5
        assert restored.runtime_seconds_per_database == {"arxiv": 7.0, "scopus": 5.5}

    def test_none_dates_serialized(self) -> None:
        """None since/until serialize as None in metadata."""
        sr = SearchResult(query="[q]")
        d = sr.to_dict()
        metadata = d["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["since"] is None
        assert metadata["until"] is None

    def test_from_dict_with_empty_data(self) -> None:
        """from_dict with minimal data does not raise."""
        sr = SearchResult.from_dict({"metadata": {}, "papers": []})
        assert sr.query == ""
        assert sr.papers == []

    def test_from_dict_bad_timestamp_ignored(self) -> None:
        """An unparseable timestamp is silently ignored."""
        sr = SearchResult.from_dict({"metadata": {"timestamp": "not-a-date"}, "papers": []})
        # processed_at gets a fresh UTC timestamp when parsing fails
        assert sr.processed_at is not None


# ---------------------------------------------------------------------------
# failed_databases tracking
# ---------------------------------------------------------------------------


class TestFailedDatabases:
    """Tests for the failed_databases field."""

    def test_default_is_empty_list(self) -> None:
        """When omitted, failed_databases defaults to an empty list."""
        sr = SearchResult(query="[q]")
        assert sr.failed_databases == []

    def test_explicit_none_gives_empty_list(self) -> None:
        """Passing None explicitly still yields an empty list internally."""
        sr = SearchResult(query="[q]", failed_databases=None)
        assert sr.failed_databases == []

    def test_stores_provided_values(self) -> None:
        """Provided database names are stored."""
        sr = SearchResult(query="[q]", failed_databases=["arxiv", "ieee"])
        assert sr.failed_databases == ["arxiv", "ieee"]

    def test_to_dict_includes_failed_databases(self) -> None:
        """to_dict serializes failed_databases into metadata."""
        sr = SearchResult(query="[q]", failed_databases=["scopus"])
        d = sr.to_dict()
        assert d["metadata"]["failed_databases"] == ["scopus"]

    def test_to_dict_empty_list_when_no_failures(self) -> None:
        """to_dict serializes empty list as [] to distinguish from missing data."""
        sr = SearchResult(query="[q]")
        d = sr.to_dict()
        assert d["metadata"]["failed_databases"] == []

    def test_round_trip_with_failures(self) -> None:
        """failed_databases survives a to_dict / from_dict round-trip."""
        sr = SearchResult(query="[q]", failed_databases=["ieee", "pubmed"])
        restored = SearchResult.from_dict(sr.to_dict())
        assert restored.failed_databases == ["ieee", "pubmed"]

    def test_round_trip_without_failures(self) -> None:
        """An empty failed_databases round-trips without error."""
        sr = SearchResult(query="[q]")
        restored = SearchResult.from_dict(sr.to_dict())
        assert restored.failed_databases == []

    def test_from_dict_missing_key(self) -> None:
        """Older saves without the key produce an empty list."""
        sr = SearchResult.from_dict({"metadata": {}, "papers": []})
        assert sr.failed_databases == []


# ---------------------------------------------------------------------------
# enrichment_databases and max_cited_by tracking
# ---------------------------------------------------------------------------


class TestEnrichmentMetadata:
    """Tests for enrichment_databases and max_cited_by fields."""

    def test_defaults_are_none(self) -> None:
        """enrichment_databases and max_cited_by default to None."""
        sr = SearchResult(query="[q]")
        assert sr.enrichment_databases is None
        assert sr.max_cited_by is None

    def test_stores_provided_values(self) -> None:
        """Provided values are stored."""
        sr = SearchResult(
            query="[q]",
            enrichment_databases=["crossref", "web_scraping"],
            max_cited_by=50,
        )
        assert sr.enrichment_databases == ["crossref", "web_scraping"]
        assert sr.max_cited_by == 50

    def test_to_dict_includes_enrichment_metadata(self) -> None:
        """to_dict serializes enrichment_databases and max_cited_by."""
        sr = SearchResult(
            query="[q]",
            enrichment_databases=["crossref"],
            max_cited_by=100,
        )
        meta = sr.to_dict()["metadata"]
        assert meta["enrichment_databases"] == ["crossref"]
        assert meta["max_cited_by"] == 100

    def test_to_dict_none_values_serialized(self) -> None:
        """None enrichment_databases and max_cited_by appear as null in metadata."""
        sr = SearchResult(query="[q]")
        meta = sr.to_dict()["metadata"]
        assert meta["enrichment_databases"] is None
        assert meta["max_cited_by"] is None

    def test_round_trip_with_enrichment_metadata(self) -> None:
        """enrichment_databases and max_cited_by survive a to_dict/from_dict round-trip."""
        sr = SearchResult(
            query="[q]",
            enrichment_databases=["crossref", "web_scraping"],
            max_cited_by=75,
        )
        restored = SearchResult.from_dict(sr.to_dict())
        assert restored.enrichment_databases == ["crossref", "web_scraping"]
        assert restored.max_cited_by == 75

    def test_round_trip_with_none_values(self) -> None:
        """None values survive a to_dict/from_dict round-trip."""
        sr = SearchResult(query="[q]")
        restored = SearchResult.from_dict(sr.to_dict())
        assert restored.enrichment_databases is None
        assert restored.max_cited_by is None

    def test_from_dict_missing_keys_give_none(self) -> None:
        """Older saves without these keys yield None (backward compatibility)."""
        sr = SearchResult.from_dict({"metadata": {}, "papers": []})
        assert sr.enrichment_databases is None
        assert sr.max_cited_by is None
