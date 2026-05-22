"""Unit tests for findpapers.connectors.crossref."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from findpapers.connectors.crossref import (
    CrossRefConnector,
)
from findpapers.core.source import SourceType

# ---------------------------------------------------------------------------
# Sample CrossRef work records for testing
# ---------------------------------------------------------------------------

_MINIMAL_WORK: dict = {
    "title": ["A Minimal Paper"],
    "DOI": "10.1234/minimal",
}

_FULL_WORK: dict = {
    "title": ["Deep Learning for Natural Language Processing"],
    "DOI": "10.1038/nature12373",
    "abstract": "<jats:p>We present a <jats:italic>novel</jats:italic> approach.</jats:p>",
    "author": [
        {
            "given": "John",
            "family": "Smith",
            "affiliation": [{"name": "MIT"}],
        },
        {
            "given": "Jane",
            "family": "Doe",
            "affiliation": [{"name": "Stanford"}, {"name": "Google"}],
        },
    ],
    "published-print": {"date-parts": [[2023, 6, 15]]},
    "container-title": ["Nature"],
    "publisher": "Springer Nature",
    "ISSN": ["0028-0836", "1476-4687"],
    "ISBN": ["978-3-030-12345-6"],
    "page": "529-533",
    "subject": ["Artificial Intelligence", "Computer Science"],
    "is-referenced-by-count": 42,
    "type": "journal-article",
    "link": [
        {
            "URL": "https://example.com/paper.pdf",
            "content-type": "application/pdf",
        }
    ],
    "URL": "http://dx.doi.org/10.1038/nature12373",
}


# ---------------------------------------------------------------------------
# CrossRefConnector._strip_jats_tags
# ---------------------------------------------------------------------------


class TestStripJatsTags:
    """Tests for JATS/HTML tag removal from abstracts."""

    def test_plain_text_unchanged(self) -> None:
        """Plain text without tags is returned unchanged."""
        assert CrossRefConnector._strip_jats_tags("Hello world") == "Hello world"

    def test_jats_p_tags_removed(self) -> None:
        """JATS paragraph tags are stripped."""
        assert CrossRefConnector._strip_jats_tags("<jats:p>Hello</jats:p>") == "Hello"

    def test_nested_tags_removed(self) -> None:
        """Nested JATS tags are all stripped."""
        text = "<jats:p>A <jats:italic>novel</jats:italic> approach.</jats:p>"
        assert CrossRefConnector._strip_jats_tags(text) == "A novel approach."

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert CrossRefConnector._strip_jats_tags("") == ""


# ---------------------------------------------------------------------------
# CrossRefConnector._parse_date
# ---------------------------------------------------------------------------


class TestParseCrossrefDate:
    """Tests for date extraction from CrossRef records."""

    def test_full_date(self) -> None:
        """Full year-month-day date is parsed correctly."""
        work = {"published-print": {"date-parts": [[2023, 6, 15]]}}
        assert CrossRefConnector._parse_date(work) == datetime.date(2023, 6, 15)

    def test_year_month_only(self) -> None:
        """Year-month defaults day to 1."""
        work = {"published-print": {"date-parts": [[2023, 6]]}}
        assert CrossRefConnector._parse_date(work) == datetime.date(2023, 6, 1)

    def test_year_only(self) -> None:
        """Year-only date defaults month and day to 1."""
        work: dict = {"published-print": {"date-parts": [[2023]]}}
        assert CrossRefConnector._parse_date(work) == datetime.date(2023, 1, 1)

    def test_fallback_to_issued(self) -> None:
        """Falls back to 'issued' when 'published-print' is absent."""
        work = {"issued": {"date-parts": [[2022, 3, 10]]}}
        assert CrossRefConnector._parse_date(work) == datetime.date(2022, 3, 10)

    def test_fallback_priority(self) -> None:
        """'published-print' takes priority over 'published-online'."""
        work = {
            "published-print": {"date-parts": [[2023, 1, 1]]},
            "published-online": {"date-parts": [[2022, 12, 25]]},
        }
        assert CrossRefConnector._parse_date(work) == datetime.date(2023, 1, 1)

    def test_no_date_fields(self) -> None:
        """Returns None when no date fields are present."""
        assert CrossRefConnector._parse_date({}) is None

    def test_empty_date_parts(self) -> None:
        """Returns None when date-parts is empty."""
        work: dict = {"published-print": {"date-parts": [[]]}}
        assert CrossRefConnector._parse_date(work) is None


# ---------------------------------------------------------------------------
# CrossRefConnector._parse_authors
# ---------------------------------------------------------------------------


class TestParseCrossrefAuthors:
    """Tests for author parsing from CrossRef records."""

    def test_given_and_family(self) -> None:
        """Authors with given+family names are combined correctly."""
        work = {
            "author": [
                {"given": "John", "family": "Smith"},
            ]
        }
        authors = CrossRefConnector._parse_authors(work)
        assert len(authors) == 1
        assert authors[0].name == "John Smith"

    def test_family_only(self) -> None:
        """Author with only family name is accepted."""
        work = {"author": [{"family": "Smith"}]}
        authors = CrossRefConnector._parse_authors(work)
        assert len(authors) == 1
        assert authors[0].name == "Smith"

    def test_organisational_author(self) -> None:
        """Authors with only 'name' (e.g. organisations) are handled."""
        work = {"author": [{"name": "WHO Consortium"}]}
        authors = CrossRefConnector._parse_authors(work)
        assert len(authors) == 1
        assert authors[0].name == "WHO Consortium"

    def test_affiliations_mapped(self) -> None:
        """Author affiliations are joined with semicolons."""
        work = {
            "author": [
                {
                    "given": "Jane",
                    "family": "Doe",
                    "affiliation": [{"name": "MIT"}, {"name": "Google"}],
                }
            ]
        }
        authors = CrossRefConnector._parse_authors(work)
        assert authors[0].affiliation == "MIT; Google"

    def test_no_authors(self) -> None:
        """Empty author list returns empty list."""
        assert CrossRefConnector._parse_authors({}) == []

    def test_multiple_authors(self) -> None:
        """Multiple authors are all parsed."""
        work = {
            "author": [
                {"given": "A", "family": "One"},
                {"given": "B", "family": "Two"},
                {"given": "C", "family": "Three"},
            ]
        }
        authors = CrossRefConnector._parse_authors(work)
        assert len(authors) == 3
        assert authors[2].name == "C Three"


# ---------------------------------------------------------------------------
# CrossRefConnector._parse_keywords
# ---------------------------------------------------------------------------


class TestParseCrossrefKeywords:
    """Tests for keyword/subject extraction."""

    def test_subjects_extracted(self) -> None:
        """Subject list is converted to keyword set."""
        work = {"subject": ["AI", "Machine Learning"]}
        assert CrossRefConnector._parse_keywords(work) == {"AI", "Machine Learning"}

    def test_empty_subjects(self) -> None:
        """Empty subject list returns empty set."""
        assert CrossRefConnector._parse_keywords({"subject": []}) == set()

    def test_no_subject_field(self) -> None:
        """Missing subject field returns empty set."""
        assert CrossRefConnector._parse_keywords({}) == set()

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped from subjects."""
        work = {"subject": ["  AI  ", "ML  "]}
        assert CrossRefConnector._parse_keywords(work) == {"AI", "ML"}


