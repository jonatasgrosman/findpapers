"""Unit tests for ScopusConnector."""

from __future__ import annotations

import datetime
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from findpapers.connectors.scopus import ScopusConnector
from findpapers.core.author import Author
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.exceptions import MissingApiKeyError
from findpapers.query.builders.scopus import ScopusQueryBuilder


class TestScopusConnectorInit:
    """Tests for ScopusConnector initialisation."""

    def test_default_builder_created(self):
        """Connector creates ScopusQueryBuilder when none provided."""
        searcher = ScopusConnector(api_key="dummy")
        assert isinstance(searcher.query_builder, ScopusQueryBuilder)

    def test_api_key_stored(self):
        """API key is stored on the instance."""
        searcher = ScopusConnector(api_key="test_key")
        assert searcher._api_key == "test_key"

    def test_name(self):
        """Connector name is 'Scopus'."""
        assert ScopusConnector(api_key="dummy").name == Database.SCOPUS

    def test_missing_api_key_raises(self):
        """Constructing without an API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError, match="api_key"):
            ScopusConnector()

    def test_missing_empty_api_key_raises(self):
        """Constructing with a blank API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError, match="api_key"):
            ScopusConnector(api_key="")
        with pytest.raises(MissingApiKeyError, match="api_key"):
            ScopusConnector(api_key="   ")


