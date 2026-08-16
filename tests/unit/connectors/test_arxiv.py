"""Unit tests for ArxivConnector."""

from __future__ import annotations

import datetime
import logging
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest
import requests

from findpapers.connectors.arxiv import _NS, ArxivConnector, _infer_source_type_from_journal_ref
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.exceptions import UnsupportedQueryError
from findpapers.query.builders.arxiv import ArxivQueryBuilder


def _make_arxiv_feed(n: int, total: int) -> str:
    """Build a minimal synthetic arXiv Atom feed with *n* entries."""
    entries = "".join(
        f"""<entry>
            <id>http://arxiv.org/abs/2301.0000{i}v1</id>
            <title>Synthetic Paper {i}</title>
            <updated>2023-01-01T00:00:00Z</updated>
            <published>2023-01-01T00:00:00Z</published>
            <summary>Synthetic abstract {i}.</summary>
            <author><name>Author {i}</name></author>
        </entry>"""
        for i in range(n)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
        <opensearch:totalResults>{total}</opensearch:totalResults>
        {entries}
    </feed>"""


class TestArxivConnectorInit:
    """Tests for ArxivConnector initialisation."""

    def test_default_builder_created(self):
        """Connector creates ArxivQueryBuilder when none provided."""
        searcher = ArxivConnector()
        assert isinstance(searcher.query_builder, ArxivQueryBuilder)

    def test_custom_builder_used(self):
        """Connector uses the provided builder."""
        builder = ArxivQueryBuilder()
        searcher = ArxivConnector(query_builder=builder)
        assert searcher.query_builder is builder

    def test_name(self):
        """Connector name is 'arXiv'."""
        assert ArxivConnector().name == Database.ARXIV


class TestArxivConnectorParseResponse:
    """Tests for response parsing."""

    def test_parse_sample_xml(self, arxiv_sample_xml, simple_query):
        """Parsing sample XML returns non-empty list of papers."""
        tree = ET.fromstring(arxiv_sample_xml)
        entries = tree.findall("atom:entry", _NS)
        assert len(entries) > 0

        papers = [ArxivConnector()._parse_paper(e) for e in entries]
        valid_papers = [p for p in papers if p is not None]
        assert len(valid_papers) > 0

    def test_parsed_paper_has_database_tag(self, arxiv_sample_xml):
        """Papers parsed from arXiv have 'arXiv' in databases set."""
        tree = ET.fromstring(arxiv_sample_xml)
        entries = tree.findall("atom:entry", _NS)
        paper = ArxivConnector()._parse_paper(entries[0])
        assert paper is not None
        assert Database.ARXIV in paper.found_in

    def test_missing_title_returns_none(self):
        """Entry without title returns None."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom">
            <title>  </title>
            <summary>some abstract</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        assert ArxivConnector()._parse_paper(entry) is None

    def test_comments_extracted_from_entry(self):
        """Comments field is populated when arxiv:comment element is present."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Some Paper</title>
            <summary>Abstract text here.</summary>
            <arxiv:comment>39 pages, 14 figures</arxiv:comment>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.comments == "39 pages, 14 figures"

    def test_comments_none_when_absent(self):
        """Comments field is None when arxiv:comment element is missing."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Some Paper</title>
            <summary>Abstract text here.</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.comments is None

    def test_sample_xml_has_papers_with_comments(self, arxiv_sample_xml):
        """Parsing the sample XML finds at least one paper with a non-None comment."""
        tree = ET.fromstring(arxiv_sample_xml)
        entries = tree.findall("atom:entry", _NS)
        papers = [ArxivConnector()._parse_paper(e) for e in entries]
        valid = [p for p in papers if p is not None]
        papers_with_comments = [p for p in valid if p.comments is not None]
        assert len(papers_with_comments) > 0

    def test_preprint_without_journal_ref_gets_repository_source(self):
        """Paper without journal_ref gets Source(title='arXiv', type=REPOSITORY)."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Some Preprint</title>
            <summary>Abstract text here.</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "arXiv"
        assert paper.source.source_type == SourceType.REPOSITORY

    def test_paper_with_journal_ref_infers_source_type(self):
        """Paper with journal_ref containing 'Physics' has source_type inferred."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Published Paper</title>
            <summary>Abstract text here.</summary>
            <arxiv:journal_ref>Phys. Rev. Lett. 123, 456 (2020)</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Phys. Rev. Lett. 123, 456 (2020)"
        assert paper.source.source_type == SourceType.JOURNAL

    def test_journal_ref_conference_inferred(self):
        """journal_ref with 'Proceedings' is classified as CONFERENCE."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Conf Paper</title>
            <summary>Abstract.</summary>
            <arxiv:journal_ref>Proceedings of NeurIPS 2023</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_journal_ref_workshop_inferred(self):
        """journal_ref with 'Workshop' is classified as CONFERENCE."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>WS Paper</title>
            <summary>Abstract.</summary>
            <arxiv:journal_ref>Workshop on ML 2022</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_journal_ref_book_inferred(self):
        """journal_ref with 'Lecture Notes' is classified as BOOK."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>LN Paper</title>
            <summary>Abstract.</summary>
            <arxiv:journal_ref>Lecture Notes in Computer Science vol. 1234</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_journal_ref_no_match_leaves_none(self):
        """journal_ref that doesn't match any heuristic leaves source_type None."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Published Paper</title>
            <summary>Abstract text here.</summary>
            <arxiv:journal_ref>Nature 580, 321 (2020)</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature 580, 321 (2020)"
        assert paper.source.source_type is None

    def test_paper_type_unpublished_for_preprint(self):
        """arXiv preprint without journal_ref gets PaperType.UNPUBLISHED."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Preprint Paper</title>
            <summary>Abstract.</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.UNPUBLISHED

    def test_paper_type_article_for_journal_ref(self):
        """arXiv paper with journal source_type gets PaperType.ARTICLE."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Published Paper</title>
            <summary>Abstract.</summary>
            <arxiv:journal_ref>Phys. Rev. Lett. 123 (2020)</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_inproceedings_for_conference_ref(self):
        """arXiv paper with conference source_type gets PaperType.INPROCEEDINGS."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Conf Paper</title>
            <summary>Abstract.</summary>
            <arxiv:journal_ref>Proceedings of NeurIPS 2023</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.INPROCEEDINGS

    def test_paper_type_inbook_for_book_ref(self):
        """arXiv paper with book source_type gets PaperType.INBOOK."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>LN Paper</title>
            <summary>Abstract.</summary>
            <arxiv:journal_ref>Lecture Notes in Computer Science vol. 1234</arxiv:journal_ref>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.paper_type is PaperType.INBOOK

    def test_doi_derived_from_entry_id_when_absent(self):
        """When <arxiv:doi> is absent, DOI is derived from <id> as 10.48550/arXiv.<id>."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Attention Is All You Need</title>
            <summary>Abstract text here.</summary>
            <id>http://arxiv.org/abs/1706.03762v5</id>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.doi == "10.48550/arXiv.1706.03762"

    def test_explicit_doi_takes_priority_over_derived(self):
        """When <arxiv:doi> is present, it is used instead of deriving from <id>."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Published Paper</title>
            <summary>Abstract text here.</summary>
            <id>http://arxiv.org/abs/2301.12345v1</id>
            <arxiv:doi>10.1145/3531146.3533206</arxiv:doi>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.doi == "10.1145/3531146.3533206"

    def test_doi_none_when_no_id_and_no_explicit_doi(self):
        """DOI is None when neither <arxiv:doi> nor a parseable <id> is present."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>Minimal Paper</title>
            <summary>Abstract text here.</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.doi is None


class TestInferSourceTypeFromJournalRef:
    """Tests for _infer_source_type_from_journal_ref heuristic."""

    @pytest.mark.parametrize(
        "text",
        [
            "Phys. Rev. Lett. 123, 456 (2020)",
            "J. High Energy Phys. 2021 (2021) 042",
            "Astrophysical Journal Letters 900, L1 (2020)",
            "IEEE Transactions on Neural Networks 32 (2021)",
            "Annals of Mathematics 192 (2020)",
            "Physical Review D 101, 054001 (2020)",
            "Bulletin of the AMS 57 (2020)",
        ],
    )
    def test_journal_patterns(self, text: str) -> None:
        """Common journal reference formats are classified as JOURNAL."""
        assert _infer_source_type_from_journal_ref(text) == SourceType.JOURNAL

    @pytest.mark.parametrize(
        "text",
        [
            "Proceedings of NeurIPS 2023",
            "Proc. IEEE CVPR 2022",
            "International Conference on Machine Learning (ICML 2021)",
            "Conf. on Computer Vision 2019",
            "Workshop on Representation Learning 2023",
            "Symposium on Foundations of Computer Science 2020",
            "Symp. on Theory of Computing 2019",
        ],
    )
    def test_conference_patterns(self, text: str) -> None:
        """Conference-related journal_ref formats are classified as CONFERENCE."""
        assert _infer_source_type_from_journal_ref(text) == SourceType.CONFERENCE

    @pytest.mark.parametrize(
        "text",
        [
            "Lecture Notes in Computer Science vol. 12345",
            "Lecture Notes in Mathematics 2456, Springer",
            "Chapter 5 in Advances in Neural Information Processing",
            "In: Book of Abstracts (unlikely but tests the pattern)",
        ],
    )
    def test_book_patterns(self, text: str) -> None:
        """Book-related journal_ref formats are classified as BOOK."""
        assert _infer_source_type_from_journal_ref(text) == SourceType.BOOK

    @pytest.mark.parametrize(
        "text",
        [
            "Nature 580, 321 (2020)",
            "Science 370, 1234 (2020)",
            "JHEP 05 (2021) 123",
            "Commun. Math. Phys. 380, 1 (2020)",
            "Nuclear Physics B 960 (2020) 115190",
            "Monthly Notices of the Royal Astronomical Society 500 (2021)",
        ],
    )
    def test_no_match_returns_none(self, text: str) -> None:
        """Refs that don't match any heuristic return None."""
        assert _infer_source_type_from_journal_ref(text) is None

    def test_conference_takes_priority_over_journal(self) -> None:
        """When text contains both conference and journal keywords, CONFERENCE wins."""
        text = "Proceedings of the Annual Review Conference 2022"
        assert _infer_source_type_from_journal_ref(text) == SourceType.CONFERENCE


class TestArxivConnectorSearch:
    """Tests for the search() method with mocked HTTP calls."""

    def test_search_raises_on_invalid_query(self, key_query):
        """Search raises UnsupportedQueryError when query uses unsupported filter (key)."""
        searcher = ArxivConnector()
        with pytest.raises(UnsupportedQueryError):
            searcher.search(key_query)

    def test_search_returns_papers_from_xml(self, simple_query, arxiv_sample_xml, mock_response):
        """Search parses XML response and returns papers."""
        searcher = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query, max_papers=5)

        assert len(papers) <= 5
        assert all(Database.ARXIV in p.found_in for p in papers)

    def test_max_papers_respected(self, simple_query, arxiv_sample_xml, mock_response):
        """search() returns no more than max_papers papers."""
        searcher = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query, max_papers=3)

        assert len(papers) <= 3

    def test_progress_callback_called(self, simple_query, arxiv_sample_xml, mock_response):
        """search() invokes progress_callback during pagination."""
        searcher = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        callback_calls = []

        def _callback(current, total):
            callback_calls.append((current, total))

        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response
        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, progress_callback=_callback)

        assert len(callback_calls) > 0

    def test_http_error_returns_empty(self, simple_query, mock_response):
        """search() returns empty list when HTTP request fails."""
        searcher = ArxivConnector()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = requests.HTTPError("500")
        with patch.object(searcher, "_rate_limit"):
            papers = searcher.search(simple_query)

        assert papers == []

    def test_http_error_logs_progress_context(self, simple_query, caplog):
        """A failed request logs how many papers were retrieved so far, at WARNING."""
        searcher = ArxivConnector()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = requests.HTTPError("500")
        with (
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.arxiv"),
        ):
            searcher.search(simple_query)

        assert any("search stopped early" in m for m in caplog.messages)

    def test_empty_entries_before_total_logs_warning(self, simple_query, mock_response, caplog):
        """Entries running out before the reported total logs a pagination-limit warning."""
        full_page = mock_response(text=_make_arxiv_feed(100, total=150))
        full_page.raise_for_status = MagicMock()
        empty_page = mock_response(text=_make_arxiv_feed(0, total=150))
        empty_page.raise_for_status = MagicMock()

        searcher = ArxivConnector()
        searcher._http_session = MagicMock()
        searcher._http_session.get.side_effect = [full_page, empty_page]

        with (
            patch.object(searcher, "_rate_limit"),
            caplog.at_level(logging.WARNING, logger="findpapers.connectors.arxiv"),
        ):
            searcher.search(simple_query)

        assert any("pagination limit" in m for m in caplog.messages)

    def test_since_until_appended_to_query(self, simple_query, arxiv_sample_xml, mock_response):
        """search() appends submittedDate range when since/until are given."""
        searcher = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        since = datetime.date(2023, 1, 15)
        until = datetime.date(2023, 12, 31)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since, until=until)

        call_args = searcher._http_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        search_query = params.get("search_query", "")
        assert "submittedDate:[202301150000 TO 202312312359]" in search_query
        # The date filter must be joined with " AND " (spaces, not "+")
        # so that requests encodes it correctly for the arXiv API.
        assert " AND submittedDate:" in search_query

    def test_since_only_uses_open_end(self, simple_query, arxiv_sample_xml, mock_response):
        """search() with only `since` uses a far-future end date."""
        searcher = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        since = datetime.date(2020, 6, 1)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, since=since)

        call_args = searcher._http_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        search_query = params.get("search_query", "")
        assert "submittedDate:[202006010000 TO 999912312359]" in search_query

    def test_until_only_uses_open_start(self, simple_query, arxiv_sample_xml, mock_response):
        """search() with only `until` uses a far-past start date."""
        searcher = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        searcher._http_session = MagicMock()
        searcher._http_session.get.return_value = response

        until = datetime.date(2022, 3, 15)

        with patch.object(searcher, "_rate_limit"):
            searcher.search(simple_query, max_papers=5, until=until)

        call_args = searcher._http_session.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        search_query = params.get("search_query", "")
        assert "submittedDate:[199101010000 TO 202203152359]" in search_query


