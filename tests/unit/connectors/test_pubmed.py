"""Unit tests for PubmedConnector."""

from __future__ import annotations

import datetime
import logging
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest
import requests

from findpapers.connectors.pubmed import (
    _MIN_REQUEST_INTERVAL_DEFAULT,
    _MIN_REQUEST_INTERVAL_WITH_KEY,
    PubmedConnector,
    _normalize_month,
    _parse_date_element,
)
from findpapers.core.author import Author
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.exceptions import UnsupportedQueryError
from findpapers.query.builders.pubmed import PubmedQueryBuilder
from findpapers.query.parser import QueryParser
from findpapers.query.propagator import FilterPropagator


class TestNormalizeMonth:
    """Tests for _normalize_month helper."""

    def test_numeric_month_padded(self):
        """Numeric month string is zero-padded."""
        assert _normalize_month("3") == "03"
        assert _normalize_month("12") == "12"

    def test_abbreviated_name_jan(self):
        """'Jan' maps to '01'."""
        assert _normalize_month("Jan") == "01"

    def test_abbreviated_name_dec(self):
        """'Dec' maps to '12'."""
        assert _normalize_month("Dec") == "12"

    def test_case_insensitive(self):
        """Month names are case-insensitive."""
        assert _normalize_month("JAN") == "01"
        assert _normalize_month("jan") == "01"

    def test_invalid_returns_01(self):
        """Non-numeric, non-abbreviated input returns '01'."""
        assert _normalize_month("Spring") == "01"


class TestParseDateElement:
    """Tests for _parse_date_element helper."""

    def test_full_date_with_numeric_month(self):
        """Element with Year, Month (numeric), Day returns correct date."""
        el = ET.fromstring("<PubDate><Year>2023</Year><Month>11</Month><Day>17</Day></PubDate>")
        assert _parse_date_element(el) == datetime.date(2023, 11, 17)

    def test_full_date_with_abbreviated_month(self):
        """Element with Year, abbreviated Month, Day returns correct date."""
        el = ET.fromstring("<PubDate><Year>2024</Year><Month>Dec</Month><Day>05</Day></PubDate>")
        assert _parse_date_element(el) == datetime.date(2024, 12, 5)

    def test_year_and_month_only(self):
        """Missing Day defaults to 01."""
        el = ET.fromstring("<PubDate><Year>2023</Year><Month>Mar</Month></PubDate>")
        assert _parse_date_element(el) == datetime.date(2023, 3, 1)

    def test_year_only(self):
        """Missing Month and Day default to 01."""
        el = ET.fromstring("<PubDate><Year>2022</Year></PubDate>")
        assert _parse_date_element(el) == datetime.date(2022, 1, 1)

    def test_missing_year_returns_none(self):
        """Element without Year returns None."""
        el = ET.fromstring("<PubDate><Month>03</Month></PubDate>")
        assert _parse_date_element(el) is None

    def test_empty_year_returns_none(self):
        """Element with empty Year text returns None."""
        el = ET.fromstring("<PubDate><Year>  </Year></PubDate>")
        assert _parse_date_element(el) is None

    def test_invalid_date_returns_none(self):
        """Unparseable date returns None (e.g. Feb 30)."""
        el = ET.fromstring("<PubDate><Year>2023</Year><Month>02</Month><Day>30</Day></PubDate>")
        assert _parse_date_element(el) is None


