"""Unit tests for IEEEConnector."""

from __future__ import annotations

import datetime
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from findpapers.connectors.ieee import _PAGE_SIZE, IEEEConnector
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.exceptions import MissingApiKeyError, UnsupportedQueryError
from findpapers.query.builders.ieee import IEEEQueryBuilder
from findpapers.query.parser import QueryParser
from findpapers.query.propagator import FilterPropagator


class TestIEEEConnectorInit:
    """Tests for IEEEConnector initialisation."""

    def test_default_builder_created(self):
        """Connector creates IEEEQueryBuilder when none provided."""
        searcher = IEEEConnector(api_key="dummy")
        assert isinstance(searcher.query_builder, IEEEQueryBuilder)

    def test_api_key_stored(self):
        """API key is stored on the instance."""
        searcher = IEEEConnector(api_key="test_key")
        assert searcher._api_key == "test_key"

    def test_name(self):
        """Connector name is 'IEEE'."""
        assert IEEEConnector(api_key="dummy").name == Database.IEEE

    def test_missing_api_key_raises(self):
        """Constructing without an API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError, match="api_key"):
            IEEEConnector()

    def test_missing_empty_api_key_raises(self):
        """Constructing with a blank API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError, match="api_key"):
            IEEEConnector(api_key="")
        with pytest.raises(MissingApiKeyError, match="api_key"):
            IEEEConnector(api_key="   ")