# ---------------------------------------------------------------------------
# CrossRefConnector._parse_pdf_url
# ---------------------------------------------------------------------------


class TestParseCrossrefPdfUrl:
    """Tests for PDF URL extraction from link entries."""

    def test_pdf_link_found(self) -> None:
        """PDF URL is extracted when content-type contains 'pdf'."""
        work = {
            "link": [{"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}]
        }
        assert CrossRefConnector._parse_pdf_url(work) == "https://example.com/paper.pdf"

    def test_no_pdf_link(self) -> None:
        """Returns None when no PDF link exists."""
        work = {"link": [{"URL": "https://example.com", "content-type": "text/html"}]}
        assert CrossRefConnector._parse_pdf_url(work) is None

    def test_no_links(self) -> None:
        """Returns None when link field is empty."""
        assert CrossRefConnector._parse_pdf_url({"link": []}) is None
        assert CrossRefConnector._parse_pdf_url({}) is None


# ---------------------------------------------------------------------------
# CrossRefConnector._build_paper
# ---------------------------------------------------------------------------


class TestBuildPaperFromCrossref:
    """Tests for building a Paper from a CrossRef work record."""

    def test_minimal_work(self) -> None:
        """Minimal CrossRef record with just title and DOI builds a Paper."""
        paper = CrossRefConnector._build_paper(_MINIMAL_WORK)
        assert paper is not None
        assert paper.title == "A Minimal Paper"
        assert paper.doi == "10.1234/minimal"

    def test_none_input(self) -> None:
        """None input returns None."""
        assert CrossRefConnector._build_paper(None) is None  # type: ignore[arg-type]

    def test_empty_dict(self) -> None:
        """Empty dict returns None (no title)."""
        assert CrossRefConnector._build_paper({}) is None

    def test_no_title(self) -> None:
        """Work without title returns None."""
        assert CrossRefConnector._build_paper({"DOI": "10.1234/x"}) is None

    def test_full_work_title(self) -> None:
        """Full record has correct title."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.title == "Deep Learning for Natural Language Processing"

    def test_full_work_abstract_stripped(self) -> None:
        """Abstract has JATS tags stripped."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert "<jats:" not in paper.abstract
        assert "novel" in paper.abstract

    def test_full_work_authors(self) -> None:
        """Authors are parsed with affiliations."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert len(paper.authors) == 2
        assert paper.authors[0].name == "John Smith"
        assert paper.authors[0].affiliation == "MIT"
        assert paper.authors[1].affiliation == "Stanford; Google"

    def test_full_work_date(self) -> None:
        """Publication date is parsed correctly."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.publication_date == datetime.date(2023, 6, 15)

    def test_full_work_source(self) -> None:
        """Source is built with ISSN, ISBN, publisher, and type."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature"
        assert paper.source.issn == "0028-0836"
        assert paper.source.isbn == "978-3-030-12345-6"
        assert paper.source.publisher == "Springer Nature"
        assert paper.source.source_type == SourceType.JOURNAL

    def test_full_work_citations(self) -> None:
        """Citations count is extracted."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.citations == 42

    def test_full_work_pages(self) -> None:
        """Page range is extracted."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.page_range == "529-533"

    def test_full_work_keywords(self) -> None:
        """Keywords/subjects are extracted."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert "Artificial Intelligence" in paper.keywords

    def test_full_work_pdf_url(self) -> None:
        """PDF URL is extracted."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.pdf_url == "https://example.com/paper.pdf"

    def test_conference_source_type(self) -> None:
        """Conference type is mapped correctly."""
        work = {
            "title": ["Conf Paper"],
            "container-title": ["ACL 2023"],
            "type": "proceedings-article",
        }
        paper = CrossRefConnector._build_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_book_source_type(self) -> None:
        """Book type is mapped correctly."""
        work = {
            "title": ["A Chapter"],
            "container-title": ["Some Book"],
            "type": "book-chapter",
        }
        paper = CrossRefConnector._build_paper(work)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_no_source_when_no_container_title(self) -> None:
        """Source is None when container-title is absent."""
        paper = CrossRefConnector._build_paper(_MINIMAL_WORK)
        assert paper is not None
        assert paper.source is None

    def test_databases_set_to_crossref(self) -> None:
        """Built paper always has databases={'crossref'}."""
        paper = CrossRefConnector._build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.databases == {"crossref"}

    def test_references_extracted_from_reference_field(self) -> None:
        """Reference DOIs from the CrossRef reference list are extracted."""
        work = {
            **_MINIMAL_WORK,
            "reference": [
                {"key": "r1", "DOI": "10.1000/ref1"},
                {"key": "r2", "DOI": "  10.1000/ref2  "},  # whitespace stripped
                {"key": "r3"},  # no DOI — skipped
                {"key": "r4", "DOI": ""},  # empty DOI — skipped
            ],
        }
        paper = CrossRefConnector._build_paper(work)
        assert paper is not None
        assert paper.references == ["10.1000/ref1", "10.1000/ref2"]

    def test_references_empty_when_no_reference_field(self) -> None:
        """Paper built without a reference field has an empty references list."""
        paper = CrossRefConnector._build_paper(_MINIMAL_WORK)
        assert paper is not None
        assert paper.references == []

    def test_references_empty_when_reference_list_has_no_dois(self) -> None:
        """Paper with references that all lack DOIs has an empty references list."""
        work = {
            **_MINIMAL_WORK,
            "reference": [
                {"key": "r1", "unstructured": "Some citation without DOI"},
                {"key": "r2"},
            ],
        }
        paper = CrossRefConnector._build_paper(work)
        assert paper is not None
        assert paper.references == []


# ---------------------------------------------------------------------------
# fetch_crossref_work
# ---------------------------------------------------------------------------


class TestCrossRefConnector:
    """Tests for the CrossRefConnector class."""

    def setup_method(self) -> None:
        """Create a fresh connector for each test."""
        self.connector = CrossRefConnector()

    def test_name(self) -> None:
        """Connector name is 'crossref'."""
        assert self.connector.name == "crossref"

    def test_min_request_interval(self) -> None:
        """Minimum request interval is a positive float."""
        assert self.connector.min_request_interval > 0

    def test_successful_fetch(self) -> None:
        """Successful API call returns the message dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "message": _FULL_WORK,
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b"{}"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        self.connector._http_session = mock_session

        result = self.connector.fetch_work("10.1038/nature12373")

        assert result == _FULL_WORK
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert "10.1038%2Fnature12373" in call_args[0][0] or "nature12373" in call_args[0][0]

    def test_404_returns_none(self) -> None:
        """404 response returns None without raising."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b"{}"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        self.connector._http_session = mock_session

        result = self.connector.fetch_work("10.9999/nonexistent")

        assert result is None

    def test_server_error_raises(self) -> None:
        """Non-404 HTTP errors propagate as exceptions."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server error")
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b"{}"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        self.connector._http_session = mock_session

        with pytest.raises(Exception, match="Server error"):
            self.connector.fetch_work("10.1234/error")

    def test_no_user_agent_header_sent(self) -> None:
        """CrossRef requests do not include a User-Agent header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "message": {}}
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b"{}"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        self.connector._http_session = mock_session

        self.connector.fetch_work("10.1234/test")

        headers = mock_session.get.call_args[1].get("headers") or {}
        assert "User-Agent" not in headers

    def test_build_paper_delegates(self) -> None:
        """build_paper delegates to _build_paper."""
        paper = self.connector.build_paper(_FULL_WORK)
        assert paper is not None
        assert paper.title == "Deep Learning for Natural Language Processing"


# ---------------------------------------------------------------------------
# Real-data fixture tests — validate parsing against collected CrossRef records
# ---------------------------------------------------------------------------


class TestBuildPaperFromRealData:
    """Validate CrossRefConnector._build_paper against real CrossRef API responses.

    These tests use fixtures collected from the live API via
    ``tests/data/crossref/collect_sample.py``.  Every record was returned by
    CrossRef and stored in ``sample_responses.json``.
    """

    @pytest.fixture(autouse=True)
    def _fixtures(self, crossref_sample_json) -> None:
        """Load the real CrossRef fixtures once per test class."""
        self.data = crossref_sample_json

    # -- Nature journal article (10.1038/nature12373) -----------------------

    def test_nature_title(self) -> None:
        """Nature article title is parsed correctly."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert "Higgs boson" in paper.title or len(paper.title) > 0

    def test_nature_authors(self) -> None:
        """Nature article has multiple real authors."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert len(paper.authors) >= 2

    def test_nature_source_is_journal(self) -> None:
        """Nature article source type is JOURNAL."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL
        assert "Nature" in paper.source.title

    def test_nature_has_issn(self) -> None:
        """Nature source has an ISSN."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.issn is not None

    def test_nature_has_citations(self) -> None:
        """Nature article has a positive citation count."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert paper.citations is not None
        assert paper.citations > 0

    def test_nature_has_pages(self) -> None:
        """Nature article has a page range."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert paper.page_range is not None

    def test_nature_has_publication_date(self) -> None:
        """Nature article has a publication date."""
        paper = CrossRefConnector._build_paper(self.data["10.1038/nature12373"])
        assert paper is not None
        assert paper.publication_date is not None
        assert paper.publication_date.year >= 2013

    # -- ACM KDD proceedings article (10.1145/3292500.3330648) --------------

    def test_kdd_source_is_conference(self) -> None:
        """ACM KDD proceedings-article maps to CONFERENCE source type."""
        paper = CrossRefConnector._build_paper(self.data["10.1145/3292500.3330648"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_kdd_has_doi(self) -> None:
        """KDD paper has the correct DOI."""
        paper = CrossRefConnector._build_paper(self.data["10.1145/3292500.3330648"])
        assert paper is not None
        assert paper.doi == "10.1145/3292500.3330648"

    # -- DETR book chapter (10.1007/978-3-030-58452-8_13) -------------------

    def test_detr_source_is_book(self) -> None:
        """DETR book-chapter maps to BOOK source type."""
        paper = CrossRefConnector._build_paper(self.data["10.1007/978-3-030-58452-8_13"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_detr_has_isbn(self) -> None:
        """Book chapter source has an ISBN."""
        paper = CrossRefConnector._build_paper(self.data["10.1007/978-3-030-58452-8_13"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.isbn is not None

    def test_detr_has_pages(self) -> None:
        """Book chapter has page numbers."""
        paper = CrossRefConnector._build_paper(self.data["10.1007/978-3-030-58452-8_13"])
        assert paper is not None
        assert paper.page_range is not None

    # -- ResNet CVPR proceedings article (10.1109/CVPR.2016.90) -------------

    def test_resnet_title(self) -> None:
        """ResNet paper title contains 'Residual'."""
        paper = CrossRefConnector._build_paper(self.data["10.1109/CVPR.2016.90"])
        assert paper is not None
        assert "Residual" in paper.title

    def test_resnet_is_conference(self) -> None:
        """ResNet paper source type is CONFERENCE."""
        paper = CrossRefConnector._build_paper(self.data["10.1109/CVPR.2016.90"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_resnet_has_authors(self) -> None:
        """ResNet paper has authors."""
        paper = CrossRefConnector._build_paper(self.data["10.1109/CVPR.2016.90"])
        assert paper is not None
        assert len(paper.authors) >= 2

    def test_resnet_high_citations(self) -> None:
        """ResNet paper has a very high citation count."""
        paper = CrossRefConnector._build_paper(self.data["10.1109/CVPR.2016.90"])
        assert paper is not None
        assert paper.citations is not None
        assert paper.citations > 1000

    # -- Springer BRM with JATS abstract (10.3758/s13428-022-02028-7) -------

    def test_springer_abstract_stripped(self) -> None:
        """Real CrossRef abstract with JATS tags is properly cleaned."""
        work = self.data["10.3758/s13428-022-02028-7"]
        raw = work.get("abstract", "")
        paper = CrossRefConnector._build_paper(work)
        assert paper is not None
        # The raw record has JATS tags; the parsed paper should not.
        if "<jats:" in raw:
            assert "<jats:" not in paper.abstract
        assert len(paper.abstract) > 0

    def test_springer_has_pdf_url(self) -> None:
        """Springer BRM record includes a PDF link."""
        paper = CrossRefConnector._build_paper(self.data["10.3758/s13428-022-02028-7"])
        assert paper is not None
        assert paper.pdf_url is not None
        assert paper.pdf_url.startswith("http")

    # -- PLOS ONE journal article (10.1371/journal.pone.0185542) ------------

    def test_plos_source_is_journal(self) -> None:
        """PLOS ONE article source type is JOURNAL."""
        paper = CrossRefConnector._build_paper(self.data["10.1371/journal.pone.0185542"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    # -- IEEE Access (10.1109/ACCESS.2021.3119621) --------------------------

    def test_ieee_has_issn(self) -> None:
        """IEEE Access article source has an ISSN."""
        paper = CrossRefConnector._build_paper(self.data["10.1109/ACCESS.2021.3119621"])
        assert paper is not None
        assert paper.source is not None
        assert paper.source.issn is not None

    # -- Elsevier (10.1016/j.apenergy.2023.121323) -------------------------

    def test_elsevier_has_pages(self) -> None:
        """Elsevier article has page field."""
        paper = CrossRefConnector._build_paper(self.data["10.1016/j.apenergy.2023.121323"])
        assert paper is not None
        assert paper.page_range is not None

    # -- Generic checks across ALL collected records ------------------------

    def test_all_records_build_successfully(self) -> None:
        """Every collected record produces a non-None Paper."""
        for doi, work in self.data.items():
            paper = CrossRefConnector._build_paper(work)
            assert paper is not None, f"CrossRefConnector._build_paper returned None for {doi}"

    def test_all_records_have_title(self) -> None:
        """Every collected record produces a paper with a non-empty title."""
        for doi, work in self.data.items():
            paper = CrossRefConnector._build_paper(work)
            assert paper is not None
            assert paper.title, f"Empty title for {doi}"

    def test_all_records_have_doi(self) -> None:
        """Every collected record preserves the DOI."""
        for doi, work in self.data.items():
            paper = CrossRefConnector._build_paper(work)
            assert paper is not None
            # DOIs are case-insensitive; CrossRef may normalise casing.
            assert paper.doi is not None, f"Missing DOI for {doi}"
            assert paper.doi.lower() == doi.lower(), f"DOI mismatch for {doi}"

    def test_all_records_have_publication_date(self) -> None:
        """Every collected record has a parseable publication date."""
        for doi, work in self.data.items():
            paper = CrossRefConnector._build_paper(work)
            assert paper is not None
            assert paper.publication_date is not None, f"Missing publication_date for {doi}"

    def test_all_records_have_source(self) -> None:
        """Every collected record produces a Paper with a Source."""
        for doi, work in self.data.items():
            paper = CrossRefConnector._build_paper(work)
            assert paper is not None
            assert paper.source is not None, f"Missing source for {doi}"