class TestScopusConnectorParsePaper:
    """Tests for _parse_paper."""

    def test_parse_sample_json(self, scopus_sample_json):
        """Parsing sample JSON returns non-empty list of papers."""
        entries = scopus_sample_json.get("search-results", {}).get("entry", [])
        assert len(entries) > 0

        papers = [ScopusConnector(api_key="dummy")._parse_paper(e) for e in entries]
        valid = [p for p in papers if p is not None]
        assert len(valid) > 0

    def test_paper_has_database_tag(self, scopus_sample_json):
        """Parsed paper has 'Scopus' in databases set."""
        entry = scopus_sample_json["search-results"]["entry"][0]
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert Database.SCOPUS in paper.found_in

    def test_missing_title_returns_none(self):
        """Entry with empty title returns None."""
        paper = ScopusConnector(api_key="dummy")._parse_paper({"dc:title": ""})
        assert paper is None

    def test_authors_as_list(self):
        """Entry with dc:creator as a list produces multiple authors."""
        entry = {
            "dc:title": "A Paper",
            "dc:creator": ["Author One", "Author Two"],
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert len(paper.authors) == 2
        assert Author(name="Author One") in paper.authors

    def test_abstract_from_teaser_fallback(self):
        """Entry without dc:description uses prism:teaser for abstract."""
        entry = {
            "dc:title": "A Paper",
            "prism:teaser": "Teaser text here.",
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.abstract == "Teaser text here."

    def test_isbn_as_list_of_dicts(self):
        """Entry with prism:isbn as list of dicts extracts first value."""
        entry = {
            "dc:title": "A Book Chapter",
            "prism:publicationName": "Some Book",
            "prism:isbn": [{"$": "978-3-16-148410-0"}, {"$": "978-0-00-000000-0"}],
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.isbn == "978-3-16-148410-0"

    def test_pages_extracted(self):
        """Entry with prism:pageRange populates page_range field."""
        entry = {"dc:title": "A Paper", "prism:pageRange": "100-110"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.page_range == "100-110"

    def test_citation_count_parsed(self):
        """citedby-count is parsed as integer."""
        entry = {"dc:title": "A Paper", "citedby-count": "42"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.citations == 42

    def test_single_author_gets_affiliation(self):
        """Single author receives the first affiliation from the entry."""
        entry = {
            "dc:title": "A Paper",
            "dc:creator": "Smith, J.",
            "affiliation": [
                {
                    "@_fa": "true",
                    "affilname": "MIT",
                    "affiliation-city": "Cambridge",
                    "affiliation-country": "United States",
                }
            ],
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Smith, J."
        assert paper.authors[0].affiliation == "MIT"

    def test_multiple_authors_skip_affiliation(self):
        """Multiple authors do not get entry-level affiliation assigned."""
        entry = {
            "dc:title": "A Paper",
            "dc:creator": ["Author One", "Author Two"],
            "affiliation": [
                {
                    "@_fa": "true",
                    "affilname": "Harvard",
                    "affiliation-city": "Boston",
                    "affiliation-country": "United States",
                }
            ],
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert len(paper.authors) == 2
        assert paper.authors[0].affiliation is None
        assert paper.authors[1].affiliation is None

    def test_empty_affiliation_list_ignored(self):
        """Empty affiliation list does not set affiliation on author."""
        entry = {
            "dc:title": "A Paper",
            "dc:creator": "Solo Author",
            "affiliation": [],
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.authors[0].affiliation is None

    def test_affiliation_from_sample_response(self, scopus_sample_json):
        """First entry in sample response has affiliation extracted."""
        entry = scopus_sample_json["search-results"]["entry"][0]
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Sumithra M.G."
        assert paper.authors[0].affiliation == "Dr. N.G.P. Institute of Technology"

    def test_source_type_journal(self):
        """aggregationType 'Journal' maps to SourceType.JOURNAL."""
        entry = {
            "dc:title": "A Paper",
            "prism:publicationName": "Nature",
            "prism:aggregationType": "Journal",
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_source_type_conference(self):
        """aggregationType 'Conference Proceeding' maps to SourceType.CONFERENCE."""
        entry = {
            "dc:title": "A Paper",
            "prism:publicationName": "ICML 2021",
            "prism:aggregationType": "Conference Proceeding",
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_source_type_book(self):
        """aggregationType 'Book' maps to SourceType.BOOK."""
        entry = {
            "dc:title": "A Chapter",
            "prism:publicationName": "Advances in AI",
            "prism:aggregationType": "Book",
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_source_type_none_when_missing(self):
        """Missing aggregationType results in source_type being None."""
        entry = {
            "dc:title": "A Paper",
            "prism:publicationName": "Something",
        }
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type is None

    def test_paper_type_article_from_subtype(self):
        """subtypeDescription 'Article' maps to PaperType.ARTICLE."""
        entry = {"dc:title": "P", "subtypeDescription": "Article"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_inproceedings_from_conference_paper(self):
        """subtypeDescription 'Conference Paper' maps to PaperType.INPROCEEDINGS."""
        entry = {"dc:title": "P", "subtypeDescription": "Conference Paper"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_book_from_subtype(self):
        """subtypeDescription 'Book' maps to PaperType.BOOK."""
        entry = {"dc:title": "P", "subtypeDescription": "Book"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.BOOK

    def test_paper_type_inbook_from_book_chapter(self):
        """subtypeDescription 'Book Chapter' maps to PaperType.INBOOK."""
        entry = {"dc:title": "P", "subtypeDescription": "Book Chapter"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.INBOOK

    def test_paper_type_techreport_from_report(self):
        """subtypeDescription 'Report' maps to PaperType.TECHREPORT."""
        entry = {"dc:title": "P", "subtypeDescription": "Report"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.TECHREPORT

    def test_paper_type_misc_from_data_paper(self):
        """subtypeDescription 'Data Paper' maps to PaperType.MISC."""
        entry = {"dc:title": "P", "subtypeDescription": "Data Paper"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.MISC

    def test_paper_type_article_from_business_article(self):
        """subtypeDescription 'Business Article' maps to PaperType.ARTICLE."""
        entry = {"dc:title": "P", "subtypeDescription": "Business Article"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_none_when_missing(self):
        """Missing subtypeDescription results in paper_type being None."""
        entry = {"dc:title": "P"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is None


class TestScopusConnectorSearch:
    """Tests for search() with mocked HTTP calls."""

    @staticmethod
    def _empty_page_response(mock_response):
        """Create a mocked response containing no entries for pagination stop."""
        response = mock_response(json_data={"search-results": {"entry": []}})
        response.raise_for_status = MagicMock()
        return response

    def test_search_returns_papers(self, simple_query, scopus_sample_json, mock_response):
        """search() returns papers from Scopus JSON response."""
        searcher = ScopusConnector(api_key="dummy")
        response_with_data = mock_response(json_data=scopus_sample_json)
        response_with_data.raise_for_status = MagicMock()
        response_empty_page = self._empty_page_response(mock_response)

        with (
            patch.object(
                searcher,
                "_get",
                side_effect=[response_with_data, response_empty_page],
            ) as mocked_get,
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        assert mocked_get.call_count == 2
        assert len(papers) > 0
        assert all(Database.SCOPUS in p.found_in for p in papers)

    def test_max_papers_respected(self, simple_query, scopus_sample_json, mock_response):
        """search() returns no more than max_papers papers."""
        searcher = ScopusConnector(api_key="dummy")
        response_with_data = mock_response(json_data=scopus_sample_json)
        response_with_data.raise_for_status = MagicMock()

        with (
            patch.object(searcher, "_get", return_value=response_with_data),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query, max_papers=2)

        assert len(papers) <= 2

    def test_http_error_breaks_loop(self, simple_query):
        """Exception in _get breaks the pagination loop and returns empty list."""
        searcher = ScopusConnector(api_key="dummy")

        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("network error")),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_http_error_logs_progress_context(self, simple_query, caplog):
        """A failed request logs how many papers were retrieved so far."""
        searcher = ScopusConnector(api_key="dummy")

        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("network error")),
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.scopus"),
        ):
            searcher.search(simple_query)

        assert any("search stopped early" in m for m in caplog.messages)

    def test_empty_entries_before_total_logs_warning(
        self, simple_query, scopus_sample_json, mock_response, caplog
    ) -> None:
        """Entries running out before the reported total logs a pagination-limit warning."""
        searcher = ScopusConnector(api_key="dummy")
        response_with_data = mock_response(json_data=scopus_sample_json)
        response_with_data.raise_for_status = MagicMock()
        response_empty_page = self._empty_page_response(mock_response)

        with (
            patch.object(
                searcher,
                "_get",
                side_effect=[response_with_data, response_empty_page],
            ),
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.scopus"),
        ):
            searcher.search(simple_query)

        assert any("pagination limit" in m for m in caplog.messages)

    def test_progress_callback_called(self, simple_query, scopus_sample_json, mock_response):
        """Progress callback is invoked after processing each page."""
        searcher = ScopusConnector(api_key="dummy")
        response_with_data = mock_response(json_data=scopus_sample_json)
        response_with_data.raise_for_status = MagicMock()
        response_empty_page = self._empty_page_response(mock_response)
        callback = MagicMock()

        with (
            patch.object(
                searcher,
                "_get",
                side_effect=[response_with_data, response_empty_page],
            ),
            patch.object(searcher, "_rate_limit"),
        ):
            searcher.search(simple_query, progress_callback=callback)

        callback.assert_called()

    def test_pagination_stops_on_short_page(self, simple_query, mock_response):
        """Pagination stops when fewer entries than page_size are returned."""
        single_entry_data = {
            "search-results": {
                "opensearch:totalResults": "1",
                "entry": [
                    {
                        "dc:title": "A Paper",
                        "dc:creator": "Some Author",
                        "prism:coverDate": "2023-01-01",
                    }
                ],
            }
        }
        searcher = ScopusConnector(api_key="dummy")
        response = mock_response(json_data=single_entry_data)
        response.raise_for_status = MagicMock()

        with (
            patch.object(searcher, "_get", return_value=response),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        # The loop should stop after first page (1 entry < page_size=25)
        assert len(papers) <= 1

    def test_search_network_error_returns_empty_list(self, simple_query):
        """Network error in _fetch_papers is caught and returns an empty list."""
        searcher = ScopusConnector(api_key="dummy")

        with patch.object(
            searcher, "_fetch_papers", side_effect=requests.ConnectionError("network down")
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_since_until_adds_date_param(self, simple_query, scopus_sample_json, mock_response):
        """search() adds date=YYYY-YYYY when since/until are given."""
        searcher = ScopusConnector(api_key="dummy")
        response = mock_response(json_data=scopus_sample_json)
        response.raise_for_status = MagicMock()
        get_calls: list = []

        def _fake_get(url, params=None, headers=None):
            get_calls.append(params)
            return response

        since = datetime.date(2019, 5, 1)
        until = datetime.date(2023, 11, 30)

        with (
            patch.object(searcher, "_get", side_effect=_fake_get),
            patch.object(searcher, "_rate_limit"),
        ):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        assert len(get_calls) >= 1
        params = get_calls[0]
        assert params["date"] == "2019-2023"

    def test_same_year_uses_single_year_format(
        self, simple_query, scopus_sample_json, mock_response
    ):
        """When since and until are in the same year, date=YYYY is used instead of YYYY-YYYY."""
        searcher = ScopusConnector(api_key="dummy")
        response = mock_response(json_data=scopus_sample_json)
        response.raise_for_status = MagicMock()
        get_calls: list = []

        def _fake_get(url, params=None, headers=None):
            get_calls.append(params)
            return response

        since = datetime.date(2020, 1, 1)
        until = datetime.date(2020, 6, 30)

        with (
            patch.object(searcher, "_get", side_effect=_fake_get),
            patch.object(searcher, "_rate_limit"),
        ):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        assert len(get_calls) >= 1
        params = get_calls[0]
        assert params["date"] == "2020"

    def test_service_error_body_logs_warning(self, simple_query, mock_response, caplog):
        """A Scopus 200 OK response with a service-error body logs a warning."""
        searcher = ScopusConnector(api_key="dummy")
        service_error_data = {
            "service-error": {
                "status": {
                    "statusCode": "AUTHENTICATION_ERROR",
                    "statusText": "Invalid API key",
                }
            }
        }
        response = mock_response(json_data=service_error_data)
        response.raise_for_status = MagicMock()

        with (
            patch.object(searcher, "_get", return_value=response),
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.scopus"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []
        assert any("Scopus API error" in m for m in caplog.messages)

    def test_error_response_body_logs_warning(self, simple_query, mock_response, caplog):
        """A Scopus 200 OK response with an error-response body logs a warning."""
        searcher = ScopusConnector(api_key="dummy")
        error_body = {
            "error-response": {"error-code": "QUOTA_EXCEEDED", "error-message": "over limit"}
        }
        response = mock_response(json_data=error_body)
        response.raise_for_status = MagicMock()

        with (
            patch.object(searcher, "_get", return_value=response),
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.scopus"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []
        assert any("Scopus API error" in m for m in caplog.messages)


class TestScopusConnectorIsOpenAccess:
    """Tests for is_open_access extraction from Scopus results."""

    def test_openaccess_flag_true(self):
        """openaccessFlag=True yields is_open_access=True."""
        entry = {"dc:title": "P", "openaccessFlag": True}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is True

    def test_openaccess_flag_false(self):
        """openaccessFlag=False yields is_open_access=False."""
        entry = {"dc:title": "P", "openaccessFlag": False}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is False

    def test_openaccess_int_one(self):
        """openaccess='1' (string) yields is_open_access=True."""
        entry = {"dc:title": "P", "openaccess": "1"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is True

    def test_openaccess_int_zero(self):
        """openaccess=0 yields is_open_access=False."""
        entry = {"dc:title": "P", "openaccess": 0}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is False

    def test_flag_takes_priority_over_int_field(self):
        """openaccessFlag takes priority over openaccess integer field."""
        entry = {"dc:title": "P", "openaccessFlag": True, "openaccess": "0"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is True

    def test_both_absent_sets_none(self):
        """Neither field present yields is_open_access=None."""
        entry = {"dc:title": "P"}
        paper = ScopusConnector(api_key="dummy")._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is None