class TestArxivConnectorFieldsOfStudyAndSubjects:
    """Tests for fields_of_study and subjects extraction from arXiv categories."""

    def test_categories_extracted_as_fields_and_subjects(self):
        """arXiv categories populate fields_of_study and subjects."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>A Paper About AI</title>
            <summary>Abstract.</summary>
            <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
            <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
            <category term="math.OC" scheme="http://arxiv.org/schemas/atom"/>
            <arxiv:primary_category term="cs.AI"/>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert "Computer Science" in paper.fields_of_study
        assert "Mathematics" in paper.fields_of_study
        assert "Artificial Intelligence" in paper.subjects
        assert "Machine Learning" in paper.subjects
        assert "Optimization and Control" in paper.subjects

    def test_no_categories_empty_sets(self):
        """Paper without categories has empty fields_of_study and subjects."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>A Paper</title>
            <summary>Abstract.</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.fields_of_study == set()
        assert paper.subjects == set()

    def test_sample_xml_has_fields_of_study(self, arxiv_sample_xml):
        """Papers parsed from sample XML have non-empty fields_of_study."""
        tree = ET.fromstring(arxiv_sample_xml)
        entries = tree.findall("atom:entry", _NS)
        papers = [ArxivConnector()._parse_paper(e) for e in entries]
        valid_papers = [p for p in papers if p is not None]
        papers_with_fos = [p for p in valid_papers if p.fields_of_study]
        assert len(papers_with_fos) > 0

    def test_is_open_access_always_true(self):
        """All arXiv papers are marked as open access."""
        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom"
               xmlns:arxiv="http://arxiv.org/schemas/atom">
            <title>A Paper</title>
            <summary>Abstract.</summary>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        paper = ArxivConnector()._parse_paper(entry)
        assert paper is not None
        assert paper.is_open_access is True

    def test_sample_xml_all_open_access(self, arxiv_sample_xml):
        """Every paper parsed from sample XML has is_open_access=True."""
        tree = ET.fromstring(arxiv_sample_xml)
        entries = tree.findall("atom:entry", _NS)
        papers = [ArxivConnector()._parse_paper(e) for e in entries]
        valid_papers = [p for p in papers if p is not None]
        assert all(p.is_open_access is True for p in valid_papers)


