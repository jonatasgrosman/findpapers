"""Unit tests for OpenAlexConnector."""

from __future__ import annotations

import datetime
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from findpapers.connectors.openalex import (
    OpenAlexConnector,
    _reconstruct_abstract,
)
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.query.builders.openalex import OpenAlexQueryBuilder


class TestOpenAlexConnectorInit:
    """Tests for OpenAlexConnector initialisation."""

    def test_default_builder_created(self):
        """Connector creates OpenAlexQueryBuilder when none provided."""
        searcher = OpenAlexConnector()
        assert isinstance(searcher.query_builder, OpenAlexQueryBuilder)

    def test_email_stored(self):
        """Email is stored for polite pool requests."""
        searcher = OpenAlexConnector(email="test@example.com")
        assert searcher._email == "test@example.com"

    def test_name(self):
        """Connector name is 'OpenAlex'."""
        assert OpenAlexConnector().name == Database.OPENALEX

    def test_api_key_stored(self):
        """API key is stored on the instance."""
        searcher = OpenAlexConnector(api_key="mykey")
        assert searcher._api_key == "mykey"

    def test_warning_when_no_api_key(self, caplog):
        """A warning is logged when no API key is provided."""
        with caplog.at_level(logging.WARNING, logger="findpapers.connectors.openalex"):
            OpenAlexConnector()
        assert any("No API key provided for OpenAlex" in msg for msg in caplog.messages)

    def test_no_warning_when_api_key_provided(self, caplog):
        """No warning is logged when an API key is provided."""
        with caplog.at_level(logging.WARNING, logger="findpapers.connectors.openalex"):
            OpenAlexConnector(api_key="mykey")
        assert not any("No API key provided" in msg for msg in caplog.messages)


class TestOpenAlexPrepareHeaders:
    """Tests for _prepare_headers."""

    def test_no_user_agent_injected(self):
        """_prepare_headers does not inject a User-Agent header."""
        headers = OpenAlexConnector()._prepare_headers({})
        assert "User-Agent" not in headers

    def test_caller_headers_preserved(self):
        """Caller-supplied headers are returned as-is."""
        headers = OpenAlexConnector()._prepare_headers({"Accept": "application/json"})
        assert headers["Accept"] == "application/json"


