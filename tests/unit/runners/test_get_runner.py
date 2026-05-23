"""Unit tests for GetRunner."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from findpapers.core.author import Author
from findpapers.core.paper import Paper
from findpapers.core.source import Source
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.get_runner import GetRunner


@pytest.fixture(autouse=True)
def _no_web_scraping():
    """Patch WebScrapingConnector so unit tests do not make real HTTP requests."""
    with patch(
        "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
        return_value=None,
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_paper(
    title: str = "Fake Paper Title",
    doi: str | None = "10.1234/test",
    url: str | None = None,
    keywords: set[str] | None = None,
    found_in: set[str] | None = None,
) -> Paper:
    """Return a minimal Paper for use in tests."""
    return Paper(
        title=title,
        abstract="An abstract.",
        authors=[Author(name="Alice Smith")],
        source=Source(title="Fake Journal"),
        publication_date=datetime.date(2023, 6, 15),
        doi=doi,
        url=url,
        keywords=keywords,
        found_in=found_in or {"crossref"},
    )


def _fake_crossref_work() -> dict:
    """Return a minimal CrossRef work record for testing."""
    return {
        "DOI": "10.1234/test",
        "title": ["Fake Paper Title"],
        "abstract": "<jats:p>An abstract.</jats:p>",
        "author": [{"given": "Alice", "family": "Smith", "affiliation": []}],
        "published-print": {"date-parts": [[2023, 6, 15]]},
        "container-title": ["Fake Journal"],
        "type": "journal-article",
        "is-referenced-by-count": 42,
    }


def _noop_fetch_doi(*_args, **_kwargs) -> None:
    """Stub for fetch_paper_by_doi that always returns None."""
    return None


def _make_runner(identifier: str = "10.1234/test") -> GetRunner:
    """Create a GetRunner with all non-CrossRef DOI connectors stubbed out."""
    runner = GetRunner(identifier=identifier)
    for attr in ("_openalex", "_semantic_scholar", "_pubmed", "_arxiv"):
        conn = getattr(runner, attr)
        if conn is not None:
            conn.fetch_paper_by_doi = _noop_fetch_doi
            conn.close = lambda: None
    return runner


# ---------------------------------------------------------------------------
# Source-skipping heuristics
# ---------------------------------------------------------------------------


class TestShouldSkipConnector:
    """Tests for GetRunner._should_skip_connector."""

    # --- arXiv DOI prefix (10.48550/) ---

    def test_arxiv_doi_skips_ieee(self):
        """arXiv DOI prefix causes IEEE to be skipped."""
        assert (
            GetRunner._should_skip_connector(
                "ieee", "10.48550/arxiv.1706.03762", "10.48550/arxiv.1706.03762"
            )
            is True
        )

    def test_arxiv_doi_does_not_skip_scopus(self):
        """arXiv DOI prefix does not skip Scopus (Scopus indexes arXiv preprints)."""
        assert (
            GetRunner._should_skip_connector(
                "scopus", "10.48550/arxiv.1706.03762", "10.48550/arxiv.1706.03762"
            )
            is False
        )

    def test_arxiv_doi_does_not_skip_arxiv(self):
        """arXiv DOI prefix does not skip arXiv itself."""
        assert (
            GetRunner._should_skip_connector(
                "arxiv", "10.48550/arxiv.1706.03762", "10.48550/arxiv.1706.03762"
            )
            is False
        )

    def test_arxiv_doi_does_not_skip_crossref(self):
        """arXiv DOI prefix does not skip CrossRef."""
        assert (
            GetRunner._should_skip_connector(
                "crossref", "10.48550/arxiv.1706.03762", "10.48550/arxiv.1706.03762"
            )
            is False
        )

    def test_arxiv_doi_case_insensitive(self):
        """DOI comparison is case-insensitive."""
        assert (
            GetRunner._should_skip_connector(
                "ieee", "10.48550/arXiv.1706.03762", "10.48550/arXiv.1706.03762"
            )
            is True
        )

    # --- bioRxiv / medRxiv DOI prefix (10.1101/) ---

    def test_biorxiv_doi_skips_ieee(self):
        """bioRxiv/medRxiv DOI prefix causes IEEE to be skipped."""
        assert (
            GetRunner._should_skip_connector(
                "ieee", "10.1101/2021.01.01.123456", "10.1101/2021.01.01.123456"
            )
            is True
        )

    def test_biorxiv_doi_does_not_skip_pubmed(self):
        """bioRxiv/medRxiv DOI prefix does not skip PubMed."""
        assert (
            GetRunner._should_skip_connector(
                "pubmed", "10.1101/2021.01.01.123456", "10.1101/2021.01.01.123456"
            )
            is False
        )

    # --- arXiv URL in identifier ---

    def test_arxiv_url_skips_ieee(self):
        """arXiv landing-page URL causes IEEE to be skipped."""
        assert (
            GetRunner._should_skip_connector("ieee", None, "https://arxiv.org/abs/1706.03762")
            is True
        )

    def test_arxiv_url_does_not_skip_scopus(self):
        """arXiv landing-page URL does not skip Scopus (Scopus indexes arXiv preprints)."""
        assert (
            GetRunner._should_skip_connector("scopus", None, "https://arxiv.org/abs/1706.03762")
            is False
        )

    def test_arxiv_url_does_not_skip_semantic_scholar(self):
        """arXiv URL does not skip Semantic Scholar."""
        assert (
            GetRunner._should_skip_connector(
                "semantic_scholar", None, "https://arxiv.org/abs/1706.03762"
            )
            is False
        )

    # --- bioRxiv / medRxiv URL in identifier ---

    def test_biorxiv_url_skips_ieee(self):
        """bioRxiv URL causes IEEE to be skipped."""
        assert (
            GetRunner._should_skip_connector(
                "ieee", None, "https://www.biorxiv.org/content/10.1101/123"
            )
            is True
        )

    def test_medrxiv_url_skips_ieee(self):
        """medRxiv URL causes IEEE to be skipped."""
        assert (
            GetRunner._should_skip_connector(
                "ieee", None, "https://www.medrxiv.org/content/10.1101/456"
            )
            is True
        )

    def test_biorxiv_url_does_not_skip_pubmed(self):
        """bioRxiv URL does not skip PubMed."""
        assert (
            GetRunner._should_skip_connector(
                "pubmed", None, "https://www.biorxiv.org/content/10.1101/123"
            )
            is False
        )

    # --- generic / other DOIs and URLs ---

    def test_regular_doi_does_not_skip_ieee(self):
        """A generic publisher DOI does not skip IEEE."""
        assert (
            GetRunner._should_skip_connector(
                "ieee", "10.1109/tpami.2021.123456", "10.1109/tpami.2021.123456"
            )
            is False
        )

    def test_no_doi_and_generic_url_does_not_skip(self):
        """No signal means no connector is skipped."""
        assert (
            GetRunner._should_skip_connector("ieee", None, "https://dl.acm.org/doi/10.1145/123")
            is False
        )

    def test_doi_none_arxiv_url_still_skips(self):
        """When doi=None, URL signal alone is sufficient to trigger skip."""
        assert (
            GetRunner._should_skip_connector("ieee", None, "https://arxiv.org/abs/2301.00001")
            is True
        )


# Identifier classification
# ---------------------------------------------------------------------------


class TestIsLandingPageUrl:
    """Tests for GetRunner._is_landing_page_url."""

    def test_http_url_is_landing_page(self):
        """Plain http:// URLs are landing pages."""
        assert GetRunner._is_landing_page_url("http://example.com/paper") is True

    def test_https_url_is_landing_page(self):
        """Plain https:// URLs are landing pages."""
        assert GetRunner._is_landing_page_url("https://arxiv.org/abs/1706.03762") is True

    def test_doi_org_url_is_not_landing_page(self):
        """https://doi.org/... is NOT a landing page — it is a DOI redirect."""
        assert GetRunner._is_landing_page_url("https://doi.org/10.1234/test") is False

    def test_dx_doi_org_url_is_not_landing_page(self):
        """https://dx.doi.org/... is NOT a landing page."""
        assert GetRunner._is_landing_page_url("https://dx.doi.org/10.1234/test") is False

    def test_bare_doi_is_not_landing_page(self):
        """Bare DOI strings are not URLs and therefore not landing pages."""
        assert GetRunner._is_landing_page_url("10.1234/test") is False