class TestIEEEConnectorParsePaper:
    """Tests for _parse_paper."""

    def test_parse_sample_json(self, ieee_sample_json):
        """Parsing sample JSON returns non-empty list of papers."""
        articles = ieee_sample_json.get("articles", [])
        assert len(articles) > 0

        papers = [IEEEConnector(api_key="dummy")._parse_paper(item) for item in articles]
        valid = [p for p in papers if p is not None]
        assert len(valid) > 0

    def test_paper_has_database_tag(self, ieee_sample_json):
        """Parsed paper has 'IEEE' in databases set."""
        item = ieee_sample_json["articles"][0]
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert Database.IEEE in paper.found_in

    def test_missing_title_returns_none(self):
        """Item with empty title returns None."""
        paper = IEEEConnector(api_key="dummy")._parse_paper(
            {"title": "  ", "abstract": "some text"}
        )
        assert paper is None

    def test_parse_with_all_keyword_groups(self):
        """ieee_terms go to subjects; author_terms and mesh_terms go to keywords."""
        item = {
            "title": "A Paper",
            "index_terms": {
                "ieee_terms": {"terms": ["term1"]},
                "author_terms": {"terms": ["term2"]},
                "mesh_terms": {"terms": ["term3"]},
            },
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.subjects == {"term1"}
        assert paper.keywords == {"term2", "term3"}

    def test_index_terms_explicit_none_does_not_crash(self):
        """When index_terms is explicitly None (not just absent), parsing should not crash."""
        item = {"title": "A Paper", "index_terms": None}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        # No keywords should be extracted, but no AttributeError either.
        assert not paper.keywords
        assert not paper.subjects

    def test_subjects_from_ieee_terms_only(self):
        """Only ieee_terms populate subjects; author_terms stay in keywords."""
        item = {
            "title": "A Paper",
            "index_terms": {
                "ieee_terms": {"terms": ["Signal processing", "Frequency estimation"]},
                "author_terms": {"terms": ["my keyword"]},
            },
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.subjects == {"Signal processing", "Frequency estimation"}
        assert paper.keywords == {"my keyword"}

    def test_no_index_terms_gives_empty_subjects(self):
        """When no index_terms are present, subjects is empty."""
        item = {"title": "A Paper"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.subjects == set()

    def test_pages_start_end(self):
        """start_page and end_page are combined into page_range field."""
        item = {"title": "A Paper", "start_page": "10", "end_page": "20"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.page_range == "10-20"

    def test_pages_start_only(self):
        """Only start_page populates page_range field."""
        item = {"title": "A Paper", "start_page": "5"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.page_range == "5"

    def test_citation_count_parsed(self):
        """citing_paper_count is parsed as an integer."""
        item = {"title": "A Paper", "citing_paper_count": "42"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.citations == 42

    def test_invalid_citation_count_ignored(self):
        """Non-numeric citing_paper_count is gracefully ignored."""
        item = {"title": "A Paper", "citing_paper_count": "N/A"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.citations is None

    def test_source_fields_extracted(self):
        """Source title, issn, isbn, and publisher are extracted."""
        item = {
            "title": "A Paper",
            "publication_title": "IEEE Trans.",
            "issn": "1234-5678",
            "isbn": "978-0-xxx",
            "publisher": "IEEE",
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "IEEE Trans."

    def test_keywords_from_sample_data(self, ieee_sample_json):
        """Author terms go to keywords; IEEE terms go to subjects."""
        articles = ieee_sample_json["articles"]
        # articles[2] is the first entry with index_terms (ieee_terms + author_terms)
        paper = IEEEConnector(api_key="dummy")._parse_paper(articles[2])
        assert paper is not None
        # ieee_terms -> subjects
        assert "Natural language processing" in paper.subjects
        # author_terms -> keywords
        assert paper.keywords is not None
        assert len(paper.keywords) > 0

    def test_source_type_journal(self):
        """content_type 'Journals' maps to SourceType.JOURNAL."""
        item = {"title": "A Paper", "publication_title": "IEEE Trans.", "content_type": "Journals"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_source_type_conference(self):
        """content_type 'Conferences' maps to SourceType.CONFERENCE."""
        item = {
            "title": "A Paper",
            "publication_title": "Proc. ICML",
            "content_type": "Conferences",
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_source_type_book(self):
        """content_type 'Books' maps to SourceType.BOOK."""
        item = {"title": "A Paper", "publication_title": "A Book Title", "content_type": "Books"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_source_type_magazine(self):
        """content_type 'Magazines' maps to SourceType.JOURNAL."""
        item = {
            "title": "A Paper",
            "publication_title": "IEEE Spectrum",
            "content_type": "Magazines",
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_source_type_none_when_unknown(self):
        """Unknown content_type results in source_type being None."""
        item = {
            "title": "A Paper",
            "publication_title": "Something",
            "content_type": "UnknownType",
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type is None

    def test_source_type_standards_maps_to_other(self):
        """content_type 'Standards' maps to SourceType.OTHER."""
        item = {
            "title": "A Paper",
            "publication_title": "IEEE Standard",
            "content_type": "Standards",
        }
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.OTHER

    def test_paper_type_article_from_journals(self):
        """content_type 'Journals' maps to PaperType.ARTICLE."""
        item = {"title": "P", "content_type": "Journals"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_inproceedings_from_conferences(self):
        """content_type 'Conferences' maps to PaperType.INPROCEEDINGS."""
        item = {"title": "P", "content_type": "Conferences"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_inbook_from_books(self):
        """content_type 'Books' maps to PaperType.INBOOK."""
        item = {"title": "P", "content_type": "Books"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.INBOOK

    def test_paper_type_techreport_from_standards(self):
        """content_type 'Standards' maps to PaperType.TECHREPORT."""
        item = {"title": "P", "content_type": "Standards"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.TECHREPORT

    def test_paper_type_none_when_unknown(self):
        """Unknown content_type results in paper_type being None."""
        item = {"title": "P", "content_type": "UnknownType"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is None


class TestIEEEConnectorSearch:
    """Tests for search() with mocked HTTP calls."""

    def test_search_raises_on_invalid_query(self, wildcard_query):
        """Search raises UnsupportedQueryError for '?' wildcard (not supported by IEEE)."""
        parser = QueryParser()
        propagator = FilterPropagator()
        q = propagator.propagate(parser.parse("[mach?]"))
        searcher = IEEEConnector(api_key="dummy")
        with pytest.raises(UnsupportedQueryError):
            searcher.search(q)

    def test_search_returns_papers(self, simple_query, ieee_sample_json, mock_response):
        """search() returns papers from IEEE JSON response."""
        searcher = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query)

        assert len(papers) > 0
        assert all(Database.IEEE in p.found_in for p in papers)

    def test_max_papers_respected(self, simple_query, ieee_sample_json, mock_response):
        """search() returns no more than max_papers papers."""
        searcher = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query, max_papers=2)

        assert len(papers) <= 2

    def test_http_error_breaks_loop(self, simple_query, mock_response):
        """HTTP error in _get breaks the pagination loop and returns partial results."""
        searcher = IEEEConnector(api_key="dummy")

        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("network error")),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_http_error_logs_progress_context(self, simple_query, caplog):
        """A failed request logs how many papers were retrieved so far."""
        searcher = IEEEConnector(api_key="dummy")

        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("network error")),
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.ieee"),
        ):
            searcher.search(simple_query)

        assert any("search stopped early" in m for m in caplog.messages)

    def test_empty_articles_before_total_logs_warning(self, simple_query, mock_response, caplog):
        """Articles running out before the reported total logs a pagination-limit warning."""
        full_page_articles = [{"title": f"Paper {i}"} for i in range(_PAGE_SIZE)]
        full_page = mock_response(
            json_data={"total_records": _PAGE_SIZE + 5, "articles": full_page_articles}
        )
        full_page.raise_for_status = MagicMock()
        empty_page = mock_response(json_data={"total_records": _PAGE_SIZE + 5, "articles": []})
        empty_page.raise_for_status = MagicMock()

        searcher = IEEEConnector(api_key="dummy")
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [full_page, empty_page]

        with (
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.ieee"),
        ):
            searcher.search(simple_query)

        assert any("pagination limit" in m for m in caplog.messages)

    def test_progress_callback_called(self, simple_query, ieee_sample_json, mock_response):
        """Progress callback is called during search."""
        searcher = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        response.raise_for_status = MagicMock()
        callback = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, progress_callback=callback)

        callback.assert_called()

    def test_search_network_error_returns_empty_list(self, simple_query):
        """Network error in _fetch_papers is caught and returns an empty list."""
        searcher = IEEEConnector(api_key="dummy")

        with patch.object(
            searcher, "_fetch_papers", side_effect=requests.ConnectionError("network down")
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_since_until_adds_year_params(self, simple_query, ieee_sample_json, mock_response):
        """search() adds start_year/end_year when since/until are given."""
        searcher = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        since = datetime.date(2020, 3, 1)
        until = datetime.date(2023, 6, 30)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        call_args = searcher._http_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("start_year") == "2020"
        assert params.get("end_year") == "2023"

    def test_since_only_adds_start_year(self, simple_query, ieee_sample_json, mock_response):
        """search() adds only start_year when only `since` is given."""
        searcher = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        since = datetime.date(2021, 1, 1)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since)

        call_args = searcher._http_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("start_year") == "2021"
        assert "end_year" not in params


class TestIEEEConnectorIsOpenAccess:
    """Tests for is_open_access extraction from IEEE results."""

    def test_open_access_type_sets_true(self):
        """access_type='OPEN_ACCESS' yields is_open_access=True."""
        item = {"title": "P", "access_type": "OPEN_ACCESS"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is True

    def test_locked_access_type_sets_false(self):
        """access_type='LOCKED' yields is_open_access=False."""
        item = {"title": "P", "access_type": "LOCKED"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is False

    def test_ephemera_access_type_sets_none(self):
        """access_type='EPHEMERA' yields is_open_access=None (unknown)."""
        item = {"title": "P", "access_type": "EPHEMERA"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is None

    def test_missing_access_type_sets_none(self):
        """Missing access_type yields is_open_access=None."""
        item = {"title": "P"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is None

    def test_case_insensitive_access_type(self):
        """access_type matching is case-insensitive."""
        item = {"title": "P", "access_type": "open_access"}
        paper = IEEEConnector(api_key="dummy")._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is True


class TestIEEEConnectorFetchPaperById:
    """Tests for fetch_paper_by_id."""

    def test_fetch_paper_by_id_returns_paper(self, ieee_sample_json, mock_response):
        """fetch_paper_by_id returns a Paper when the API responds with a valid article."""
        connector = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = response

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_id("9413133")

        assert paper is not None

    def test_fetch_paper_by_id_returns_none_when_articles_empty(self, mock_response):
        """fetch_paper_by_id returns None when the API returns no articles."""
        connector = IEEEConnector(api_key="dummy")
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = mock_response(json_data={"articles": []})

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("0000000")

        assert result is None

    def test_fetch_paper_by_id_returns_none_on_request_error(self):
        """fetch_paper_by_id returns None when the HTTP request fails."""
        connector = IEEEConnector(api_key="dummy")
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = requests.RequestException("timeout")

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("9413133")

        assert result is None


class TestIEEEConnectorURLPattern:
    """Tests for url_pattern and fetch_paper_by_url."""

    @pytest.mark.parametrize(
        ("url", "expected_id"),
        [
            ("https://ieeexplore.ieee.org/document/9413133", "9413133"),
            ("https://ieeexplore.ieee.org/abstract/document/9413133", "9413133"),
            ("https://ieeexplore.ieee.org/document/9413133/", "9413133"),
        ],
    )
    def test_url_pattern_matches_ieee_urls(self, url: str, expected_id: str) -> None:
        """url_pattern matches IEEE Xplore landing-page URLs."""
        connector = IEEEConnector(api_key="dummy")
        match = connector.url_pattern.search(url)
        assert match is not None
        assert match.group(1) == expected_id

    def test_url_pattern_does_not_match_non_ieee_url(self) -> None:
        """url_pattern returns None for non-IEEE URLs."""
        connector = IEEEConnector(api_key="dummy")
        assert connector.url_pattern.search("https://arxiv.org/abs/1706.03762") is None

    def test_fetch_paper_by_url_delegates_to_fetch_paper_by_id(
        self, ieee_sample_json, mock_response
    ) -> None:
        """fetch_paper_by_url extracts the article number and delegates to fetch_paper_by_id."""
        connector = IEEEConnector(api_key="dummy")
        response = mock_response(json_data=ieee_sample_json)
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = response

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_url("https://ieeexplore.ieee.org/document/9413133")

        assert paper is not None

    def test_fetch_paper_by_url_returns_none_for_unrecognised_url(self) -> None:
        """fetch_paper_by_url returns None when the URL is not an IEEE Xplore URL."""
        connector = IEEEConnector(api_key="dummy")
        result = connector.fetch_paper_by_url("https://arxiv.org/abs/1706.03762")
        assert result is None