class TestPubmedConnectorInit:
    """Tests for PubmedConnector initialisation."""

    def test_default_builder_created(self):
        """Connector creates PubmedQueryBuilder when none provided."""
        searcher = PubmedConnector()
        assert isinstance(searcher.query_builder, PubmedQueryBuilder)

    def test_api_key_stored(self):
        """API key is stored on the instance."""
        searcher = PubmedConnector(api_key="test_key")
        assert searcher._api_key == "test_key"

    def test_warning_when_no_api_key(self, caplog):
        """A warning is logged when no API key is provided."""
        with caplog.at_level(logging.WARNING, logger="findpapers.connectors.pubmed"):
            PubmedConnector()
        assert any("No API key provided for PubMed" in msg for msg in caplog.messages)

    def test_no_warning_when_api_key_provided(self, caplog):
        """No warning is logged when an API key is provided."""
        with caplog.at_level(logging.WARNING, logger="findpapers.connectors.pubmed"):
            PubmedConnector(api_key="key")
        assert not any("No API key provided" in msg for msg in caplog.messages)

    def test_name(self):
        """Connector name is 'PubMed'."""
        assert PubmedConnector().name == Database.PUBMED

    def test_rate_interval_without_key(self):
        """Default rate interval is used when no API key provided."""
        searcher = PubmedConnector()
        assert searcher._request_interval == _MIN_REQUEST_INTERVAL_DEFAULT

    def test_rate_interval_with_key(self):
        """Faster rate interval used when API key is provided."""
        searcher = PubmedConnector(api_key="key")
        assert searcher._request_interval == _MIN_REQUEST_INTERVAL_WITH_KEY
        assert searcher._request_interval < _MIN_REQUEST_INTERVAL_DEFAULT


