"""Unit tests for WosConnector."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from findpapers.connectors.wos import WosConnector, _extract_citation_count, _parse_wos_date
from findpapers.core.paper import Database, PaperType
from findpapers.core.source import SourceType
from findpapers.exceptions import MissingApiKeyError
from findpapers.query.builders.wos import WosQueryBuilder


class TestWosConnectorInit:
    """Tests for WosConnector initialisation."""

    def test_default_builder_created(self) -> None:
        """Connector creates WosQueryBuilder when none provided."""
        connector = WosConnector(api_key="dummy")
        assert isinstance(connector.query_builder, WosQueryBuilder)

    def test_api_key_stored(self) -> None:
        """API key is stored on the instance."""
        connector = WosConnector(api_key="test_key_123")
        assert connector._api_key == "test_key_123"

    def test_name_returns_wos_value(self) -> None:
        """Connector name is 'wos'."""
        assert WosConnector(api_key="dummy").name == Database.WOS.value

    def test_missing_api_key_raises(self) -> None:
        """Constructing without an API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError):
            WosConnector()

    def test_empty_api_key_raises(self) -> None:
        """Constructing with an empty API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError):
            WosConnector(api_key="")

    def test_blank_api_key_raises(self) -> None:
        """Constructing with a whitespace-only API key raises MissingApiKeyError."""
        with pytest.raises(MissingApiKeyError):
            WosConnector(api_key="   ")

    def test_min_request_interval(self) -> None:
        """Default request interval is 1.0 second (Free Trial rate limit)."""
        assert WosConnector(api_key="dummy").min_request_interval == 1.0

    def test_custom_builder_used(self) -> None:
        """A provided WosQueryBuilder instance is stored as-is."""
        custom_builder = WosQueryBuilder()
        connector = WosConnector(query_builder=custom_builder, api_key="dummy")
        assert connector.query_builder is custom_builder


class TestParsewosDate:
    """Tests for the private _parse_wos_date helper."""

    def test_year_only(self) -> None:
        """Year without month defaults to January 1st."""
        result = _parse_wos_date(2021, None)
        assert result == datetime.date(2021, 1, 1)

    def test_year_with_known_month(self) -> None:
        """Year + 'JUN' resolves to June 1st."""
        result = _parse_wos_date(2021, "JUN")
        assert result == datetime.date(2021, 6, 1)

    def test_season_spring(self) -> None:
        """'SPR' maps to April 1st."""
        result = _parse_wos_date(2020, "SPR")
        assert result == datetime.date(2020, 4, 1)

    def test_bimonthly_jan_feb(self) -> None:
        """'JAN-FEB' maps to January 1st."""
        result = _parse_wos_date(2019, "JAN-FEB")
        assert result == datetime.date(2019, 1, 1)

    def test_unknown_month_defaults_to_january(self) -> None:
        """Unrecognised month string falls back to January 1st."""
        result = _parse_wos_date(2018, "UNKNOWN")
        assert result == datetime.date(2018, 1, 1)

    def test_none_year_returns_none(self) -> None:
        """Missing year returns None."""
        assert _parse_wos_date(None, "JUN") is None

    def test_lowercase_month_normalised(self) -> None:
        """Lower-case month abbreviation is normalised correctly."""
        result = _parse_wos_date(2022, "oct")
        assert result == datetime.date(2022, 10, 1)


class TestExtractCitationCount:
    """Tests for the private _extract_citation_count helper."""

    def test_wos_db_count_returned(self) -> None:
        """Extracts count where db is 'WOS'."""
        result = _extract_citation_count([{"db": "WOS", "count": 42}])
        assert result == 42

    def test_none_when_empty(self) -> None:
        """Empty list returns None."""
        assert _extract_citation_count([]) is None

    def test_none_when_no_wos_entry(self) -> None:
        """Returns None when no WOS db entry exists."""
        result = _extract_citation_count([{"db": "OTHER", "count": 10}])
        assert result is None

    def test_case_insensitive_db_match(self) -> None:
        """DB field comparison is case-insensitive."""
        result = _extract_citation_count([{"db": "wos", "count": 7}])
        assert result == 7

    def test_string_count_converted_to_int(self) -> None:
        """String count value is converted to int."""
        result = _extract_citation_count([{"db": "WOS", "count": "100"}])
        assert result == 100

    def test_none_count_skipped(self) -> None:
        """Entry with count=None is skipped."""
        result = _extract_citation_count([{"db": "WOS", "count": None}])
        assert result is None


class TestWosParseDocument:
    """Tests for WosConnector._parse_document."""

    def test_parse_full_hit(self, wos_sample_json: dict) -> None:
        """Full first hit parses to a Paper with expected fields."""
        hit = wos_sample_json["hits"][0]
        connector = WosConnector(api_key="dummy")
        paper = connector._parse_document(hit)
        assert paper is not None
        assert paper.title == "On the Explainability of Natural Language Processing Deep Models"
        assert len(paper.authors) == 2
        assert paper.authors[0].name == "El Zini, Julia"
        assert paper.publication_date == datetime.date(2023, 6, 1)
        assert paper.doi == "10.1145/3529755"
        assert paper.citations == 77
        assert "NLP" in paper.keywords
        assert Database.WOS.value in paper.found_in

    def test_parse_sets_source(self, wos_sample_json: dict) -> None:
        """Source title and ISSN are extracted from the first hit."""
        hit = wos_sample_json["hits"][0]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "ACM COMPUTING SURVEYS"
        assert paper.source.issn == "0360-0300"
        assert paper.source.source_type == SourceType.JOURNAL

    def test_parse_page_range(self, wos_sample_json: dict) -> None:
        """Page range is extracted correctly from a hit that has one."""
        # hit[3] has pages.range="230-243" and pages.count=14
        hit = wos_sample_json["hits"][3]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.page_range == "230-243"
        assert paper.page_count == 14

    def test_parse_conference_source_type(self, wos_sample_json: dict) -> None:
        """Hit with sourceType 'Proceedings Paper' produces SourceType.CONFERENCE."""
        # hit[7] has sourceTypes=["Proceedings Paper"]
        hit = wos_sample_json["hits"][7]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_paper_type_article(self, wos_sample_json: dict) -> None:
        """First hit with type 'Article' maps to PaperType.ARTICLE."""
        hit = wos_sample_json["hits"][0]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.paper_type == PaperType.ARTICLE

    def test_paper_type_inproceedings(self, wos_sample_json: dict) -> None:
        """Hit with type 'Meeting' maps to PaperType.INPROCEEDINGS."""
        # hit[7] has types=["Meeting"] which is a conference/proceedings document
        hit = wos_sample_json["hits"][7]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.paper_type == PaperType.INPROCEEDINGS

    def test_missing_title_returns_none(self) -> None:
        """Document with empty title returns None."""
        paper = WosConnector(api_key="dummy")._parse_document({"title": ""})
        assert paper is None

    def test_absent_title_key_returns_none(self) -> None:
        """Document with no title key returns None."""
        paper = WosConnector(api_key="dummy")._parse_document({})
        assert paper is None

    def test_no_citations_when_empty(self) -> None:
        """Document with an empty citations list has citations=None."""
        doc = {"title": "Test Paper", "citations": []}
        paper = WosConnector(api_key="dummy")._parse_document(doc)
        assert paper is not None
        assert paper.citations is None

    def test_abstract_is_none(self, wos_sample_json: dict) -> None:
        """Starter API does not return abstracts; abstract field is empty."""
        hit = wos_sample_json["hits"][0]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.abstract == ""

    def test_url_from_record_link(self, wos_sample_json: dict) -> None:
        """Record URL is extracted from the links field."""
        hit = wos_sample_json["hits"][0]
        paper = WosConnector(api_key="dummy")._parse_document(hit)
        assert paper is not None
        assert paper.url is not None
        assert "webofscience.com" in paper.url


class TestWosFetchPaperByDoi:
    """Tests for WosConnector.fetch_paper_by_doi."""

    def test_successful_doi_lookup(self, wos_sample_json: dict, mock_response) -> None:
        """DOI lookup returns parsed Paper from first hit."""
        single_hit_response = {"hits": [wos_sample_json["hits"][0]]}
        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", return_value=mock_response(single_hit_response)):
            paper = connector.fetch_paper_by_doi("10.1145/3529755")
        assert paper is not None
        assert paper.doi == "10.1145/3529755"

    def test_doi_query_uses_do_prefix(self, wos_sample_json: dict, mock_response) -> None:
        """The DOI query uses 'DO=<doi>' field tag."""
        single_hit_response = {"hits": [wos_sample_json["hits"][0]]}
        connector = WosConnector(api_key="dummy")
        with patch.object(
            connector, "_get", return_value=mock_response(single_hit_response)
        ) as mock_get:
            connector.fetch_paper_by_doi("10.1038/nature14539")
        call_kwargs = mock_get.call_args
        params = (
            call_kwargs[1].get("params") or call_kwargs[0][1]
            if len(call_kwargs[0]) > 1
            else call_kwargs[1]["params"]
        )
        assert "DO=10.1038/nature14539" in params["q"]

    def test_empty_hits_returns_none(self, mock_response) -> None:
        """Empty hits list returns None."""
        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", return_value=mock_response({"hits": []})):
            assert connector.fetch_paper_by_doi("10.nonexistent/xyz") is None

    def test_request_exception_returns_none(self) -> None:
        """HTTP error during DOI lookup returns None."""
        import requests

        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", side_effect=requests.RequestException("timeout")):
            assert connector.fetch_paper_by_doi("10.failing/doi") is None


class TestWosFetchPaperById:
    """Tests for WosConnector.fetch_paper_by_id."""

    def test_successful_uid_lookup(self, wos_sample_json: dict, mock_response) -> None:
        """UID lookup calls /documents/{uid} and returns parsed Paper."""
        doc = wos_sample_json["hits"][0]
        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", return_value=mock_response(doc)) as mock_get:
            paper = connector.fetch_paper_by_id("WOS:000282418500002")
        assert paper is not None
        assert paper.title == "On the Explainability of Natural Language Processing Deep Models"
        called_url = mock_get.call_args[0][0]
        assert "WOS:000282418500002" in called_url

    def test_request_exception_returns_none(self) -> None:
        """HTTP error during UID lookup returns None."""
        import requests

        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", side_effect=requests.RequestException("error")):
            assert connector.fetch_paper_by_id("WOS:INVALID") is None


class TestWosFetchPapers:
    """Tests for WosConnector._fetch_papers."""

    def test_fetch_papers_returns_list(
        self,
        simple_query,
        wos_sample_json: dict,
        mock_response,
    ) -> None:
        """_fetch_papers returns a non-empty list from sample response."""
        connector = WosConnector(api_key="dummy")
        # cap to len(hits) to prevent the mock triggering another paginated
        # request (the page-size equals the real sample's hit count).
        with patch.object(connector, "_get", return_value=mock_response(wos_sample_json)):
            papers = connector._fetch_papers(
                simple_query, max_papers=len(wos_sample_json["hits"]), progress_callback=None
            )
        assert len(papers) == len(wos_sample_json["hits"])

    def test_fetch_papers_respects_max_papers(
        self,
        simple_query,
        wos_sample_json: dict,
        mock_response,
    ) -> None:
        """max_papers=1 returns at most 1 paper."""
        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", return_value=mock_response(wos_sample_json)):
            papers = connector._fetch_papers(simple_query, max_papers=1, progress_callback=None)
        assert len(papers) <= 1

    def test_fetch_papers_progress_callback_called(
        self,
        simple_query,
        wos_sample_json: dict,
        mock_response,
    ) -> None:
        """Progress callback is invoked at least once."""
        calls: list[tuple] = []
        connector = WosConnector(api_key="dummy")
        # cap to avoid the full-page mock causing infinite pagination.
        with patch.object(connector, "_get", return_value=mock_response(wos_sample_json)):
            connector._fetch_papers(
                simple_query,
                max_papers=len(wos_sample_json["hits"]),
                progress_callback=lambda fetched, total: calls.append((fetched, total)),
            )
        assert len(calls) >= 1

    def test_date_filter_appends_py_range_to_query(
        self,
        simple_query,
        wos_sample_json: dict,
        mock_response,
    ) -> None:
        """When since/until are given, PY=(year-year) is appended to the query."""
        connector = WosConnector(api_key="dummy")
        with patch.object(
            connector, "_get", return_value=mock_response(wos_sample_json)
        ) as mock_get:
            connector._fetch_papers(
                simple_query,
                max_papers=1,  # stop after one page to prevent infinite loop
                progress_callback=None,
                since=datetime.date(2020, 1, 1),
                until=datetime.date(2022, 12, 31),
            )
        params = mock_get.call_args[1].get("params") or {}
        assert "publishTimeSpan" not in params
        assert "PY=(2020-2022)" in params["q"]

    def test_empty_hits_ends_pagination(self, simple_query, mock_response) -> None:
        """Empty hits list stops pagination and returns empty list."""
        connector = WosConnector(api_key="dummy")
        with patch.object(
            connector, "_get", return_value=mock_response({"hits": [], "metadata": {"total": 0}})
        ):
            papers = connector._fetch_papers(simple_query, max_papers=None, progress_callback=None)
        assert papers == []

    def test_request_exception_stops_pagination(self, simple_query) -> None:
        """RequestException halts pagination gracefully and returns empty list."""
        import requests

        connector = WosConnector(api_key="dummy")
        with patch.object(connector, "_get", side_effect=requests.RequestException("fail")):
            papers = connector._fetch_papers(simple_query, max_papers=None, progress_callback=None)
        assert papers == []

    def test_request_exception_logs_informative_warning(self, simple_query, caplog) -> None:
        """A failed page logs how many papers were retrieved vs. the estimated total."""
        import requests

        connector = WosConnector(api_key="dummy")
        with (
            patch.object(connector, "_get", side_effect=requests.RequestException("boom")),
            caplog.at_level("WARNING", logger="findpapers.connectors.wos"),
        ):
            connector._fetch_papers(simple_query, max_papers=None, progress_callback=None)
        assert any(
            "search stopped early" in record.message and "page=1" in record.message
            for record in caplog.records
        )

    def test_request_exception_reports_processed_total_via_callback(
        self, simple_query, wos_sample_json: dict, mock_response
    ) -> None:
        """After a mid-pagination failure, the final callback reports a completed
        (processed == total) state instead of the stale, larger API estimate,
        so callers relying on the callback alone see a finished bar."""
        import requests

        connector = WosConnector(api_key="dummy")
        first_page = mock_response(wos_sample_json)
        calls: list[tuple] = []
        with patch.object(
            connector, "_get", side_effect=[first_page, requests.RequestException("boom")]
        ):
            connector._fetch_papers(
                simple_query,
                max_papers=None,
                progress_callback=lambda fetched, total: calls.append((fetched, total)),
            )
        last_fetched, last_total = calls[-1]
        assert last_fetched == len(wos_sample_json["hits"])
        # The API's own metadata.total (learned from the first page) is still
        # reported as-is by the connector; it's search_runner's job to correct
        # it for display, so it stays the original, possibly larger, estimate.
        assert last_total == wos_sample_json["metadata"]["total"]

    def test_empty_hits_before_total_logs_warning(
        self, simple_query, mock_response, caplog
    ) -> None:
        """Hits emptying out before the reported total logs a warning explaining
        that this may be a WoS-side pagination limit rather than an error."""
        connector = WosConnector(api_key="dummy")
        # A full page (== page_size) is required so pagination continues to a
        # second page instead of stopping via the "short last page" natural
        # end-of-results check.
        full_page_hits = [
            {"title": f"Paper {i}", "names": {}, "source": {}, "identifiers": {}, "links": {}}
            for i in range(50)
        ]
        first_page = mock_response(
            {"metadata": {"total": 100, "page": 1, "limit": 50}, "hits": full_page_hits}
        )
        second_page = mock_response({"metadata": {"total": 100}, "hits": []})
        with (
            patch.object(connector, "_get", side_effect=[first_page, second_page]),
            caplog.at_level("WARNING", logger="findpapers.connectors.wos"),
        ):
            papers = connector._fetch_papers(simple_query, max_papers=None, progress_callback=None)
        assert len(papers) == 50
        assert any("pagination limit" in record.message for record in caplog.records)

    def test_empty_hits_at_expected_total_does_not_warn(
        self, simple_query, mock_response, caplog
    ) -> None:
        """Hits emptying out exactly when the total is reached is a normal
        completion and should not log a warning."""
        connector = WosConnector(api_key="dummy")
        full_page_hits = [
            {"title": f"Paper {i}", "names": {}, "source": {}, "identifiers": {}, "links": {}}
            for i in range(50)
        ]
        first_page = mock_response(
            {"metadata": {"total": 50, "page": 1, "limit": 50}, "hits": full_page_hits}
        )
        second_page = mock_response({"metadata": {"total": 50}, "hits": []})
        with (
            patch.object(connector, "_get", side_effect=[first_page, second_page]),
            caplog.at_level("WARNING", logger="findpapers.connectors.wos"),
        ):
            papers = connector._fetch_papers(simple_query, max_papers=None, progress_callback=None)
        assert len(papers) == 50
        assert not any("pagination limit" in record.message for record in caplog.records)


class TestWosUrlPattern:
    """Tests for WosConnector.url_pattern regex."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.webofscience.com/wos/woscc/full-record/WOS:000282418500002",
            "https://webofscience.com/wos/woscc/full-record/WOS:000282418500002",
            "https://www.webofscience.com/wos/WOS:000282418500002",
        ],
    )
    def test_valid_urls_match(self, url: str) -> None:
        """Various WoS URL formats are matched by the url_pattern."""
        connector = WosConnector(api_key="dummy")
        match = connector.url_pattern.search(url)
        assert match is not None
        assert match.group(1).startswith("WOS:")

    def test_non_wos_url_does_not_match(self) -> None:
        """A non-WoS URL does not match the url_pattern."""
        connector = WosConnector(api_key="dummy")
        assert connector.url_pattern.search("https://pubmed.ncbi.nlm.nih.gov/12345") is None