# ---------------------------------------------------------------------------
# DOI sanitization
# ---------------------------------------------------------------------------


class TestSanitizeDoi:
    """Tests for GetRunner._sanitize_doi."""

    def test_bare_doi_unchanged(self):
        """A bare DOI passes through unchanged."""
        assert GetRunner._sanitize_doi("10.1234/test") == "10.1234/test"

    def test_https_prefix_stripped(self):
        """https://doi.org/ prefix is stripped."""
        assert GetRunner._sanitize_doi("https://doi.org/10.1234/test") == "10.1234/test"

    def test_http_prefix_stripped(self):
        """http://doi.org/ prefix is stripped."""
        assert GetRunner._sanitize_doi("http://doi.org/10.1234/test") == "10.1234/test"

    def test_dx_prefix_stripped(self):
        """https://dx.doi.org/ prefix is stripped."""
        assert GetRunner._sanitize_doi("https://dx.doi.org/10.1234/test") == "10.1234/test"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is removed."""
        assert GetRunner._sanitize_doi("  10.1234/test  ") == "10.1234/test"

    def test_empty_raises(self):
        """Empty string raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="must not be empty"):
            GetRunner._sanitize_doi("")

    def test_blank_raises(self):
        """Whitespace-only string raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="must not be empty"):
            GetRunner._sanitize_doi("   ")

    def test_prefix_only_raises(self):
        """A bare doi.org URL with no DOI raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="must not be empty"):
            GetRunner._sanitize_doi("https://doi.org/")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestGetRunnerInit:
    """Tests for GetRunner initialisation."""

    def test_default_timeout(self):
        """Default timeout is 10.0 seconds."""
        runner = GetRunner(identifier="10.1234/test")
        assert runner._timeout == 10.0

    def test_custom_timeout(self):
        """Custom timeout is stored."""
        runner = GetRunner(identifier="10.1234/test", timeout=30.0)
        assert runner._timeout == 30.0

    def test_timeout_propagated_to_crossref(self):
        """Custom timeout is forwarded to the CrossRef connector."""
        runner = GetRunner(identifier="10.1234/test", timeout=42.0)
        assert runner._crossref is not None
        assert runner._crossref._timeout == 42.0

    def test_timeout_propagated_to_all_doi_connectors(self):
        """Custom timeout is forwarded to every DOI connector."""
        runner = GetRunner(identifier="10.1234/test", timeout=25.0)
        for connector in runner._doi_connectors:
            assert connector._timeout == 25.0

    def test_timeout_propagated_to_scraper(self):
        """Custom timeout is also forwarded to the WebScrapingConnector."""
        runner = GetRunner(identifier="10.1234/test", timeout=15.0)
        assert runner._scraper is not None
        assert runner._scraper._timeout == 15.0

    def test_ieee_connector_absent_without_key(self):
        """IEEE connector is None when no API key is provided."""
        runner = GetRunner(identifier="10.1234/test")
        assert runner._ieee is None

    def test_scopus_connector_absent_without_key(self):
        """Scopus connector is None when no API key is provided."""
        runner = GetRunner(identifier="10.1234/test")
        assert runner._scopus is None

    def test_databases_none_creates_all_connectors(self):
        """When databases=None, all non-key-gated connectors are created."""
        runner = GetRunner(identifier="10.1234/test")
        assert runner._arxiv is not None
        assert runner._pubmed is not None
        assert runner._openalex is not None
        assert runner._semantic_scholar is not None

    def test_databases_subset_skips_excluded_connectors(self):
        """Only selected databases have their connectors initialised."""
        runner = GetRunner(identifier="10.1234/test", databases=["arxiv", "pubmed"])
        assert runner._arxiv is not None
        assert runner._pubmed is not None
        assert runner._openalex is None
        assert runner._semantic_scholar is None

    def test_databases_single_entry(self):
        """A single-database list creates only that connector."""
        runner = GetRunner(identifier="10.1234/test", databases=["openalex"])
        assert runner._openalex is not None
        assert runner._arxiv is None
        assert runner._pubmed is None
        assert runner._semantic_scholar is None

    def test_databases_empty_list_raises(self):
        """An empty databases list raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="must not be an empty list"):
            GetRunner(identifier="10.1234/test", databases=[])

    def test_databases_unknown_value_raises(self):
        """An unrecognised database name raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="Unknown database"):
            GetRunner(identifier="10.1234/test", databases=["unknown_db"])

    def test_databases_case_insensitive(self):
        """Database names are case-insensitive."""
        runner = GetRunner(identifier="10.1234/test", databases=["ArXiv", "PUBMED"])
        assert runner._arxiv is not None
        assert runner._pubmed is not None
        assert runner._openalex is None

    def test_databases_ieee_with_key_and_filter(self):
        """IEEE connector is created when both key and filter include it."""
        runner = GetRunner(
            identifier="10.1234/test",
            databases=["ieee"],
            ieee_api_key="fake-key",
        )
        assert runner._ieee is not None

    def test_databases_ieee_excluded_by_filter_despite_key(self):
        """IEEE connector is None when excluded by databases filter, even with API key."""
        runner = GetRunner(
            identifier="10.1234/test",
            databases=["arxiv"],
            ieee_api_key="fake-key",
        )
        assert runner._ieee is None

    def test_crossref_always_present_regardless_of_filter(self):
        """CrossRef connector is created when databases=None (all sources)."""
        runner = GetRunner(identifier="10.1234/test")
        assert runner._crossref is not None

    def test_crossref_absent_when_excluded(self):
        """CrossRef connector is None when 'crossref' is not in databases."""
        runner = GetRunner(identifier="10.1234/test", databases=["arxiv", "pubmed"])
        assert runner._crossref is None

    def test_crossref_present_when_explicitly_included(self):
        """CrossRef connector is created when 'crossref' is in databases."""
        runner = GetRunner(identifier="10.1234/test", databases=["crossref"])
        assert runner._crossref is not None

    def test_web_scraping_enabled_by_default(self):
        """Scraper is created when databases=None."""
        runner = GetRunner(identifier="10.1234/test")
        assert runner._scraper is not None

    def test_web_scraping_disabled_when_excluded(self):
        """Scraper is None when 'web_scraping' is not in databases."""
        runner = GetRunner(identifier="10.1234/test", databases=["arxiv"])
        assert runner._scraper is None

    def test_web_scraping_enabled_when_included(self):
        """Scraper is created when 'web_scraping' is explicitly included."""
        runner = GetRunner(identifier="10.1234/test", databases=["web_scraping", "crossref"])
        assert runner._scraper is not None

    def test_databases_accepts_all_get_databases_values(self):
        """Every value in GET_DATABASES is accepted without raising."""
        from findpapers.runners.get_runner import GET_DATABASES

        # IEEE and Scopus need keys; skip them here to avoid MissingApiKeyError.
        values = GET_DATABASES - {"ieee", "scopus"}
        runner = GetRunner(identifier="10.1234/test", databases=list(values))
        assert runner is not None