class TestPubmedConnectorParsePaper:
    """Tests for _parse_paper using real efetch XML data."""

    def test_parse_sample_xml(self, pubmed_efetch_xml):
        """Parsing sample efetch XML returns at least one valid paper."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        assert len(articles) > 0

        papers = [PubmedConnector()._parse_paper(a) for a in articles]
        valid = [p for p in papers if p is not None]
        assert len(valid) > 0

    def test_paper_has_database_tag(self, pubmed_efetch_xml):
        """Parsed paper has 'PubMed' in databases set."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        paper = PubmedConnector()._parse_paper(articles[0])
        assert paper is not None
        assert Database.PUBMED in paper.found_in

    def test_missing_title_returns_none(self):
        """Article element without title returns None."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>   </ArticleTitle>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        assert PubmedConnector()._parse_paper(el) is None

    def test_missing_medline_citation_returns_none(self):
        """Element without MedlineCitation returns None."""
        xml_str = "<PubmedArticle></PubmedArticle>"
        el = ET.fromstring(xml_str)
        assert PubmedConnector()._parse_paper(el) is None

    def test_author_with_initials_only(self):
        """Author with LastName + Initials (no ForeName) is parsed."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345</PMID>
                <Article>
                    <ArticleTitle>A Paper</ArticleTitle>
                    <AuthorList>
                        <Author>
                            <LastName>Smith</LastName>
                            <Initials>J</Initials>
                        </Author>
                    </AuthorList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.authors == [Author(name="J Smith")]

    def test_keywords_extracted(self):
        """Keywords and MeSH descriptors are collected."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>99</PMID>
                <Article>
                    <ArticleTitle>Test Paper</ArticleTitle>
                </Article>
                <KeywordList>
                    <Keyword>Deep Learning</Keyword>
                </KeywordList>
                <MeshHeadingList>
                    <MeshHeading>
                        <DescriptorName>Neural Networks, Computer</DescriptorName>
                    </MeshHeading>
                </MeshHeadingList>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.keywords is not None
        assert "Deep Learning" in paper.keywords
        assert "Neural Networks, Computer" in paper.keywords

    def test_doi_extracted(self):
        """DOI from ArticleId is extracted."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>55</PMID>
                <Article>
                    <ArticleTitle>DOI Paper</ArticleTitle>
                </Article>
            </MedlineCitation>
            <PubmedData>
                <ArticleIdList>
                    <ArticleId IdType="doi">10.1234/test</ArticleId>
                </ArticleIdList>
            </PubmedData>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.doi == "10.1234/test"

    def test_url_from_pmid(self):
        """URL is built from the PMID."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345</PMID>
                <Article>
                    <ArticleTitle>URL Paper</ArticleTitle>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.url == "https://pubmed.ncbi.nlm.nih.gov/12345/"

    def test_source_from_journal(self):
        """Source is built from Journal title and ISSN."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>1</PMID>
                <Article>
                    <ArticleTitle>Journal Paper</ArticleTitle>
                    <Journal>
                        <ISSN>1234-5678</ISSN>
                        <Title>Nature</Title>
                        <ISOAbbreviation>Nature</ISOAbbreviation>
                    </Journal>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature"
        assert paper.source.issn == "1234-5678"

    def test_source_type_is_always_journal(self):
        """PubMed sources always have source_type=JOURNAL."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>1</PMID>
                <Article>
                    <ArticleTitle>Journal Paper</ArticleTitle>
                    <Journal>
                        <Title>Some Journal</Title>
                    </Journal>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_pages_from_medline_pgn(self):
        """Pages are extracted from MedlinePgn in Pagination element."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>1</PMID>
                <Article>
                    <ArticleTitle>Test</ArticleTitle>
                    <Pagination>
                        <StartPage>100</StartPage>
                        <EndPage>115</EndPage>
                        <MedlinePgn>100-115</MedlinePgn>
                    </Pagination>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.page_range == "100-115"

    def test_pages_from_start_end_when_no_medline_pgn(self):
        """Pages are built from StartPage\u2013EndPage when MedlinePgn is absent."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>1</PMID>
                <Article>
                    <ArticleTitle>Test</ArticleTitle>
                    <Pagination>
                        <StartPage>200</StartPage>
                        <EndPage>210</EndPage>
                    </Pagination>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.page_range == "200\u2013210"

    def test_pages_from_sample_data(self, pubmed_efetch_xml):
        """Pages are extracted from the real PubMed sample data."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        paper = PubmedConnector()._parse_paper(articles[0])
        assert paper is not None
        assert paper.page_range is not None
        assert "1148" in paper.page_range

    def test_paper_type_journal_article(self):
        """Journal Article publication type maps to PaperType.ARTICLE."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Journal Article</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_congress(self):
        """Congress publication type maps to PaperType.INPROCEEDINGS."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Congress</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_meeting_abstract(self):
        """Meeting Abstract publication type maps to PaperType.INPROCEEDINGS."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Meeting Abstract</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_academic_dissertation(self):
        """Academic Dissertation maps to PaperType.PHDTHESIS."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Academic Dissertation</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.PHDTHESIS

    def test_paper_type_technical_report(self):
        """Technical Report maps to PaperType.TECHREPORT."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Technical Report</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.TECHREPORT

    def test_paper_type_preprint(self):
        """Preprint publication type maps to PaperType.UNPUBLISHED."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Preprint</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.UNPUBLISHED

    def test_paper_type_review_maps_to_article(self):
        """Review publication type maps to PaperType.ARTICLE."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Review</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_congress_takes_priority_over_journal_article(self):
        """When multiple pub types, more specific type wins by priority order."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Journal Article</PublicationType>
                        <PublicationType>Congress</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_none_when_no_publication_type(self):
        """No PublicationTypeList results in paper_type being None."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is None

    def test_paper_type_none_for_unrecognised_type(self):
        """Unrecognised publication type results in paper_type being None."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <PublicationTypeList>
                        <PublicationType>Letter</PublicationType>
                    </PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.paper_type is None

    def test_date_prefers_article_date_over_pubdate(self):
        """ArticleDate (electronic) is preferred over PubDate (print issue)."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>1</PMID>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <Journal>
                        <JournalIssue>
                            <PubDate>
                                <Year>2026</Year><Month>Mar</Month>
                            </PubDate>
                        </JournalIssue>
                    </Journal>
                    <ArticleDate DateType="Electronic">
                        <Year>2023</Year><Month>11</Month><Day>17</Day>
                    </ArticleDate>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.publication_date == datetime.date(2023, 11, 17)

    def test_date_falls_back_to_pubdate_when_no_article_date(self):
        """PubDate is used when ArticleDate is absent."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>2</PMID>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                    <Journal>
                        <JournalIssue>
                            <PubDate>
                                <Year>2024</Year><Month>Dec</Month>
                            </PubDate>
                        </JournalIssue>
                    </Journal>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.publication_date == datetime.date(2024, 12, 1)

    def test_date_none_when_no_date_elements(self):
        """Publication date is None when neither ArticleDate nor PubDate exist."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>3</PMID>
                <Article>
                    <ArticleTitle>T</ArticleTitle>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        el = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(el)
        assert paper is not None
        assert paper.publication_date is None

    def test_date_from_sample_data_uses_article_date(self, pubmed_efetch_xml):
        """First article in sample data has ArticleDate 2022-08-25, not PubDate 2024-Dec."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        paper = PubmedConnector()._parse_paper(articles[0])
        assert paper is not None
        # ArticleDate is 2022-08-25; PubDate is 2024-Dec
        assert paper.publication_date == datetime.date(2022, 8, 25)