class TestOpenAlexConnectorParsePaper:
    """Tests for _parse_paper."""

    def test_parse_sample_json(self, openalex_sample_json):
        """Parsing sample JSON results returns non-empty list of papers."""
        results = openalex_sample_json.get("results", [])
        assert len(results) > 0

        papers = [OpenAlexConnector()._parse_paper(r) for r in results]
        valid = [p for p in papers if p is not None]
        assert len(valid) > 0

    def test_paper_has_database_tag(self, openalex_sample_json):
        """Parsed paper has 'OpenAlex' in databases set."""
        result = openalex_sample_json["results"][0]
        paper = OpenAlexConnector()._parse_paper(result)
        assert paper is not None
        assert Database.OPENALEX in paper.found_in

    def test_missing_title_returns_none(self):
        """Result with blank title returns None."""
        paper = OpenAlexConnector()._parse_paper({"title": "  "})
        assert paper is None

    def test_open_access_url_used(self):
        """oa_url from open_access is used as paper URL."""
        work = {
            "title": "A Paper",
            "open_access": {"oa_url": "https://example.com/paper.pdf"},
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.url == "https://example.com/paper.pdf"

    def test_landing_page_url_fallback(self):
        """primary_location.landing_page_url is fallback when oa_url absent."""
        work = {
            "title": "A Paper",
            "open_access": {},
            "primary_location": {"landing_page_url": "https://example.com/landing"},
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.url == "https://example.com/landing"

    def test_pdf_url_from_locations(self):
        """pdf_url is extracted from the first location with one."""
        work = {
            "title": "A Paper",
            "locations": [
                {"pdf_url": None},
                {"pdf_url": "https://example.com/paper.pdf"},
            ],
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.pdf_url == "https://example.com/paper.pdf"

    def test_keywords_from_concepts_and_keywords(self):
        """Keywords collected from both concepts and keywords fields."""
        work = {
            "title": "A Paper",
            "concepts": [{"display_name": "Machine Learning"}],
            "keywords": [{"display_name": "Deep Learning"}],
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.keywords is not None
        assert "Machine Learning" in paper.keywords
        assert "Deep Learning" in paper.keywords

    def test_source_from_primary_location(self):
        """Source is built from primary_location.source when it is a journal."""
        work = {
            "title": "A Paper",
            "primary_location": {
                "source": {
                    "display_name": "Nature",
                    "issn_l": ["1234-5678"],
                    "type": "journal",
                },
                "landing_page_url": None,
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature"
        assert paper.source.issn == "1234-5678"

    def test_source_skipped_when_repository(self):
        """Repository-only sources should produce a repository-type source."""
        work = {
            "title": "A Dissertation",
            "primary_location": {
                "source": {
                    "display_name": "University of Liverpool",
                    "type": "repository",
                },
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "University of Liverpool"
        assert paper.source.source_type == SourceType.REPOSITORY

    def test_source_prefers_journal_over_repository(self):
        """When primary location is a repository, journal from other locations is used."""
        work = {
            "title": "A Paper",
            "primary_location": {
                "source": {
                    "display_name": "Zenodo",
                    "type": "repository",
                },
            },
            "locations": [
                {
                    "source": {
                        "display_name": "Zenodo",
                        "type": "repository",
                    },
                },
                {
                    "source": {
                        "display_name": "Nature Physics",
                        "issn_l": ["1745-2473"],
                        "type": "journal",
                    },
                },
            ],
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature Physics"
        assert paper.source.source_type == SourceType.JOURNAL

    def test_source_type_conference(self):
        """Conference source type is mapped to SourceType.CONFERENCE."""
        work = {
            "title": "A Paper",
            "primary_location": {
                "source": {
                    "display_name": "NeurIPS",
                    "type": "conference",
                },
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_source_type_book_series(self):
        """'book series' source type is mapped to SourceType.BOOK."""
        work = {
            "title": "A Paper",
            "primary_location": {
                "source": {
                    "display_name": "Lecture Notes in CS",
                    "type": "book series",
                },
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_source_type_ebook_platform(self):
        """'ebook platform' source type is mapped to SourceType.BOOK."""
        work = {
            "title": "A Paper",
            "primary_location": {
                "source": {
                    "display_name": "Springer eBooks",
                    "type": "ebook platform",
                },
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_source_without_type_is_accepted(self):
        """Sources without a type field are accepted (fallback)."""
        work = {
            "title": "A Paper",
            "primary_location": {
                "source": {"display_name": "Nature", "issn_l": ["1234-5678"]},
                "landing_page_url": None,
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature"

    def test_doi_stripped_of_prefix(self):
        """DOI prefix 'https://doi.org/' is stripped."""
        work = {
            "title": "A Paper",
            "doi": "https://doi.org/10.1234/test",
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.doi == "10.1234/test"

    def test_pages_from_biblio(self):
        """Pages are extracted from biblio.first_page and last_page."""
        work = {
            "title": "A Paper",
            "biblio": {"first_page": "100", "last_page": "115"},
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.page_range == "100\u2013115"

    def test_pages_first_only(self):
        """Only first_page is stored when last_page is absent."""
        work = {
            "title": "A Paper",
            "biblio": {"first_page": "42", "last_page": None},
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.page_range == "42"

    def test_pages_none_when_biblio_absent(self):
        """Pages are None when biblio is not present."""
        work = {"title": "A Paper"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.page_range is None

    def test_pages_from_sample_data(self, openalex_sample_json):
        """Pages are extracted from real sample data."""
        results = openalex_sample_json["results"]
        paper = OpenAlexConnector()._parse_paper(results[0])
        assert paper is not None
        assert paper.page_range is not None
        assert "\u2013" in paper.page_range  # en-dash separator

    def test_paper_type_article_from_work_type(self):
        """work.type 'article' maps to PaperType.ARTICLE."""
        work = {"title": "P", "type": "article"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_book_chapter(self):
        """work.type 'book-chapter' maps to PaperType.INBOOK."""
        work = {"title": "P", "type": "book-chapter"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.INBOOK

    def test_paper_type_dissertation(self):
        """work.type 'dissertation' maps to PaperType.PHDTHESIS."""
        work = {"title": "P", "type": "dissertation"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.PHDTHESIS

    def test_paper_type_preprint(self):
        """work.type 'preprint' maps to PaperType.UNPUBLISHED."""
        work = {"title": "P", "type": "preprint"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.UNPUBLISHED

    def test_paper_type_report(self):
        """work.type 'report' maps to PaperType.TECHREPORT."""
        work = {"title": "P", "type": "report"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.TECHREPORT

    def test_paper_type_book(self):
        """work.type 'book' maps to PaperType.BOOK."""
        work = {"title": "P", "type": "book"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.BOOK

    def test_paper_type_inproceedings_when_article_in_conference_source(self):
        """work.type 'article' with conference source promotes to INPROCEEDINGS."""
        work = {
            "title": "P",
            "type": "article",
            "primary_location": {
                "source": {
                    "display_name": "NeurIPS 2023",
                    "type": "conference",
                },
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_none_when_unknown(self):
        """Unknown work.type results in paper_type being None."""
        work = {"title": "P", "type": "unknownxyz"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.paper_type is None

    def test_language_extracted(self):
        """Language field from the work dict is normalised and stored."""
        work = {"title": "P", "language": "en"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.language == "en"

    def test_language_absent_is_none(self):
        """Paper language is None when 'language' key is absent."""
        work = {"title": "P"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.language is None

    def test_language_from_sample_json(self, openalex_sample_json):
        """Sample JSON works have their language field parsed correctly."""
        results = openalex_sample_json.get("results", [])
        papers = [OpenAlexConnector()._parse_paper(r) for r in results]
        valid = [p for p in papers if p is not None]
        # Every paper in the sample has a language field; they should all be 2-letter codes.
        for paper in valid:
            if paper.language is not None:
                assert len(paper.language) == 2, f"Unexpected language code: {paper.language!r}"


class TestOpenAlexConnectorReconstructAbstract:
    """Tests for _reconstruct_abstract helper."""

    def test_reconstruct_basic(self):
        """Inverted index is correctly reconstructed into a sentence."""
        inverted = {"Hello": [0], "world": [1]}
        result = _reconstruct_abstract(inverted)
        assert result == "Hello world"

    def test_reconstruct_returns_empty_on_none(self):
        """None inverted index returns empty string."""
        assert _reconstruct_abstract(None) == ""

    def test_reconstruct_returns_empty_on_empty_dict(self):
        """Empty dict returns empty string."""
        assert _reconstruct_abstract({}) == ""


class TestOpenAlexConnectorSearch:
    """Tests for search() with mocked HTTP calls."""

    def _make_next_page_response(self, mock_response: Any, empty: bool = False) -> MagicMock:
        """Build a response that signals no further pages."""
        data = {
            "meta": {"count": 0, "per_page": 25, "next_cursor": None},
            "results": [],
        }
        r = mock_response(json_data=data)
        r.raise_for_status = MagicMock()
        return r  # type: ignore[no-any-return]

    def test_search_returns_papers(self, simple_query, openalex_sample_json, mock_response):
        """search() returns papers from OpenAlex JSON response."""
        searcher = OpenAlexConnector()
        first_page = mock_response(json_data=openalex_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = self._make_next_page_response(mock_response)

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query)

        assert len(papers) > 0
        assert all(Database.OPENALEX in p.found_in for p in papers)

    def test_max_papers_respected(self, simple_query, openalex_sample_json, mock_response):
        """search() returns no more than max_papers papers."""
        searcher = OpenAlexConnector()
        first_page = mock_response(json_data=openalex_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = self._make_next_page_response(mock_response)

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query, max_papers=2)

        assert len(papers) <= 2

    def test_http_error_breaks_loop(self, simple_query):
        """Exception in _get breaks the loop and returns what was gathered."""
        searcher = OpenAlexConnector()

        with (
            patch.object(searcher, "_get", side_effect=requests.RequestException("timeout")),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_progress_callback_called(self, simple_query, openalex_sample_json, mock_response):
        """Progress callback is called after processing results."""
        searcher = OpenAlexConnector()
        first_page = mock_response(json_data=openalex_sample_json)
        first_page.raise_for_status = MagicMock()
        second_page = self._make_next_page_response(mock_response)
        callback = MagicMock()

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [first_page, second_page]
        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, progress_callback=callback)

        callback.assert_called()

    def test_search_network_error_returns_empty_list(self, simple_query):
        """Network error in _fetch_papers is caught and returns an empty list."""
        searcher = OpenAlexConnector()

        with patch.object(
            searcher, "_fetch_papers", side_effect=requests.ConnectionError("network down")
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_or_query_fetches_all_expansion_branches(self, or_query, mock_response):
        """Each OR clause is queried even when the first clause fills the budget.

        When an OR query is expanded into two sub-queries (one per clause),
        both HTTP requests must be issued.  Each branch uses an independent
        accumulator so that one clause cannot exhaust max_papers and prevent
        the remaining clauses from being fetched.
        """
        searcher = OpenAlexConnector()

        def _make_page(doi: str, title: str) -> MagicMock:
            data = {
                "meta": {"count": 1, "per_page": 1, "next_cursor": None},
                "results": [
                    {
                        "title": title,
                        "doi": f"https://doi.org/{doi}",
                        "publication_date": "2024-01-01",
                        "abstract_inverted_index": None,
                        "authorships": [],
                        "cited_by_count": 0,
                        "open_access": {},
                        "locations": [],
                        "primary_location": {},
                        "concepts": [],
                        "keywords": [],
                        "type": "article",
                    }
                ],
            }
            r = mock_response(json_data=data)
            r.raise_for_status = MagicMock()
            return r  # type: ignore[no-any-return]

        page_ml = _make_page("10.ml/1", "Machine Learning Paper")
        page_dl = _make_page("10.dl/1", "Deep Learning Paper")

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [page_ml, page_dl]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(or_query, max_papers=2)

        # Both OR clauses must have been fetched.
        assert len(papers) == 2
        dois = {p.doi for p in papers}
        assert "10.ml/1" in dois
        assert "10.dl/1" in dois

    def test_or_query_max_papers_still_respected(self, or_query, mock_response):
        """Final result is capped at max_papers even when OR expands to multiple clauses."""
        searcher = OpenAlexConnector()

        def _make_page(doi: str, title: str) -> MagicMock:
            data = {
                "meta": {"count": 1, "per_page": 1, "next_cursor": None},
                "results": [
                    {
                        "title": title,
                        "doi": f"https://doi.org/{doi}",
                        "publication_date": "2024-01-01",
                        "abstract_inverted_index": None,
                        "authorships": [],
                        "cited_by_count": 0,
                        "open_access": {},
                        "locations": [],
                        "primary_location": {},
                        "concepts": [],
                        "keywords": [],
                        "type": "article",
                    }
                ],
            }
            r = mock_response(json_data=data)
            r.raise_for_status = MagicMock()
            return r  # type: ignore[no-any-return]

        page_ml = _make_page("10.ml/1", "Machine Learning Paper")
        page_dl = _make_page("10.dl/1", "Deep Learning Paper")

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [page_ml, page_dl]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(or_query, max_papers=1)

        assert len(papers) <= 1

    def test_since_until_adds_filter_params(
        self, simple_query, openalex_sample_json, mock_response
    ):
        """search() adds from_publication_date/to_publication_date filters."""
        searcher = OpenAlexConnector()
        data = openalex_sample_json.copy()
        data["meta"] = {"count": 1, "next_cursor": None}
        response = mock_response(json_data=data)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        since = datetime.date(2022, 1, 1)
        until = datetime.date(2023, 6, 30)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        call_args = searcher._http_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        filter_str = params.get("filter", "")
        assert "from_publication_date:2022-01-01" in filter_str
        assert "to_publication_date:2023-06-30" in filter_str


class TestOpenAlexFieldsOfStudyAndSubjects:
    """Tests for fields_of_study and subjects extraction from primary_topic."""

    def test_primary_topic_extracted(self):
        """primary_topic populates fields_of_study and subjects."""
        work: dict[str, Any] = {
            "title": "A Paper",
            "primary_topic": {
                "display_name": "Technology-Enhanced Education Studies",
                "score": 0.9,
                "subfield": {"display_name": "Education"},
                "field": {"display_name": "Social Sciences"},
                "domain": {"display_name": "Social Sciences"},
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert "Social Sciences" in paper.fields_of_study
        assert "Education" in paper.subjects
        assert "Technology-Enhanced Education Studies" in paper.subjects

    def test_different_domain_and_field(self):
        """When domain and field differ, both go to fields_of_study."""
        work: dict[str, Any] = {
            "title": "A Paper",
            "primary_topic": {
                "display_name": "Machine Learning Algorithms",
                "subfield": {"display_name": "Artificial Intelligence"},
                "field": {"display_name": "Computer Science"},
                "domain": {"display_name": "Physical Sciences"},
            },
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert "Computer Science" in paper.fields_of_study
        assert "Physical Sciences" in paper.fields_of_study
        assert "Artificial Intelligence" in paper.subjects

    def test_no_primary_topic_empty_sets(self):
        """Paper without primary_topic has empty fields_of_study and subjects."""
        work: dict[str, Any] = {"title": "A Paper"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.fields_of_study == set()
        assert paper.subjects == set()

    def test_sample_json_has_fields_of_study(self, openalex_sample_json):
        """Papers from sample JSON have non-empty fields_of_study."""
        results = openalex_sample_json.get("results", [])
        papers = [OpenAlexConnector()._parse_paper(r) for r in results]
        valid = [p for p in papers if p is not None]
        papers_with_fos = [p for p in valid if p.fields_of_study]
        assert len(papers_with_fos) > 0


class TestOpenAlexConnectorIsOpenAccess:
    """Tests for is_open_access extraction from OpenAlex results."""

    def test_is_oa_true(self):
        """open_access.is_oa=True yields is_open_access=True."""
        work = {"title": "P", "open_access": {"is_oa": True, "oa_url": None}}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_open_access is True

    def test_is_oa_false(self):
        """open_access.is_oa=False yields is_open_access=False."""
        work = {"title": "P", "open_access": {"is_oa": False}}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_open_access is False

    def test_open_access_absent_sets_none(self):
        """Missing open_access object yields is_open_access=None."""
        work: dict[str, Any] = {"title": "P"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_open_access is None

    def test_is_oa_key_absent_in_open_access_sets_none(self):
        """open_access dict without is_oa key yields is_open_access=None."""
        work = {"title": "P", "open_access": {"oa_url": "https://example.com"}}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_open_access is None

    def test_is_open_access_from_sample_json(self, openalex_sample_json):
        """Sample JSON works have is_open_access parsed as a bool or None."""
        results = openalex_sample_json.get("results", [])
        papers = [OpenAlexConnector()._parse_paper(r) for r in results]
        valid = [p for p in papers if p is not None]
        for paper in valid:
            assert paper.is_open_access is None or isinstance(paper.is_open_access, bool)


class TestOpenAlexConnectorIsRetracted:
    """Tests for is_retracted extraction from OpenAlex results."""

    def test_is_retracted_true(self):
        """is_retracted=True in the work yields Paper.is_retracted=True."""
        work = {"title": "P", "is_retracted": True}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_retracted is True

    def test_is_retracted_false(self):
        """is_retracted=False in the work yields Paper.is_retracted=False."""
        work = {"title": "P", "is_retracted": False}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_retracted is False

    def test_is_retracted_absent_sets_none(self):
        """Missing is_retracted field yields Paper.is_retracted=None."""
        work: dict[str, Any] = {"title": "P"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.is_retracted is None

    def test_is_retracted_from_sample_json(self, openalex_sample_json):
        """Sample JSON works have is_retracted parsed as a bool or None."""
        results = openalex_sample_json.get("results", [])
        papers = [OpenAlexConnector()._parse_paper(r) for r in results]
        valid = [p for p in papers if p is not None]
        for paper in valid:
            assert paper.is_retracted is None or isinstance(paper.is_retracted, bool)


class TestOpenAlexConnectorFunders:
    """Tests for funders extraction from OpenAlex funders field."""

    def test_funders_extracted_from_funders_list(self):
        """display_name values in funders are collected into paper.funders."""
        work = {
            "title": "P",
            "funders": [
                {"display_name": "National Science Foundation", "id": "https://openalex.org/F1"},
                {"display_name": "National Institutes of Health", "id": "https://openalex.org/F2"},
            ],
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.funders == {"National Science Foundation", "National Institutes of Health"}

    def test_funders_empty_when_funders_absent(self):
        """Paper without funders field has an empty funders set."""
        work: dict[str, Any] = {"title": "P"}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.funders == set()

    def test_funders_empty_when_funders_is_empty_list(self):
        """Paper with empty funders list has an empty funders set."""
        work = {"title": "P", "funders": []}
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.funders == set()

    def test_funders_skips_blank_display_name(self):
        """Funder entries with blank display_name are skipped."""
        work = {
            "title": "P",
            "funders": [
                {"display_name": ""},
                {"display_name": "   "},
                {"display_name": "European Commission"},
            ],
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.funders == {"European Commission"}

    def test_funders_skips_missing_display_name_key(self):
        """Funder entries without display_name key are skipped."""
        work = {
            "title": "P",
            "funders": [
                {"id": "https://openalex.org/F1"},
                {"display_name": "Wellcome Trust"},
            ],
        }
        paper = OpenAlexConnector()._parse_paper(work)
        assert paper is not None
        assert paper.funders == {"Wellcome Trust"}


class TestOpenAlexConnectorFetchPaperById:
    """Tests for fetch_paper_by_id."""

    def test_fetch_paper_by_id_returns_paper(self, openalex_sample_json, mock_response):
        """fetch_paper_by_id returns a Paper when the API responds with a valid work."""
        # Pick the first result from the sample as a single-work response.
        single_work = openalex_sample_json["results"][0]
        connector = OpenAlexConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = mock_response(json_data=single_work)

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_id("W2741809807")

        assert paper is not None

    def test_fetch_paper_by_id_returns_none_on_404(self, mock_response):
        """fetch_paper_by_id returns None when the API responds with 404."""
        import requests as _requests

        connector = OpenAlexConnector()
        error_response = mock_response(status_code=404)
        error_response.status_code = 404
        http_error = _requests.HTTPError(response=error_response)
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = http_error

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("W9999999999")

        assert result is None

    def test_fetch_paper_by_id_returns_none_on_request_error(self):
        """fetch_paper_by_id returns None when the HTTP request fails."""
        connector = OpenAlexConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = requests.RequestException("timeout")

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("W2741809807")

        assert result is None


class TestOpenAlexConnectorURLPattern:
    """Tests for url_pattern and fetch_paper_by_url."""

    @pytest.mark.parametrize(
        ("url", "expected_id"),
        [
            ("https://openalex.org/W2741809807", "W2741809807"),
            ("https://openalex.org/works/W2741809807", "W2741809807"),
        ],
    )
    def test_url_pattern_matches_openalex_urls(self, url: str, expected_id: str) -> None:
        """url_pattern matches OpenAlex work landing-page URLs."""
        connector = OpenAlexConnector()
        match = connector.url_pattern.search(url)
        assert match is not None
        assert match.group(1) == expected_id

    def test_url_pattern_does_not_match_non_openalex_url(self) -> None:
        """url_pattern returns None for non-OpenAlex URLs."""
        connector = OpenAlexConnector()
        assert connector.url_pattern.search("https://arxiv.org/abs/1706.03762") is None

    def test_fetch_paper_by_url_delegates_to_fetch_paper_by_id(
        self, openalex_sample_json, mock_response
    ) -> None:
        """fetch_paper_by_url extracts the OpenAlex ID and delegates to fetch_paper_by_id."""
        single_work = openalex_sample_json["results"][0]
        connector = OpenAlexConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = mock_response(json_data=single_work)

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_url("https://openalex.org/W2741809807")

        assert paper is not None

    def test_fetch_paper_by_url_returns_none_for_unrecognised_url(self) -> None:
        """fetch_paper_by_url returns None when the URL is not an OpenAlex URL."""
        connector = OpenAlexConnector()
        result = connector.fetch_paper_by_url("https://arxiv.org/abs/1706.03762")
        assert result is None
