"""Unit tests for SimilarRunner."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from findpapers.core.paper import Paper
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.similar_runner import SIMILAR_DATABASES, SimilarRunner


def _make_paper(title: str = "Test", doi: str | None = "10.1000/seed") -> Paper:
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


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSimilarRunnerValidation:
    """Tests for the databases parameter validation."""

    def test_none_uses_all_databases(self) -> None:
        """None selects every database in priority order."""
        runner = SimilarRunner(paper=_make_paper())
        assert runner._active_databases == SIMILAR_DATABASES

    def test_empty_list_raises(self) -> None:
        """An empty databases list raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError):
            SimilarRunner(paper=_make_paper(), databases=[])

    def test_unknown_database_raises(self) -> None:
        """An unknown database name raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError):
            SimilarRunner(paper=_make_paper(), databases=["not-a-real-database"])

    def test_subset_preserves_priority_order(self) -> None:
        """A subset is reordered to match SIMILAR_DATABASES priority."""
        runner = SimilarRunner(paper=_make_paper(), databases=["openalex", "semantic_scholar"])
        assert runner._active_databases == ["semantic_scholar", "openalex"]


# ---------------------------------------------------------------------------
# DOI short-circuit
# ---------------------------------------------------------------------------


class TestSimilarRunnerNoDoi:
    """Tests for the seed-paper-without-DOI short circuit."""

    def test_no_doi_skips_all_sources_without_http_calls(self) -> None:
        """A seed paper with no DOI yields an empty result; every source is skipped."""
        runner = SimilarRunner(paper=_make_paper(doi=None))

        with (
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_related"
            ) as mock_ss,
            patch("findpapers.connectors.openalex.OpenAlexConnector.fetch_related") as mock_oa,
            patch("findpapers.connectors.pubmed.PubmedConnector.fetch_related") as mock_pm,
        ):
            result = runner.run(show_progress=False)

        assert result.papers == []
        assert set(result.skipped_databases) == set(SIMILAR_DATABASES)
        assert result.failed_databases == []
        mock_ss.assert_not_called()
        mock_oa.assert_not_called()
        mock_pm.assert_not_called()


# ---------------------------------------------------------------------------
# Merge / dedup / provenance / ordering
# ---------------------------------------------------------------------------


class TestSimilarRunnerMerge:
    """Tests for cross-source merge, dedup, provenance, and priority order."""

    def test_merges_duplicate_across_sources_with_combined_provenance(self) -> None:
        """A paper found by two sources is merged into one, provenance from both."""
        seed = _make_paper(doi="10.1000/seed")
        shared = _make_paper("Shared Paper", doi="10.1000/shared")
        ss_only = _make_paper("SS Only", doi="10.1000/ss-only")

        runner = SimilarRunner(paper=seed, databases=["semantic_scholar", "openalex"])

        with (
            patch.object(
                runner._semantic_scholar,
                "fetch_related",
                return_value=[ss_only, shared],
            ),
            patch.object(
                runner._openalex,
                "fetch_related",
                return_value=[_make_paper("Shared Paper", doi="10.1000/shared")],
            ),
        ):
            result = runner.run(show_progress=False)

        by_doi = {p.doi: p for p in result.papers}
        assert set(by_doi) == {"10.1000/ss-only", "10.1000/shared"}
        assert by_doi["10.1000/shared"].found_in == {"semantic_scholar", "openalex"}
        assert by_doi["10.1000/ss-only"].found_in == {"semantic_scholar"}

    def test_priority_order_ss_first_then_pubmed_only_then_openalex_only(self) -> None:
        """Results follow source priority: SS, then PubMed-only, then OpenAlex-only."""
        seed = _make_paper(doi="10.1000/seed")
        ss_paper = _make_paper("From SS", doi="10.1000/ss")
        pm_paper = _make_paper("From PubMed", doi="10.1000/pm")
        oa_paper = _make_paper("From OpenAlex", doi="10.1000/oa")

        runner = SimilarRunner(paper=seed)

        with (
            patch.object(runner._semantic_scholar, "fetch_related", return_value=[ss_paper]),
            patch.object(runner._pubmed, "_resolve_pmid", return_value="12345"),
            patch.object(runner._pubmed, "fetch_related", return_value=[pm_paper]),
            patch.object(runner._openalex, "fetch_related", return_value=[oa_paper]),
        ):
            result = runner.run(show_progress=False)

        assert [p.doi for p in result.papers] == [
            "10.1000/ss",
            "10.1000/pm",
            "10.1000/oa",
        ]

    def test_excludes_seed_paper_when_echoed_back(self) -> None:
        """A source echoing the seed paper back does not add it to the result."""
        seed = _make_paper("Seed", doi="10.1000/seed")
        runner = SimilarRunner(paper=seed, databases=["semantic_scholar"])

        with patch.object(
            runner._semantic_scholar,
            "fetch_related",
            return_value=[_make_paper("Seed", doi="10.1000/seed")],
        ):
            result = runner.run(show_progress=False)

        assert result.papers == []


# ---------------------------------------------------------------------------
# PubMed skip vs failed
# ---------------------------------------------------------------------------


class TestSimilarRunnerPubmedSkipVsFailed:
    """Tests distinguishing PubMed inapplicability (skip) from errors (failed)."""

    def test_pubmed_skipped_when_pmid_not_resolvable(self) -> None:
        """No resolvable PMID marks PubMed as skipped, not failed."""
        seed = _make_paper(doi="10.1000/seed")
        runner = SimilarRunner(paper=seed, databases=["pubmed"])

        with (
            patch.object(runner._pubmed, "_resolve_pmid", return_value=None),
            patch.object(runner._pubmed, "fetch_related") as mock_fetch,
        ):
            result = runner.run(show_progress=False)

        assert result.skipped_databases == ["pubmed"]
        assert result.failed_databases == []
        mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Per-source error isolation
# ---------------------------------------------------------------------------


class TestSimilarRunnerErrorIsolation:
    """Tests that one source's failure does not abort the others."""

    def test_source_exception_is_isolated(self) -> None:
        """A source raising an exception is recorded as failed; others still run."""
        seed = _make_paper(doi="10.1000/seed")
        oa_paper = _make_paper("From OpenAlex", doi="10.1000/oa")
        runner = SimilarRunner(paper=seed, databases=["semantic_scholar", "openalex"])

        with (
            patch.object(
                runner._semantic_scholar, "fetch_related", side_effect=RuntimeError("boom")
            ),
            patch.object(runner._openalex, "fetch_related", return_value=[oa_paper]),
        ):
            result = runner.run(show_progress=False)

        assert result.failed_databases == ["semantic_scholar"]
        assert [p.doi for p in result.papers] == ["10.1000/oa"]


# ---------------------------------------------------------------------------
# max_papers_per_database forwarding
# ---------------------------------------------------------------------------


class TestSimilarRunnerMaxPapersForwarding:
    """Tests that max_papers_per_database is forwarded to each source."""

    def test_forwarded_to_each_active_connector(self) -> None:
        """Each connector's fetch_related receives the configured cap."""
        seed = _make_paper(doi="10.1000/seed")
        runner = SimilarRunner(
            paper=seed, databases=["semantic_scholar", "openalex"], max_papers_per_database=7
        )

        with (
            patch.object(runner._semantic_scholar, "fetch_related", return_value=[]) as mock_ss,
            patch.object(runner._openalex, "fetch_related", return_value=[]) as mock_oa,
        ):
            runner.run(show_progress=False)

        mock_ss.assert_called_once_with(seed, 7)
        mock_oa.assert_called_once_with(seed, 7)