# ---------------------------------------------------------------------------
# run() — bare DOI path
# ---------------------------------------------------------------------------


class TestGetRunnerDoiPath:
    """Tests for run() when identifier is a bare DOI or doi.org URL."""

    def test_bare_doi_returns_paper(self):
        """run() returns a Paper when CrossRef finds the DOI."""
        fake_paper = _fake_paper()
        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=fake_paper,
            ),
        ):
            runner = _make_runner("10.1234/test")
            result = runner.run()

        assert result is fake_paper

    def test_doi_org_url_stripped_and_found(self):
        """run() strips the doi.org prefix and resolves the paper correctly."""
        fake_paper = _fake_paper()
        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=fake_paper,
            ),
        ):
            runner = _make_runner("https://doi.org/10.1234/test")
            result = runner.run()

        assert result is fake_paper

    def test_bare_doi_returns_none_when_not_found(self):
        """run() returns None when no connector finds the DOI."""
        with patch(
            "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
            return_value=None,
        ):
            runner = _make_runner("10.9999/nonexistent")
            result = runner.run()

        assert result is None

    def test_bare_doi_merges_extra_connector_results(self):
        """DOI connectors beyond CrossRef have their data merged in."""
        base_paper = _fake_paper(keywords=None)
        extra_paper = Paper(
            title="Fake Paper Title",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            doi="10.1234/test",
            keywords={"ML", "AI"},
            found_in={"semantic_scholar"},
        )
        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=base_paper,
            ),
        ):
            runner = _make_runner()
            runner._semantic_scholar.fetch_paper_by_doi = lambda doi: extra_paper  # type: ignore[union-attr, method-assign]
            result = runner.run()

        assert result is base_paper
        assert result.keywords is not None
        assert "ML" in result.keywords

    def test_crossref_url_has_priority_over_other_doi_connectors(self):
        """CrossRef URL is preserved over a longer URL from another DOI connector when
        there is no scraped URL (bare DOI path without a successful web-scraping stage)."""
        base_paper = _fake_paper(url="https://doi.org/10.1234/test")
        extra_paper = Paper(
            title="Fake Paper Title",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            doi="10.1234/test",
            url="https://www.some-publisher.com/articles/very-long-url/10.1234/test",
            found_in={"openalex"},
        )
        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=base_paper,
            ),
        ):
            runner = _make_runner()
            runner._openalex.fetch_paper_by_doi = lambda doi: extra_paper  # type: ignore[union-attr, method-assign]
            result = runner.run()

        assert result is not None
        assert result.url == "https://doi.org/10.1234/test"

    def test_fallback_when_crossref_returns_none(self):
        """When CrossRef finds nothing, another connector can still provide a result."""
        fallback_paper = _fake_paper(found_in={"openalex"})
        with patch(
            "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
            return_value=None,
        ):
            runner = _make_runner()
            runner._openalex.fetch_paper_by_doi = lambda doi: fallback_paper  # type: ignore[union-attr, method-assign]
            result = runner.run()

        assert result is fallback_paper

    def test_verbose_mode_does_not_raise(self):
        """run() with verbose=True completes without raising."""
        with patch(
            "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
            return_value=None,
        ):
            runner = _make_runner()
            result = runner.run(verbose=True)

        assert result is None

    def test_verbose_true_restores_root_logger_level(self):
        """run(verbose=True) restores the root logger level on exit."""
        import logging

        with patch(
            "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
            return_value=None,
        ):
            root_logger = logging.getLogger()
            original_level = root_logger.level
            root_logger.setLevel(logging.WARNING)
            try:
                runner = _make_runner()
                runner.run(verbose=True)
                assert root_logger.level == logging.WARNING
            finally:
                root_logger.setLevel(original_level)


