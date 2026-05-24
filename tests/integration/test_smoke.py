"""Smoke tests that exercise the main findpapers features against live APIs.

These tests are designed to run **post-merge** on CI, hitting real external
services.  They intentionally use small limits (``max_papers_per_database=5``)
and short timeouts to keep execution fast and polite to upstream providers.

The suite validates that the happy-path of each feature works end-to-end and
produces structurally correct results.  Failures here indicate that an
upstream API may have changed its contract or that a recent code change
broke the integration surface.

Environment variables
---------------------
All API keys are optional.  Databases that require a missing key are
automatically skipped by ``Engine``.

* ``FINDPAPERS_IEEE_API_TOKEN``
* ``FINDPAPERS_SCOPUS_API_TOKEN``
* ``FINDPAPERS_PUBMED_API_TOKEN``
* ``FINDPAPERS_OPENALEX_API_TOKEN``
* ``FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN``
* ``FINDPAPERS_EMAIL``
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from findpapers import Engine, load_from_json, save_to_bibtex, save_to_json
from findpapers.core.paper import Paper
from findpapers.core.search_result import SearchResult

# All tests in this module require live network access.
pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A well-known DOI that is unlikely to disappear from CrossRef.
_KNOWN_DOI = "10.1038/nature11804"

# A simple query that should return results on every free database.
_SEARCH_QUERY = "[machine learning]"

# All supported databases.  The Engine skips any that lack a configured API key.
_ALL_DATABASES = ["arxiv", "ieee", "openalex", "pubmed", "scopus", "semantic_scholar"]


def _build_engine() -> Engine:
    """Build an ``Engine`` using environment-variable keys (if any).

    Returns
    -------
    Engine
        Configured engine instance.
    """
    return Engine(
        ieee_api_key=os.environ.get("FINDPAPERS_IEEE_API_TOKEN"),
        scopus_api_key=os.environ.get("FINDPAPERS_SCOPUS_API_TOKEN"),
        pubmed_api_key=os.environ.get("FINDPAPERS_PUBMED_API_TOKEN"),
        openalex_api_key=os.environ.get("FINDPAPERS_OPENALEX_API_TOKEN"),
        email=os.environ.get("FINDPAPERS_EMAIL"),
        semantic_scholar_api_key=os.environ.get("FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearch:
    """Verify that ``Engine.search`` returns papers from live databases."""

    @pytest.mark.parametrize("database", _ALL_DATABASES)
    def test_search_single_database(self, database: str) -> None:
        """Search a single database and assert we get at least one paper.

        Parameters
        ----------
        database : str
            Database identifier to query.
        """
        engine = _build_engine()
        result = engine.search(
            _SEARCH_QUERY,
            databases=[database],
            max_papers_per_database=5,
            show_progress=False,
        )

        assert isinstance(result, SearchResult), "Expected a SearchResult instance"
        assert len(result.papers) > 0, f"No papers returned from {database}"

        # Every paper must have at least a title.
        for paper in result.papers:
            assert isinstance(paper, Paper)
            assert paper.title, "Paper is missing a title"

    def test_search_multiple_databases(self) -> None:
        """Search across all available databases simultaneously."""
        engine = _build_engine()
        result = engine.search(
            _SEARCH_QUERY,
            databases=_ALL_DATABASES,
            max_papers_per_database=3,
            show_progress=False,
        )

        assert isinstance(result, SearchResult)
        assert len(result.papers) > 0, "No papers returned from multi-database search"


class TestDOILookup:
    """Verify that ``Engine.get`` works against CrossRef."""

    def test_fetch_known_doi(self) -> None:
        """Fetch a well-known DOI and check basic fields."""
        engine = _build_engine()
        paper = engine.get(_KNOWN_DOI)

        assert paper is not None, f"DOI lookup returned None for {_KNOWN_DOI}"
        assert isinstance(paper, Paper)
        assert paper.title, "Paper from DOI lookup is missing a title"
        assert paper.doi, "Paper from DOI lookup is missing a DOI"


class TestEnrichment:
    """Verify that ``Engine.search`` enriches papers correctly.

    Enrichment is not a standalone method — it is applied automatically
    during :meth:`~findpapers.engine.Engine.search` and
    :meth:`~findpapers.engine.Engine.snowball` via the
    ``enrichment_databases`` parameter.
    """

    def test_search_with_default_enrichment(self) -> None:
        """Search with default enrichment and verify papers have a DOI.

        The default enrichment databases (CrossRef + web scraping) should
        populate DOIs for arXiv papers that don't carry a DOI natively.
        """
        engine = _build_engine()
        result = engine.search(
            _SEARCH_QUERY,
            databases=["arxiv"],
            max_papers_per_database=3,
            show_progress=False,
        )

        assert len(result.papers) > 0, "Need at least one paper to verify enrichment"

        papers_with_doi = [p for p in result.papers if p.doi]
        assert len(papers_with_doi) > 0, "No papers have a DOI after enrichment"

    def test_search_without_enrichment(self) -> None:
        """Search with enrichment disabled should still return papers."""
        engine = _build_engine()
        result = engine.search(
            _SEARCH_QUERY,
            databases=["arxiv"],
            max_papers_per_database=3,
            show_progress=False,
            enrichment_databases=None,
        )

        assert isinstance(result, SearchResult)
        assert len(result.papers) > 0, "No papers returned when enrichment is disabled"


class TestSnowball:
    """Verify that ``Engine.snowball`` returns a SnowballResult."""

    def test_snowball_from_doi(self) -> None:
        """Snowball from a single seed paper found by DOI."""
        engine = _build_engine()
        seed = engine.get(_KNOWN_DOI)

        assert seed is not None, "Seed paper not found; cannot test snowball"

        result = engine.snowball(seed, max_depth=1, show_progress=False, max_per_level=5)

        assert result is not None, "Snowball returned None"
        # The seed itself should always be in seed_papers.
        assert len(result.seed_papers) >= 1, "Snowball result has no seed papers"


class TestSave:
    """Verify that save/load round-trips work correctly."""

    def test_json_round_trip(self) -> None:
        """Save a SearchResult to JSON and re-import it."""
        engine = _build_engine()
        result = engine.search(
            _SEARCH_QUERY,
            databases=["arxiv"],
            max_papers_per_database=3,
            show_progress=False,
        )

        assert len(result.papers) > 0

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "results.json")

            save_to_json(result, json_path)
            assert os.path.isfile(json_path), "JSON file was not created"

            # Validate the file is valid JSON.
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            assert "papers" in data

            # Round-trip: load back and compare paper count.
            loaded = load_from_json(json_path)
            assert isinstance(loaded, SearchResult)
            assert len(loaded.papers) == len(result.papers)

    def test_bibtex_save(self) -> None:
        """Save papers to BibTeX and verify the file is non-empty."""
        engine = _build_engine()
        result = engine.search(
            _SEARCH_QUERY,
            databases=["arxiv"],
            max_papers_per_database=3,
            show_progress=False,
        )

        assert len(result.papers) > 0

        with tempfile.TemporaryDirectory() as tmpdir:
            bib_path = os.path.join(tmpdir, "results.bib")
            save_to_bibtex(result.papers, bib_path)

            assert os.path.isfile(bib_path), "BibTeX file was not created"
            content = Path(bib_path).read_text(encoding="utf-8")
            assert len(content) > 0, "BibTeX file is empty"
            assert "@" in content, "BibTeX file has no entries"