class TestPubmedConnectorSearch:
    """Tests for search() with mocked HTTP calls."""

    def test_search_raises_for_question_mark_wildcard(self, wildcard_query):
        """Search raises UnsupportedQueryError for '?' wildcard (not supported by PubMed)."""
        # The wildcard_query uses 'machine*' which is valid (>= 4 chars).
        # Override with '?' test via a custom query.
        parser = QueryParser()
        propagator = FilterPropagator()
        q = propagator.propagate(parser.parse("[mac?]"))
        searcher = PubmedConnector()
        with pytest.raises(UnsupportedQueryError):
            searcher.search(q)

    def test_search_returns_papers(
        self,
        simple_query,
        pubmed_esearch_json,
        pubmed_efetch_xml,
        mock_response,
    ):
        """search() returns papers parsed from esearch + efetch responses."""
        searcher = PubmedConnector()
        esearch_mock = mock_response(json_data=pubmed_esearch_json)
        esearch_mock.raise_for_status = MagicMock()
        efetch_mock = mock_response(text=pubmed_efetch_xml)
        efetch_mock.raise_for_status = MagicMock()

        side_effects = [esearch_mock, efetch_mock]

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = side_effects
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query)

        assert len(papers) > 0
        assert all(Database.PUBMED in p.found_in for p in papers)

    def test_max_papers_respected(
        self,
        simple_query,
        pubmed_esearch_json,
        pubmed_efetch_xml,
        mock_response,
    ):
        """search() returns no more than max_papers papers."""
        searcher = PubmedConnector()
        esearch_mock = mock_response(json_data=pubmed_esearch_json)
        esearch_mock.raise_for_status = MagicMock()
        efetch_mock = mock_response(text=pubmed_efetch_xml)
        efetch_mock.raise_for_status = MagicMock()

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [esearch_mock, efetch_mock]
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query, max_papers=2)

        assert len(papers) <= 2

    def test_esearch_error_breaks_loop(self, simple_query):
        """Exception in _search_ids breaks the loop and returns empty list."""
        searcher = PubmedConnector()

        with patch.object(
            searcher, "_search_ids", side_effect=requests.RequestException("network error")
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_efetch_error_breaks_loop(self, simple_query, pubmed_esearch_json, mock_response):
        """Exception in _fetch_details breaks the loop."""
        searcher = PubmedConnector()
        esearch_mock = mock_response(json_data=pubmed_esearch_json)
        esearch_mock.raise_for_status = MagicMock()

        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = esearch_mock
        with (
            patch.object(
                searcher, "_fetch_details", side_effect=requests.RequestException("fetch error")
            ),
            patch.object(searcher, "_rate_limit"),
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_progress_callback_called(
        self,
        simple_query,
        pubmed_esearch_json,
        pubmed_efetch_xml,
        mock_response,
    ):
        """Progress callback is invoked after each page."""
        searcher = PubmedConnector()
        esearch_mock = mock_response(json_data=pubmed_esearch_json)
        esearch_mock.raise_for_status = MagicMock()
        efetch_mock = mock_response(text=pubmed_efetch_xml)
        efetch_mock.raise_for_status = MagicMock()
        callback = MagicMock()

        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [esearch_mock, efetch_mock]
        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, progress_callback=callback)

        callback.assert_called()

    def test_search_network_error_returns_empty_list(self, simple_query):
        """Network error in _fetch_papers is caught and returns an empty list."""
        searcher = PubmedConnector()

        with patch.object(
            searcher, "_fetch_papers", side_effect=requests.ConnectionError("network down")
        ):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_since_until_adds_date_params(
        self, simple_query, pubmed_esearch_json, pubmed_efetch_xml, mock_response
    ):
        """search() adds mindate/maxdate/datetype when since/until are given."""
        searcher = PubmedConnector()
        esearch_mock = mock_response(json_data=pubmed_esearch_json)
        esearch_mock.raise_for_status = MagicMock()
        efetch_mock = mock_response(text=pubmed_efetch_xml)
        efetch_mock.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [esearch_mock, efetch_mock]

        since = datetime.date(2022, 3, 1)
        until = datetime.date(2023, 9, 30)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        # The first call is the esearch; check its params for date filtering.
        esearch_call = searcher._http_session.get.call_args_list[0]
        params = esearch_call.kwargs.get("params") or esearch_call[1].get("params", {})
        assert params.get("datetype") == "pdat"
        assert params.get("mindate") == "2022/03/01"
        assert params.get("maxdate") == "2023/09/30"

    def test_pagination_uses_successful_paper_count(self, simple_query):
        """Pagination should use len(papers) not processed count.

        When some papers fail to parse, the connector should keep
        fetching until max_papers successfully parsed papers are found,
        rather than stopping based on the number of IDs processed.
        """
        searcher = PubmedConnector()

        # Page 1: returns 3 IDs but only 1 parses successfully.
        # Page 2: returns 3 IDs and 2 parse successfully => total = 3 >= max_papers.
        call_count = 0

        def fake_search_ids(
            query: str,
            offset: int,
            count: int,
            date_params: dict[str, str],
        ) -> tuple[list[str], int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (["id1", "id2", "id3"], 10)
            elif call_count == 2:
                return (["id4", "id5", "id6"], 10)
            return ([], 10)

        def fake_fetch_details(ids: list[str]) -> list[ET.Element]:
            # Return one element per ID (content doesn't matter here).
            return [ET.Element("PubmedArticle") for _ in ids]

        parse_results = iter(
            [
                MagicMock(),  # id1 -> success
                None,  # id2 -> parse failure
                None,  # id3 -> parse failure
                MagicMock(),  # id4 -> success
                MagicMock(),  # id5 -> success
                None,  # id6 -> parse failure
            ]
        )

        with (
            patch.object(searcher, "_search_ids", side_effect=fake_search_ids),
            patch.object(searcher, "_fetch_details", side_effect=fake_fetch_details),
            patch.object(searcher, "_parse_paper", side_effect=lambda el: next(parse_results)),
        ):
            papers = searcher.search(simple_query, max_papers=3)

        # Should have fetched 2 pages to reach 3 successfully parsed papers.
        assert call_count == 2
        assert len(papers) == 3


class TestPubmedSubjectsExtraction:
    """Tests for subjects extraction from MeSH headings."""

    def test_major_mesh_topics_as_subjects(self, pubmed_efetch_xml):
        """MeSH descriptors with MajorTopicYN='Y' are extracted as subjects."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        assert len(articles) > 0

        paper = PubmedConnector()._parse_paper(articles[0])
        assert paper is not None
        # The sample data has MeSH headings with MajorTopicYN="Y"
        assert len(paper.subjects) > 0

    def test_mesh_major_topic_inline_xml(self):
        """Inline XML with MeSH MajorTopicYN='Y' populates subjects."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345</PMID>
                <Article>
                    <Journal>
                        <Title>Test Journal</Title>
                        <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
                    </Journal>
                    <ArticleTitle>Test Paper</ArticleTitle>
                    <Abstract><AbstractText>An abstract.</AbstractText></Abstract>
                    <AuthorList><Author><LastName>Doe</LastName><ForeName>John</ForeName></Author></AuthorList>
                </Article>
                <MeshHeadingList>
                    <MeshHeading>
                        <DescriptorName MajorTopicYN="Y">Machine Learning</DescriptorName>
                    </MeshHeading>
                    <MeshHeading>
                        <DescriptorName MajorTopicYN="N">Humans</DescriptorName>
                    </MeshHeading>
                    <MeshHeading>
                        <DescriptorName MajorTopicYN="Y">Natural Language Processing</DescriptorName>
                    </MeshHeading>
                </MeshHeadingList>
            </MedlineCitation>
        </PubmedArticle>
        """
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert "Machine Learning" in paper.subjects
        assert "Natural Language Processing" in paper.subjects
        # Humans is MajorTopicYN="N", should NOT be in subjects
        assert "Humans" not in paper.subjects
        # But all descriptors should still be in keywords
        assert "Machine Learning" in paper.keywords
        assert "Humans" in paper.keywords


class TestPubmedLanguageExtraction:
    """Tests for language extraction from <Language> elements."""

    def test_language_eng_maps_to_en(self):
        """<Language>eng</Language> is normalised to 'en'."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>1</PMID>
                <Article>
                    <ArticleTitle>Sample</ArticleTitle>
                    <Language>eng</Language>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.language == "en"

    def test_language_por_maps_to_pt(self):
        """<Language>por</Language> is normalised to 'pt'."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>2</PMID>
                <Article>
                    <ArticleTitle>Amostra</ArticleTitle>
                    <Language>por</Language>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.language == "pt"

    def test_language_absent_is_none(self):
        """Papers without <Language> element have language=None."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>3</PMID>
                <Article>
                    <ArticleTitle>No Language</ArticleTitle>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.language is None

    def test_language_from_sample_xml(self, pubmed_efetch_xml):
        """Sample XML records (all 'eng') are normalised to 'en'."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        for article_el in articles:
            paper = PubmedConnector()._parse_paper(article_el)
            if paper is not None:
                # All sample records use 'eng'
                assert paper.language == "en", (
                    f"Expected 'en', got {paper.language!r} for {paper.title!r}"
                )


class TestPubmedIsRetractedExtraction:
    """Tests for is_retracted extraction from PubMed PublicationTypeList."""

    def _make_xml(self, pub_types: list[str], title: str = "Sample") -> str:
        """Build a minimal PubmedArticle XML string with the given PublicationTypes."""
        type_elements = "".join(
            f'<PublicationType UI="">{pt}</PublicationType>' for pt in pub_types
        )
        return f"""
        <PubmedArticle>
            <MedlineCitation>
                <PMID>99</PMID>
                <Article>
                    <ArticleTitle>{title}</ArticleTitle>
                    <PublicationTypeList>{type_elements}</PublicationTypeList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """

    def test_retracted_publication_sets_is_retracted_true(self):
        """'Retracted Publication' pub type yields is_retracted=True."""
        xml_str = self._make_xml(["Journal Article", "Retracted Publication"])
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.is_retracted is True

    def test_retraction_of_publication_does_not_set_is_retracted(self):
        """'Retraction of Publication' (the notice itself) does NOT yield is_retracted=True."""
        xml_str = self._make_xml(["Retraction of Publication"])
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.is_retracted is False

    def test_no_retraction_type_sets_is_retracted_false(self):
        """Normal paper without any retraction pub type yields is_retracted=False."""
        xml_str = self._make_xml(["Journal Article", "Research Support, Non-U.S. Gov't"])
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.is_retracted is False

    def test_empty_publication_type_list_sets_is_retracted_false(self):
        """Paper with an empty PublicationTypeList yields is_retracted=False."""
        xml_str = self._make_xml([])
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.is_retracted is False

    def test_is_retracted_from_sample_xml(self, pubmed_efetch_xml):
        """Sample XML records yield is_retracted as a bool (not None)."""
        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        for article_el in articles:
            paper = PubmedConnector()._parse_paper(article_el)
            if paper is not None:
                assert isinstance(paper.is_retracted, bool), (
                    f"Expected bool, got {paper.is_retracted!r} for {paper.title!r}"
                )


class TestPubmedFundersExtraction:
    """Tests for funders extraction from PubMed GrantList elements."""

    @staticmethod
    def _make_grant_xml(agencies: list[str], title: str = "Sample") -> str:
        """Build a minimal PubmedArticle XML string with the given grant agencies."""
        grant_elements = "".join(f"<Grant><Agency>{a}</Agency></Grant>" for a in agencies)
        grant_list = f"<GrantList>{grant_elements}</GrantList>" if agencies else ""
        return f"""
        <PubmedArticle>
            <MedlineCitation>
                <PMID>99</PMID>
                <Article>
                    <ArticleTitle>{title}</ArticleTitle>
                    {grant_list}
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """

    def test_funders_extracted_from_grant_agencies(self):
        """Agency names inside GrantList/Grant are collected into funders."""
        xml_str = self._make_grant_xml(["National Cancer Institute", "FAPESP"])
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.funders == {"National Cancer Institute", "FAPESP"}

    def test_funders_empty_when_no_grant_list(self):
        """Paper without GrantList has an empty funders set."""
        xml_str = self._make_grant_xml([])
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.funders == set()

    def test_funders_skips_blank_agency(self):
        """Grant entries with blank Agency text are skipped."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>99</PMID>
                <Article>
                    <ArticleTitle>Sample</ArticleTitle>
                    <GrantList>
                        <Grant><Agency>   </Agency></Grant>
                        <Grant><Agency>NIH</Agency></Grant>
                    </GrantList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.funders == {"NIH"}

    def test_funders_skips_grant_without_agency_element(self):
        """Grant entries without an Agency element are skipped."""
        xml_str = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>99</PMID>
                <Article>
                    <ArticleTitle>Sample</ArticleTitle>
                    <GrantList>
                        <Grant><GrantID>R01AA000</GrantID></Grant>
                        <Grant><Agency>Wellcome Trust</Agency></Grant>
                    </GrantList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """
        article = ET.fromstring(xml_str)
        paper = PubmedConnector()._parse_paper(article)
        assert paper is not None
        assert paper.funders == {"Wellcome Trust"}


class TestPubmedConnectorFetchPaperById:
    """Tests for fetch_paper_by_id."""

    def test_fetch_paper_by_id_returns_paper(self, pubmed_efetch_xml, mock_response):
        """fetch_paper_by_id returns a Paper when efetch responds with a valid record."""
        connector = PubmedConnector()
        efetch_mock = mock_response(text=pubmed_efetch_xml)
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = efetch_mock

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_id("12345678")

        assert paper is not None

    def test_fetch_paper_by_id_returns_none_on_empty_response(self, mock_response):
        """fetch_paper_by_id returns None when efetch returns no articles."""
        empty_xml = "<PubmedArticleSet></PubmedArticleSet>"
        connector = PubmedConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = mock_response(text=empty_xml)

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("99999999")

        assert result is None

    def test_fetch_paper_by_id_returns_none_on_request_error(self):
        """fetch_paper_by_id returns None when the HTTP request fails."""
        connector = PubmedConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = requests.RequestException("timeout")

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("12345678")

        assert result is None


class TestPubmedConnectorURLPattern:
    """Tests for url_pattern and fetch_paper_by_url."""

    @pytest.mark.parametrize(
        ("url", "expected_id"),
        [
            ("https://pubmed.ncbi.nlm.nih.gov/12345678", "12345678"),
            ("https://pubmed.ncbi.nlm.nih.gov/12345678/", "12345678"),
            ("https://www.ncbi.nlm.nih.gov/pubmed/99887766", "99887766"),
        ],
    )
    def test_url_pattern_matches_pubmed_urls(self, url: str, expected_id: str) -> None:
        """url_pattern matches PubMed landing-page URLs."""
        connector = PubmedConnector()
        match = connector.url_pattern.search(url)
        assert match is not None
        assert match.group(1) == expected_id

    def test_url_pattern_does_not_match_non_pubmed_url(self) -> None:
        """url_pattern returns None for non-PubMed URLs."""
        connector = PubmedConnector()
        assert connector.url_pattern.search("https://arxiv.org/abs/1706.03762") is None

    def test_fetch_paper_by_url_delegates_to_fetch_paper_by_id(
        self, pubmed_efetch_xml, mock_response
    ) -> None:
        """fetch_paper_by_url extracts the PMID and delegates to fetch_paper_by_id."""
        connector = PubmedConnector()
        efetch_mock = mock_response(text=pubmed_efetch_xml)
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = efetch_mock

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_url("https://pubmed.ncbi.nlm.nih.gov/12345678")

        assert paper is not None

    def test_fetch_paper_by_url_returns_none_for_unrecognised_url(self) -> None:
        """fetch_paper_by_url returns None when the URL is not a PubMed URL."""
        connector = PubmedConnector()
        result = connector.fetch_paper_by_url("https://arxiv.org/abs/1706.03762")
        assert result is None