# ---------------------------------------------------------------------------
# run() — landing-page URL path
# ---------------------------------------------------------------------------


class TestGetRunnerUrlPath:
    """Tests for run() when identifier is a landing-page URL."""

    def test_url_scraping_result_returned_without_doi(self):
        """When scraping finds a paper but no DOI, Stage 2 is skipped."""
        scraped_paper = _fake_paper(doi=None)
        with patch(
            "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
            return_value=scraped_paper,
        ):
            runner = GetRunner(identifier="https://example.com/paper")
            result = runner.run()

        assert result is scraped_paper

    def test_url_scraping_returns_none_when_page_has_no_metadata(self):
        """run() returns None when the page yields no paper."""
        with patch(
            "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
            return_value=None,
        ):
            runner = GetRunner(identifier="https://example.com/no-meta")
            result = runner.run()

        assert result is None

    def test_url_scraping_enriched_by_doi_connectors(self):
        """When scraping finds a DOI, DOI connectors enrich the scraped paper."""
        scraped_paper = _fake_paper(
            doi="10.1234/test", title="Scraped Title", found_in={"web_scraping"}
        )
        crossref_paper = _fake_paper(keywords={"NLP"}, found_in={"crossref"})

        mock_scraper = MagicMock(return_value=scraped_paper)
        with (
            patch(
                "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
                mock_scraper,
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=crossref_paper,
            ),
        ):
            runner = _make_runner("https://example.com/paper")
            result = runner.run()

        # The scraper paper is the base; CrossRef data is merged in.
        assert result is scraped_paper
        assert result.keywords is not None
        assert "NLP" in result.keywords

    def test_url_lookup_connector_delegates_without_html_scraping(self):
        """When a URL-lookup connector matches, HTML scraping is bypassed."""
        api_paper = _fake_paper(doi=None, found_in={"arxiv"})
        with patch(
            "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
            return_value=api_paper,
        ):
            runner = GetRunner(identifier="https://arxiv.org/abs/1706.03762")
            result = runner.run()

        # The paper from the API connector is returned (no DOI → Stage 2 skipped).
        assert result is api_paper

    def test_scraping_failure_falls_through_to_none(self):
        """When scraping raises, the runner returns None instead of propagating."""
        with patch(
            "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
            side_effect=Exception("network error"),
        ):
            runner = GetRunner(identifier="https://example.com/paper")
            result = runner.run()

        assert result is None

    def test_scraping_url_has_priority_over_crossref_url(self):
        """Scraped URL (final URL after HTTP redirects) wins over the CrossRef URL."""
        scraped_paper = _fake_paper(doi="10.1234/test", url="https://example.com/paper")
        crossref_paper = _fake_paper(url="https://doi.org/10.1234/test", found_in={"crossref"})

        with (
            patch(
                "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
                return_value=scraped_paper,
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=crossref_paper,
            ),
        ):
            runner = _make_runner("https://example.com/paper")
            result = runner.run()

        assert result is scraped_paper
        assert result.url == "https://example.com/paper"


