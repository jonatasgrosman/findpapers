"""Unit tests for SemanticScholarConnector."""

from __future__ import annotations

import datetime
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from findpapers.connectors.semantic_scholar import (
    _MIN_REQUEST_INTERVAL_DEFAULT,
    _MIN_REQUEST_INTERVAL_WITH_KEY,
    _PAGE_SIZE,
    SemanticScholarConnector,
)
from findpapers.core.author import Author
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.query.builders.semantic_scholar import SemanticScholarQueryBuilder


class TestSemanticScholarConnectorInit:
    """Tests for SemanticScholarConnector initialisation."""

    def test_default_builder_created(self):
        """Connector creates SemanticScholarQueryBuilder when none provided."""
        searcher = SemanticScholarConnector()
        assert isinstance(searcher.query_builder, SemanticScholarQueryBuilder)

    def test_api_key_stored(self):
        """API key is stored on the instance."""
        searcher = SemanticScholarConnector(api_key="test_key")
        assert searcher._api_key == "test_key"

    def test_warning_when_no_api_key(self, caplog):
        """A warning is logged when no API key is provided."""
        with caplog.at_level(logging.WARNING, logger="findpapers.connectors.semantic_scholar"):
            SemanticScholarConnector()
        assert any("No API key provided for Semantic Scholar" in msg for msg in caplog.messages)

    def test_no_warning_when_api_key_provided(self, caplog):
        """No warning is logged when an API key is provided."""
        with caplog.at_level(logging.WARNING, logger="findpapers.connectors.semantic_scholar"):
            SemanticScholarConnector(api_key="key")
        assert not any("No API key provided" in msg for msg in caplog.messages)

    def test_name(self):
        """Connector name is 'Semantic Scholar'."""
        assert SemanticScholarConnector().name == Database.SEMANTIC_SCHOLAR

    def test_rate_interval_without_key(self):
        """Default rate interval used when no API key provided."""
        searcher = SemanticScholarConnector()
        assert searcher._request_interval == _MIN_REQUEST_INTERVAL_DEFAULT

    def test_rate_interval_with_key(self):
        """Rate interval with key matches INTERVAL_WITH_KEY constant."""
        searcher = SemanticScholarConnector(api_key="key")
        assert searcher._request_interval == _MIN_REQUEST_INTERVAL_WITH_KEY