class TestArxivConnectorFetchPaperById:
    """Tests for fetch_paper_by_id."""

    def test_fetch_paper_by_id_returns_paper(self, arxiv_sample_xml, mock_response):
        """fetch_paper_by_id returns a Paper when the API responds with a valid entry."""
        connector = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = response

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_id("1706.03762")

        assert paper is not None

    def test_fetch_paper_by_id_returns_none_on_empty_response(self, mock_response):
        """fetch_paper_by_id returns None when the API returns no entries."""
        empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>"""
        connector = ArxivConnector()
        response = mock_response(text=empty_xml)
        response.raise_for_status = MagicMock()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = response

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("9999.99999")

        assert result is None

    def test_fetch_paper_by_id_returns_none_on_request_error(self):
        """fetch_paper_by_id returns None when the HTTP request fails."""
        connector = ArxivConnector()
        connector._http_session = MagicMock()
        connector._http_session.get.side_effect = requests.RequestException("timeout")

        with patch.object(connector, "_rate_limit"):
            result = connector.fetch_paper_by_id("1706.03762")

        assert result is None


class TestArxivConnectorURLPattern:
    """Tests for url_pattern and fetch_paper_by_url."""

    @pytest.mark.parametrize(
        ("url", "expected_id"),
        [
            ("https://arxiv.org/abs/1706.03762", "1706.03762"),
            ("https://arxiv.org/abs/1706.03762v5", "1706.03762"),
            ("https://arxiv.org/pdf/2301.12345", "2301.12345"),
            ("http://arxiv.org/abs/2301.12345v1", "2301.12345"),
        ],
    )
    def test_url_pattern_matches_arxiv_urls(self, url: str, expected_id: str) -> None:
        """url_pattern matches arXiv abstract and PDF URLs."""
        connector = ArxivConnector()
        match = connector.url_pattern.search(url)
        assert match is not None
        assert match.group(1) == expected_id

    def test_url_pattern_does_not_match_non_arxiv_url(self) -> None:
        """url_pattern returns None for non-arXiv URLs."""
        connector = ArxivConnector()
        assert connector.url_pattern.search("https://pubmed.ncbi.nlm.nih.gov/12345") is None

    def test_fetch_paper_by_url_delegates_to_fetch_paper_by_id(
        self, arxiv_sample_xml, mock_response
    ) -> None:
        """fetch_paper_by_url extracts the arXiv ID and delegates to fetch_paper_by_id."""
        connector = ArxivConnector()
        response = mock_response(text=arxiv_sample_xml)
        response.raise_for_status = MagicMock()
        connector._http_session = MagicMock()
        connector._http_session.get.return_value = response

        with patch.object(connector, "_rate_limit"):
            paper = connector.fetch_paper_by_url("https://arxiv.org/abs/1706.03762")

        assert paper is not None
        # Verify the correct API parameter was sent (id_list should match the extracted ID).
        call_kwargs = connector._http_session.get.call_args
        assert "1706.03762" in str(call_kwargs)

    def test_fetch_paper_by_url_returns_none_for_unrecognised_url(self) -> None:
        """fetch_paper_by_url returns None when the URL is not an arXiv URL."""
        connector = ArxivConnector()
        result = connector.fetch_paper_by_url("https://ieeexplore.ieee.org/document/9413133")
        assert result is None