# ---------------------------------------------------------------------------
# run() — databases filter behaviour
# ---------------------------------------------------------------------------


class TestGetRunnerDatabasesFilter:
    """Behavioural tests for run() when specific databases are enabled/disabled."""

    def test_crossref_disabled_returns_none_for_bare_doi(self):
        """When crossref is disabled and no other connector finds the DOI, returns None."""
        runner = GetRunner(identifier="10.1234/test", databases=["arxiv", "pubmed"])
        assert runner._crossref is None
        # stub only the connectors that exist
        if runner._arxiv is not None:
            runner._arxiv.fetch_paper_by_doi = lambda doi: None  # type: ignore[method-assign]
        if runner._pubmed is not None:
            runner._pubmed.fetch_paper_by_doi = lambda doi: None  # type: ignore[method-assign]
        result = runner.run()
        assert result is None

    def test_crossref_disabled_but_other_connector_finds_paper(self):
        """Without crossref, another Stage-2 connector can still return a result."""
        fake_paper = _fake_paper(found_in={"arxiv"})
        runner = GetRunner(identifier="10.1234/test", databases=["arxiv"])
        assert runner._crossref is None
        runner._arxiv.fetch_paper_by_doi = lambda doi: fake_paper  # type: ignore[union-attr, method-assign]
        result = runner.run()
        assert result is fake_paper

    def test_web_scraping_disabled_skips_stage1_for_landing_url(self):
        """When web_scraping is disabled, a landing-page URL returns None (no DOI)."""
        runner = GetRunner(
            identifier="https://example.com/paper",
            databases=["crossref", "arxiv"],
        )
        assert runner._scraper is None
        result = runner.run()
        assert result is None

    def test_web_scraping_only_returns_scraped_paper(self):
        """When only web_scraping is enabled, Stage 2 is never reached."""
        scraped_paper = _fake_paper(doi=None, found_in={"web_scraping"})
        with patch(
            "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
            return_value=scraped_paper,
        ):
            runner = GetRunner(
                identifier="https://example.com/paper",
                databases=["web_scraping"],
            )
            result = runner.run()

        assert result is scraped_paper
        # CrossRef must not be instantiated.
        assert runner._crossref is None

    def test_web_scraping_disabled_stage1_not_called_even_for_url(self):
        """WebScraping.fetch_paper_from_url is never called when web_scraping disabled."""
        with patch(
            "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url"
        ) as mock_scrape:
            runner = GetRunner(
                identifier="https://example.com/paper",
                databases=["crossref"],
            )
            runner.run()

        mock_scrape.assert_not_called()

    def test_bare_doi_with_web_scraping_calls_scraper_with_doi_url(self):
        """When identifier is a bare DOI and web_scraping is enabled, the scraper
        is called with the https://doi.org/{doi} redirect URL."""
        scraped_paper = _fake_paper(doi="10.1234/test", found_in={"web_scraping"})
        with (
            patch(
                "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
                return_value=scraped_paper,
            ) as mock_scrape,
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=None,
            ),
        ):
            runner = GetRunner(
                identifier="10.1234/test",
                databases=["web_scraping", "crossref"],
            )
            result = runner.run()

        mock_scrape.assert_called_once()
        call_url = mock_scrape.call_args[0][0]
        assert call_url == "https://doi.org/10.1234/test"
        assert result is scraped_paper

    def test_bare_doi_with_web_scraping_disabled_does_not_call_scraper(self):
        """When web_scraping is disabled, the scraper is never called for bare DOIs."""
        with (
            patch(
                "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url"
            ) as mock_scrape,
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=None,
            ),
        ):
            runner = GetRunner(
                identifier="10.1234/test",
                databases=["crossref"],
            )
            runner.run()

        mock_scrape.assert_not_called()

    def test_doi_org_url_with_web_scraping_calls_scraper(self):
        """When identifier is a doi.org URL and web_scraping is enabled, the
        scraper is called with the normalised https://doi.org/{doi} URL."""
        scraped_paper = _fake_paper(doi="10.1234/test", found_in={"web_scraping"})
        with (
            patch(
                "findpapers.connectors.web_scraping.WebScrapingConnector.fetch_paper_from_url",
                return_value=scraped_paper,
            ) as mock_scrape,
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=None,
            ),
        ):
            runner = GetRunner(
                identifier="https://doi.org/10.1234/test",
                databases=["web_scraping", "crossref"],
            )
            result = runner.run()

        mock_scrape.assert_called_once()
        call_url = mock_scrape.call_args[0][0]
        assert call_url == "https://doi.org/10.1234/test"
        assert result is scraped_paper