class TestSemanticScholarConnectorParsePaper:
    """Tests for _parse_paper."""

    def test_parse_sample_json(self, semantic_scholar_sample_json):
        """Parsing sample data entries returns non-empty list of papers."""
        data = semantic_scholar_sample_json.get("data", [])
        assert len(data) > 0

        papers = [SemanticScholarConnector()._parse_paper(item) for item in data]
        valid = [p for p in papers if p is not None]
        assert len(valid) > 0

    def test_paper_has_database_tag(self, semantic_scholar_sample_json):
        """Parsed paper has 'Semantic Scholar' in databases set."""
        item = semantic_scholar_sample_json["data"][0]
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert Database.SEMANTIC_SCHOLAR in paper.found_in

    def test_missing_title_returns_none(self):
        """Item with blank title returns None."""
        paper = SemanticScholarConnector()._parse_paper({"title": "", "abstract": "a"})
        assert paper is None

    def test_pdf_url_extracted(self):
        """openAccessPdf.url is extracted as pdf_url."""
        item = {
            "title": "A Paper",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.pdf_url == "https://example.com/paper.pdf"

    def test_keywords_from_fields_of_study(self):
        """fieldsOfStudy strings are collected as fields_of_study, not keywords."""
        item = {
            "title": "A Paper",
            "fieldsOfStudy": ["Computer Science", "Biology"],
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert "Computer Science" in paper.fields_of_study
        assert "Biology" in paper.fields_of_study

    def test_source_from_journal(self):
        """Source is built from journal.name."""
        item = {
            "title": "A Paper",
            "journal": {"name": "Nature", "pages": "1-10"},
            "venue": "",
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature"
        assert paper.page_range == "1-10"

    def test_source_from_venue_fallback(self):
        """venue is used as source title when journal.name is absent."""
        item = {
            "title": "A Paper",
            "journal": {},
            "venue": "ICML",
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "ICML"

    def test_source_type_from_publication_venue_journal(self):
        """publicationVenue.type 'journal' maps to SourceType.JOURNAL."""
        item = {
            "title": "A Paper",
            "journal": {"name": "Nature"},
            "publicationVenue": {"type": "journal"},
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_source_type_from_publication_venue_conference(self):
        """publicationVenue.type 'conference' maps to SourceType.CONFERENCE."""
        item = {
            "title": "A Paper",
            "journal": {"name": "NeurIPS"},
            "publicationVenue": {"type": "conference"},
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_source_type_fallback_to_publication_types(self):
        """publicationTypes list is used when publicationVenue is absent."""
        item = {
            "title": "A Paper",
            "journal": {"name": "Some Journal"},
            "publicationTypes": ["JournalArticle"],
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_source_type_conference_from_publication_types(self):
        """publicationTypes 'Conference' maps to SourceType.CONFERENCE."""
        item = {
            "title": "A Paper",
            "journal": {"name": "Workshop"},
            "publicationTypes": ["Conference"],
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_source_type_none_when_no_venue_or_types(self):
        """source_type is None when neither publicationVenue nor publicationTypes is present."""
        item = {
            "title": "A Paper",
            "journal": {"name": "Unknown"},
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type is None

    def test_doi_from_external_ids(self):
        """DOI is extracted from externalIds.DOI."""
        item = {
            "title": "A Paper",
            "externalIds": {"DOI": "10.1234/test"},
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.doi == "10.1234/test"

    def test_doi_derived_from_arxiv_id_when_doi_absent(self):
        """DOI is derived from ArXivId when externalIds.DOI is absent."""
        item = {
            "title": "A Paper",
            "externalIds": {"ArXivId": "1706.03762"},
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.doi == "10.48550/arXiv.1706.03762"

    def test_explicit_doi_takes_priority_over_arxiv_id(self):
        """externalIds.DOI takes priority over ArXivId derivation."""
        item = {
            "title": "A Paper",
            "externalIds": {
                "DOI": "10.1145/3531146.3533206",
                "ArXivId": "2301.12345",
            },
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.doi == "10.1145/3531146.3533206"

    def test_doi_none_when_no_external_ids(self):
        """DOI is None when externalIds has neither DOI nor ArXivId."""
        item = {"title": "A Paper", "externalIds": {}}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.doi is None

    def test_year_fallback_for_pub_date(self):
        """Year field is used as fallback when publicationDate is absent."""
        item = {"title": "A Paper", "year": 2020}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.publication_date is not None
        assert paper.publication_date.year == 2020

    def test_paper_type_article_from_journal_article(self):
        """publicationTypes 'JournalArticle' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["JournalArticle"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_article_from_case_report(self):
        """publicationTypes 'CaseReport' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["CaseReport"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_article_from_clinical_trial(self):
        """publicationTypes 'ClinicalTrial' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["ClinicalTrial"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_article_from_editorial(self):
        """publicationTypes 'Editorial' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["Editorial"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_article_from_letters_and_comments(self):
        """publicationTypes 'LettersAndComments' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["LettersAndComments"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_article_from_meta_analysis(self):
        """publicationTypes 'MetaAnalysis' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["MetaAnalysis"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_article_from_study(self):
        """publicationTypes 'Study' maps to PaperType.ARTICLE."""
        item = {"title": "P", "publicationTypes": ["Study"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_inproceedings_from_conference(self):
        """publicationTypes 'Conference' maps to PaperType.INPROCEEDINGS."""
        item = {"title": "P", "publicationTypes": ["Conference"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_book_from_book(self):
        """publicationTypes 'Book' maps to PaperType.BOOK."""
        item = {"title": "P", "publicationTypes": ["Book"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.BOOK

    def test_paper_type_inbook_from_book_section(self):
        """publicationTypes 'BookSection' maps to PaperType.INBOOK."""
        item = {"title": "P", "publicationTypes": ["BookSection"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.INBOOK

    def test_paper_type_misc_from_dataset(self):
        """publicationTypes 'Dataset' maps to PaperType.MISC."""
        item = {"title": "P", "publicationTypes": ["Dataset"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.MISC

    def test_paper_type_misc_from_news(self):
        """publicationTypes 'News' maps to PaperType.MISC."""
        item = {"title": "P", "publicationTypes": ["News"]}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is PaperType.MISC

    def test_paper_type_none_when_missing(self):
        """Missing publicationTypes results in paper_type being None."""
        item = {"title": "P"}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.paper_type is None


class TestSemanticScholarConnectorSearch:
    """Tests for search() with mocked HTTP calls."""

    def _empty_page(self, mock_response):
        """A response with no token and no data (signals last page)."""
        data = {"total": 0, "data": [], "token": None}
        r = mock_response(json_data=data)
        r.raise_for_status = MagicMock()
        return r

    def test_search_returns_papers(
        self,
        simple_query,
        semantic_scholar_sample_json,
        mock_response,
    ):
        """search() returns papers from Semantic Scholar bulk search response."""
        searcher = SemanticScholarConnector()
        first_page = mock_response(json_data=semantic_scholar_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = self._empty_page(mock_response)

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query)

        assert len(papers) > 0
        assert all(Database.SEMANTIC_SCHOLAR in p.found_in for p in papers)

    def test_max_papers_respected(
        self,
        simple_query,
        semantic_scholar_sample_json,
        mock_response,
    ):
        """search() returns no more than max_papers papers."""
        searcher = SemanticScholarConnector()
        first_page = mock_response(json_data=semantic_scholar_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = self._empty_page(mock_response)

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query, max_papers=2)

        assert len(papers) <= 2

    def test_http_error_breaks_loop(self, simple_query):
        """Exception in _get breaks the loop and returns empty list."""
        searcher = SemanticScholarConnector()

        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("network error")),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_progress_callback_called(
        self,
        simple_query,
        semantic_scholar_sample_json,
        mock_response,
    ):
        """Progress callback is called after each page."""
        searcher = SemanticScholarConnector()
        first_page = mock_response(json_data=semantic_scholar_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = self._empty_page(mock_response)
        callback = MagicMock()

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]
        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, progress_callback=callback)

        callback.assert_called()

    def test_search_network_error_returns_empty_list(self, simple_query):
        """Network error in _fetch_papers is caught and returns an empty list."""
        searcher = SemanticScholarConnector()

        with patch.object(
            searcher, "_fetch_papers", side_effect=requests.ConnectionError("network down")
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_since_until_adds_date_range_param(
        self, simple_query, semantic_scholar_sample_json, mock_response
    ):
        """search() adds publicationDateOrYear range when since/until are given."""
        searcher = SemanticScholarConnector()
        first_page = mock_response(json_data=semantic_scholar_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = mock_response(json_data={"total": 0, "token": None, "data": []})
        second_page.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]

        since = datetime.date(2022, 1, 1)
        until = datetime.date(2023, 12, 31)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        call_args = searcher._http_session.get.call_args_list[0]
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("publicationDateOrYear") == "2022-01-01:2023-12-31"

    def test_since_only_open_ended_range(
        self, simple_query, semantic_scholar_sample_json, mock_response
    ):
        """search() with only `since` produces an open-ended range."""
        searcher = SemanticScholarConnector()
        first_page = mock_response(json_data=semantic_scholar_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = mock_response(json_data={"total": 0, "token": None, "data": []})
        second_page.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]

        since = datetime.date(2021, 6, 15)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since)

        call_args = searcher._http_session.get.call_args_list[0]
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params.get("publicationDateOrYear") == "2021-06-15:"

    def test_min_request_interval_property(self):
        """min_request_interval property delegates to _request_interval."""
        searcher = SemanticScholarConnector(api_key="key")
        assert searcher.min_request_interval == _MIN_REQUEST_INTERVAL_WITH_KEY

    def test_prepare_headers_injects_api_key(self):
        """_prepare_headers adds x-api-key header when API key is set."""
        searcher = SemanticScholarConnector(api_key="secret-key")
        headers = searcher._prepare_headers({})
        assert headers["x-api-key"] == "secret-key"

    def test_prepare_headers_no_key(self):
        """_prepare_headers does not add x-api-key when no key is set."""
        searcher = SemanticScholarConnector()
        headers = searcher._prepare_headers({})
        assert "x-api-key" not in headers

    def test_pagination_token_used_on_second_page(self, simple_query, mock_response):
        """Pagination token from page 1 is sent as param on page 2."""
        # Build a first page with exactly _PAGE_SIZE items so size check passes.
        items = [{"title": f"Paper {i}"} for i in range(_PAGE_SIZE)]
        page1 = mock_response(json_data={"total": _PAGE_SIZE + 5, "token": "NEXT", "data": items})
        page1.raise_for_status = MagicMock()
        page2 = mock_response(json_data={"total": _PAGE_SIZE + 5, "token": None, "data": []})
        page2.raise_for_status = MagicMock()

        searcher = SemanticScholarConnector()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [page1, page2]

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query)

        # The second call should include the token param.
        assert searcher._http_session.get.call_count == 2
        second_call_params = searcher._http_session.get.call_args_list[1].kwargs.get(
            "params"
        ) or searcher._http_session.get.call_args_list[1][1].get("params", {})
        assert second_call_params.get("token") == "NEXT"

    def test_empty_data_on_first_page_returns_empty(self, simple_query, mock_response):
        """When first page returns no items, search returns empty list."""
        page = mock_response(json_data={"total": 0, "token": None, "data": []})
        page.raise_for_status = MagicMock()

        searcher = SemanticScholarConnector()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = page

        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_request_failure_logs_progress_context(self, simple_query, caplog):
        """A failed page request logs how many papers were retrieved so far."""
        searcher = SemanticScholarConnector()
        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("boom")),
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.semantic_scholar"),
        ):
            searcher.search(simple_query)
        assert any("search stopped early" in m for m in caplog.messages)

    def test_empty_data_before_total_logs_warning(self, simple_query, mock_response, caplog):
        """Data running out before the reported total logs a pagination-limit warning."""
        items = [{"title": f"Paper {i}"} for i in range(_PAGE_SIZE)]
        page1 = mock_response(json_data={"total": _PAGE_SIZE + 5, "token": "NEXT", "data": items})
        page1.raise_for_status = MagicMock()
        page2 = mock_response(json_data={"total": _PAGE_SIZE + 5, "token": None, "data": []})
        page2.raise_for_status = MagicMock()

        searcher = SemanticScholarConnector()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [page1, page2]

        with (
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.semantic_scholar"),
        ):
            searcher.search(simple_query)

        assert any("pagination limit" in m for m in caplog.messages)


class TestSemanticScholarAffiliationEnrichment:
    """Tests for _enrich_author_affiliations."""

    def test_affiliation_batch_request_error_continues(self):
        """RequestException during batch fetch is caught and processing continues."""
        searcher = SemanticScholarConnector()
        author = Author(name="Test Author")
        id_map: dict[str, list] = {"auth1": [author]}

        with patch.object(searcher, "_post", side_effect=requests.RequestException("fail")):
            # Should not raise.
            searcher._enrich_author_affiliations(id_map)

        assert author.affiliation is None

    def test_affiliation_non_dict_result_skipped(self):
        """Non-dict entries in the batch response are silently skipped."""
        searcher = SemanticScholarConnector()
        author = Author(name="Test Author")
        id_map: dict[str, list] = {"auth1": [author]}

        mock_resp = MagicMock()
        # API returns a non-dict entry (e.g. None for unresolved author).
        mock_resp.json.return_value = [None, "invalid"]

        with patch.object(searcher, "_post", return_value=mock_resp):
            searcher._enrich_author_affiliations(id_map)

        assert author.affiliation is None

    def test_affiliation_empty_affiliations_skipped(self):
        """Authors with empty affiliations list are skipped."""
        searcher = SemanticScholarConnector()
        author = Author(name="Test Author")
        id_map: dict[str, list] = {"auth1": [author]}

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"authorId": "auth1", "affiliations": []},
        ]

        with patch.object(searcher, "_post", return_value=mock_resp):
            searcher._enrich_author_affiliations(id_map)

        assert author.affiliation is None

    def test_affiliation_set_on_matching_authors(self):
        """Affiliations are joined and set on matching authors."""
        searcher = SemanticScholarConnector()
        author1 = Author(name="Author One")
        author2 = Author(name="Author One Dup")
        id_map: dict[str, list] = {"auth1": [author1, author2]}

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"authorId": "auth1", "affiliations": ["MIT", "Stanford"]},
        ]

        with patch.object(searcher, "_post", return_value=mock_resp):
            searcher._enrich_author_affiliations(id_map)

        assert author1.affiliation == "MIT; Stanford"
        assert author2.affiliation == "MIT; Stanford"

    def test_affiliation_not_overwritten_if_already_set(self):
        """Authors with existing affiliation are not overwritten."""
        searcher = SemanticScholarConnector()
        author = Author(name="Test Author")
        author.affiliation = "Existing"
        id_map: dict[str, list] = {"auth1": [author]}

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"authorId": "auth1", "affiliations": ["MIT"]},
        ]

        with patch.object(searcher, "_post", return_value=mock_resp):
            searcher._enrich_author_affiliations(id_map)

        assert author.affiliation == "Existing"


class TestSemanticScholarFieldsOfStudyAndSubjects:
    """Tests for fields_of_study and subjects extraction."""

    def test_fields_of_study_from_fieldsOfStudy(self):
        """fieldsOfStudy populates fields_of_study."""
        item = {
            "title": "A Paper",
            "fieldsOfStudy": ["Computer Science", "Biology"],
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.fields_of_study == {"Computer Science", "Biology"}

    def test_subjects_from_s2FieldsOfStudy(self):
        """s2FieldsOfStudy categories not in fieldsOfStudy go to subjects."""
        item = {
            "title": "A Paper",
            "fieldsOfStudy": ["Computer Science"],
            "s2FieldsOfStudy": [
                {"category": "Computer Science", "source": "external"},
                {"category": "Engineering", "source": "s2-fos-model"},
            ],
        }
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.fields_of_study == {"Computer Science"}
        # Engineering is in s2FieldsOfStudy but not in fieldsOfStudy -> subjects
        assert "Engineering" in paper.subjects
        # Computer Science is already in fields_of_study, not duplicated in subjects
        assert "Computer Science" not in paper.subjects

    def test_no_fields_empty_sets(self):
        """Paper without fieldsOfStudy or s2FieldsOfStudy has empty sets."""
        item = {"title": "A Paper"}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.fields_of_study == set()
        assert paper.subjects == set()


class TestSemanticScholarConnectorIsOpenAccess:
    """Tests for is_open_access extraction from Semantic Scholar results."""

    def test_is_open_access_true(self):
        """isOpenAccess=True yields is_open_access=True."""
        item = {"title": "P", "isOpenAccess": True}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is True

    def test_is_open_access_false(self):
        """isOpenAccess=False yields is_open_access=False."""
        item = {"title": "P", "isOpenAccess": False}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is False

    def test_is_open_access_absent_sets_none(self):
        """Missing isOpenAccess key yields is_open_access=None."""
        item = {"title": "P"}
        paper = SemanticScholarConnector()._parse_paper(item)
        assert paper is not None
        assert paper.is_open_access is None


class TestSemanticScholarConnectorFetchPaperById:
    """Tests for fetch_paper_by_id."""

    def test_fetch_paper_by_id_returns_paper(self, semantic_scholar_sample_json, mock_response):
        """fetch_paper_by_id returns a Paper when the API responds with a valid record."""
        single_paper = semantic_scholar_sample_json["data"][0]
        connector = SemanticScholarConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = mock_response(json_data=single_paper)

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_id("204e3073870fae3d05bcbc2f6a8e263d9b72e776")

        assert paper is not None

    def test_fetch_paper_by_id_returns_none_on_404(self, mock_response):
        """fetch_paper_by_id returns None when the API responds with 404."""
        connector = SemanticScholarConnector()
        error_response = mock_response(status_code=404)
        error_response.status_code = 404
        http_error = requests.HTTPError(response=error_response)
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = http_error

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("a" * 40)

        assert result is None

    def test_fetch_paper_by_id_returns_none_on_request_error(self):
        """fetch_paper_by_id returns None when the HTTP request fails."""
        connector = SemanticScholarConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = requests.RequestException("timeout")

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("204e3073870fae3d05bcbc2f6a8e263d9b72e776")

        assert result is None


class TestSemanticScholarConnectorURLPattern:
    """Tests for url_pattern and fetch_paper_by_url."""

    @pytest.mark.parametrize(
        ("url", "expected_id"),
        [
            (
                "https://www.semanticscholar.org/paper/Attention-is-All-you-Need/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
                "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
            ),
            (
                "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
                "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
            ),
        ],
    )
    def test_url_pattern_matches_semantic_scholar_urls(self, url: str, expected_id: str) -> None:
        """url_pattern matches Semantic Scholar paper landing-page URLs."""
        connector = SemanticScholarConnector()
        match = connector.url_pattern.search(url)
        assert match is not None
        assert match.group(1) == expected_id

    def test_url_pattern_does_not_match_non_ss_url(self) -> None:
        """url_pattern returns None for non-Semantic Scholar URLs."""
        connector = SemanticScholarConnector()
        assert connector.url_pattern.search("https://arxiv.org/abs/1706.03762") is None

    def test_fetch_paper_by_url_delegates_to_fetch_paper_by_id(
        self, semantic_scholar_sample_json, mock_response
    ) -> None:
        """fetch_paper_by_url extracts the SS ID and delegates to fetch_paper_by_id."""
        single_paper = semantic_scholar_sample_json["data"][0]
        connector = SemanticScholarConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = mock_response(json_data=single_paper)
        ss_url = "https://www.semanticscholar.org/paper/Attention/204e3073870fae3d05bcbc2f6a8e263d9b72e776"

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_url(ss_url)

        assert paper is not None

    def test_fetch_paper_by_url_returns_none_for_unrecognised_url(self) -> None:
        """fetch_paper_by_url returns None when the URL is not a Semantic Scholar URL."""
        connector = SemanticScholarConnector()
        result = connector.fetch_paper_by_url("https://arxiv.org/abs/1706.03762")
        assert result is None