# ---------------------------------------------------------------------------
# cited_by population in GetRunner
# ---------------------------------------------------------------------------


class TestGetRunnerCitedBy:
    """Tests that GetRunner._run_cited_by_stage populates cited_by."""

    def test_cited_by_populated_via_openalex(self) -> None:
        """cited_by is filled with DOIs from OpenAlex fetch_cited_by."""
        base = _fake_paper(doi="10.1234/test")
        citing_a = _fake_paper(title="Citer A", doi="10.1000/a")
        citing_b = _fake_paper(title="Citer B", doi="10.1000/b")

        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=base,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_cited_by",
                return_value=[citing_a, citing_b],
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_cited_by",
                return_value=[],
            ),
        ):
            runner = GetRunner(
                identifier="10.1234/test",
                databases=["crossref", "openalex", "semantic_scholar"],
            )
            result = runner.run()

        assert result is not None
        assert "10.1000/a" in result.cited_by
        assert "10.1000/b" in result.cited_by

    def test_cited_by_not_duplicated_across_connectors(self) -> None:
        """DOIs returned by multiple connectors are not duplicated in cited_by."""
        base = _fake_paper(doi="10.1234/test")
        citing = _fake_paper(title="Citer", doi="10.1000/citer")

        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=base,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_cited_by",
                return_value=[citing],
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_cited_by",
                return_value=[citing],
            ),
        ):
            runner = GetRunner(
                identifier="10.1234/test",
                databases=["crossref", "openalex", "semantic_scholar"],
            )
            result = runner.run()

        assert result is not None
        assert result.cited_by.count("10.1000/citer") == 1

    def test_cited_by_skips_papers_without_doi(self) -> None:
        """fetch_cited_by papers without a DOI are not added to cited_by."""
        base = _fake_paper(doi="10.1234/test")
        citing_no_doi = _fake_paper(title="NoDoi", doi=None)

        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=base,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_cited_by",
                return_value=[citing_no_doi],
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_cited_by",
                return_value=[],
            ),
        ):
            runner = GetRunner(
                identifier="10.1234/test",
                databases=["crossref", "openalex", "semantic_scholar"],
            )
            result = runner.run()

        assert result is not None
        assert result.cited_by == []

    def test_cited_by_not_called_when_no_doi_found(self) -> None:
        """When no DOI is resolved, fetch_cited_by is never called."""
        with (
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_cited_by",
            ) as mock_cb,
        ):
            runner = GetRunner(
                identifier="https://example.com/paper",
                databases=["web_scraping", "openalex"],
            )
            result = runner.run()

        mock_cb.assert_not_called()
        assert result is None

    def test_cited_by_connector_error_is_silently_ignored(self) -> None:
        """An exception from fetch_cited_by does not abort the lookup."""
        base = _fake_paper(doi="10.1234/test")

        with (
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.fetch_work",
                return_value=_fake_crossref_work(),
            ),
            patch(
                "findpapers.connectors.crossref.CrossRefConnector.build_paper",
                return_value=base,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.openalex.OpenAlexConnector.fetch_cited_by",
                side_effect=RuntimeError("API error"),
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_paper_by_doi",
                return_value=None,
            ),
            patch(
                "findpapers.connectors.semantic_scholar.SemanticScholarConnector.fetch_cited_by",
                return_value=[],
            ),
        ):
            runner = GetRunner(
                identifier="10.1234/test",
                databases=["crossref", "openalex", "semantic_scholar"],
            )
            result = runner.run()

        assert result is not None
        assert result.cited_by == []
