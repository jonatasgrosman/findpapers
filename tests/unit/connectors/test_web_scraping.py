"""Unit tests for WebScrapingConnector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from curl_cffi.requests.errors import RequestsError as _CurlError

from findpapers.connectors.web_scraping import WebScrapingConnector
from findpapers.core.paper import PaperType


def _mock_html_response(
    html: str,
    content_type: str = "text/html; charset=utf-8",
    url: str = "https://example.com/paper",
    status_code: int = 200,
) -> MagicMock:
    """Build a minimal mock :class:`requests.Response` for HTML content."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason = "OK"
    resp.headers = {"content-type": content_type}
    resp.text = html
    resp.content = html.encode()
    resp.url = url
    resp.raise_for_status = MagicMock()
    return resp


def _mock_non_html_response(
    content_type: str = "application/pdf",
    url: str = "https://example.com/paper.pdf",
) -> MagicMock:
    """Build a minimal mock :class:`requests.Response` for non-HTML content."""
    resp = MagicMock()
    resp.status_code = 200
    resp.reason = "OK"
    resp.headers = {"content-type": content_type}
    resp.text = ""
    resp.content = b""
    resp.url = url
    resp.raise_for_status = MagicMock()
    return resp


_TITLED_HTML = '<html><head><meta name="citation_title" content="Web Test Paper"></head></html>'


class TestWebScrapingConnectorProperties:
    """Tests for connector identity properties."""

    def test_name_is_web_scraping(self) -> None:
        """name property returns 'web_scraping'."""
        connector = WebScrapingConnector()
        assert connector.name == "web_scraping"

    def test_min_request_interval_is_zero(self) -> None:
        """min_request_interval is 0.0 (no per-host rate limit)."""
        connector = WebScrapingConnector()
        assert connector.min_request_interval == 0.0


class TestWebScrapingConnectorInit:
    """Tests for constructor defaults and parameter storage."""

    def test_default_proxy_is_none(self) -> None:
        """Proxy defaults to None when not supplied."""
        connector = WebScrapingConnector()
        assert connector._proxy is None

    def test_default_ssl_verify_is_true(self) -> None:
        """ssl_verify defaults to True."""
        connector = WebScrapingConnector()
        assert connector._ssl_verify is True

    def test_proxy_stored(self) -> None:
        """Supplied proxy is stored on the instance."""
        connector = WebScrapingConnector(proxy="http://proxy:8080")
        assert connector._proxy == "http://proxy:8080"

    def test_ssl_verify_false_stored(self) -> None:
        """ssl_verify=False is stored on the instance."""
        connector = WebScrapingConnector(ssl_verify=False)
        assert connector._ssl_verify is False


class TestWebScrapingConnectorGetProxies:
    """Tests for _get_proxies helper."""

    def test_returns_none_when_no_proxy(self) -> None:
        """_get_proxies returns None when no proxy is configured."""
        connector = WebScrapingConnector()
        assert connector._get_proxies() is None

    def test_returns_dict_when_proxy_set(self) -> None:
        """_get_proxies returns http/https dict when proxy is configured."""
        connector = WebScrapingConnector(proxy="http://proxy:8080")
        proxies = connector._get_proxies()
        assert proxies == {"http": "http://proxy:8080", "https": "http://proxy:8080"}


class TestWebScrapingConnectorFetchPaperFromUrl:
    """Tests for fetch_paper_from_url."""

    def test_returns_none_for_non_html_content_type(self) -> None:
        """Returns None when the response is not text/html."""
        connector = WebScrapingConnector()
        with patch.object(connector, "_make_html_request", return_value=_mock_non_html_response()):
            result = connector.fetch_paper_from_url("https://example.com/paper.pdf")
        assert result is None

    def test_returns_paper_for_html_with_title(self) -> None:
        """Returns a Paper when the HTML contains a parseable title."""
        connector = WebScrapingConnector()
        with patch.object(
            connector, "_make_html_request", return_value=_mock_html_response(_TITLED_HTML)
        ):
            paper = connector.fetch_paper_from_url("https://example.com/paper")
        assert paper is not None
        assert paper.title == "Web Test Paper"

    def test_returns_none_for_html_without_title(self) -> None:
        """Returns None when the HTML has no parseable title."""
        empty_html = "<html><head></head><body>No meta tags here.</body></html>"
        connector = WebScrapingConnector()
        with patch.object(
            connector, "_make_html_request", return_value=_mock_html_response(empty_html)
        ):
            result = connector.fetch_paper_from_url("https://example.com/paper")
        assert result is None

    def test_paper_url_is_final_redirect_url(self) -> None:
        """The paper URL is set to response.url (after redirects), not the original URL."""
        final_url = "https://doi.org/resolved/paper"
        connector = WebScrapingConnector()
        resp = _mock_html_response(_TITLED_HTML, url=final_url)
        with patch.object(connector, "_make_html_request", return_value=resp):
            paper = connector.fetch_paper_from_url("https://example.com/redirect")
        assert paper is not None
        assert paper.url == final_url

    def test_raises_on_network_error(self) -> None:
        """Propagates requests.RequestException on network-level curl_cffi errors."""
        connector = WebScrapingConnector()
        with (
            patch.object(connector, "_make_html_request", side_effect=_CurlError("refused")),
            pytest.raises(requests.RequestException),
        ):
            connector.fetch_paper_from_url("https://example.com/paper")

    def _curl_session_ctx(self, response: MagicMock) -> tuple[MagicMock, MagicMock]:
        """Return (MockSession, session_ctx) with ctx.get pre-configured to return *response*."""
        ctx = MagicMock()
        ctx.get.return_value = response
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=ctx)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session, ctx

    def test_proxy_forwarded_to_session_get(self) -> None:
        """proxy setting is forwarded as proxies= to _CurlSession.get()."""
        connector = WebScrapingConnector(proxy="http://proxy:8080")
        mock_session, ctx = self._curl_session_ctx(_mock_html_response(_TITLED_HTML))
        with patch("findpapers.connectors.web_scraping._CurlSession", return_value=mock_session):
            connector.fetch_paper_from_url("https://example.com/paper")
        _, get_kwargs = ctx.get.call_args
        assert get_kwargs["proxies"] == {"http": "http://proxy:8080", "https": "http://proxy:8080"}

    def test_ssl_verify_false_forwarded_to_session_get(self) -> None:
        """ssl_verify=False is forwarded as verify=False to _CurlSession.get()."""
        connector = WebScrapingConnector(ssl_verify=False)
        mock_session, ctx = self._curl_session_ctx(_mock_html_response(_TITLED_HTML))
        with patch("findpapers.connectors.web_scraping._CurlSession", return_value=mock_session):
            connector.fetch_paper_from_url("https://example.com/paper")
        _, get_kwargs = ctx.get.call_args
        assert get_kwargs["verify"] is False

    def test_ssl_verify_defaults_to_true_in_request(self) -> None:
        """verify=True is passed to _CurlSession.get() by default."""
        connector = WebScrapingConnector()
        mock_session, ctx = self._curl_session_ctx(_mock_html_response(_TITLED_HTML))
        with patch("findpapers.connectors.web_scraping._CurlSession", return_value=mock_session):
            connector.fetch_paper_from_url("https://example.com/paper")
        _, get_kwargs = ctx.get.call_args
        assert get_kwargs["verify"] is True

    def test_no_proxy_sends_none_to_session_get(self) -> None:
        """proxies=None is passed to _CurlSession.get() when no proxy is configured."""
        connector = WebScrapingConnector()
        mock_session, ctx = self._curl_session_ctx(_mock_html_response(_TITLED_HTML))
        with patch("findpapers.connectors.web_scraping._CurlSession", return_value=mock_session):
            connector.fetch_paper_from_url("https://example.com/paper")
        _, get_kwargs = ctx.get.call_args
        assert get_kwargs["proxies"] is None

    def test_allow_redirects_is_true(self) -> None:
        """allow_redirects=True is always passed to _CurlSession.get()."""
        connector = WebScrapingConnector()
        mock_session, ctx = self._curl_session_ctx(_mock_html_response(_TITLED_HTML))
        with patch("findpapers.connectors.web_scraping._CurlSession", return_value=mock_session):
            connector.fetch_paper_from_url("https://example.com/paper")
        _, get_kwargs = ctx.get.call_args
        assert get_kwargs["allow_redirects"] is True

    def test_timeout_forwarded_to_session_get(self) -> None:
        """Custom timeout is forwarded to _CurlSession.get()."""
        connector = WebScrapingConnector()
        mock_session, ctx = self._curl_session_ctx(_mock_html_response(_TITLED_HTML))
        with patch("findpapers.connectors.web_scraping._CurlSession", return_value=mock_session):
            connector.fetch_paper_from_url("https://example.com/paper", timeout=30.0)
        _, get_kwargs = ctx.get.call_args
        assert get_kwargs["timeout"] == 30.0

    def test_raise_for_status_called(self) -> None:
        """raise_for_status() is called on the response."""
        connector = WebScrapingConnector()
        resp = _mock_html_response(_TITLED_HTML)
        with patch.object(connector, "_make_html_request", return_value=resp):
            connector.fetch_paper_from_url("https://example.com/paper")
        resp.raise_for_status.assert_called_once()


class TestWebScrapingConnectorContextManager:
    """Tests for context-manager protocol (from ConnectorBase)."""

    def test_context_manager_closes_session(self) -> None:
        """Using the connector as a context manager closes the HTTP session afterwards."""
        with WebScrapingConnector() as connector:
            # Force session creation
            connector._get_session()
            assert hasattr(connector, "_http_session")
        # After __exit__, session must be closed/removed
        assert not hasattr(connector, "_http_session")


# ---------------------------------------------------------------------------
# Helpers shared by the API-fallback tests
# ---------------------------------------------------------------------------


def _mock_api_response(
    body: dict,
    status_code: int = 200,
) -> MagicMock:
    """Build a minimal mock :class:`requests.Response` for a JSON API call."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason = "OK" if status_code == 200 else "Error"
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


def _mock_blocking_html_response(
    status_code: int = 403,
    url: str = "https://example.com/blocked",
) -> MagicMock:
    """Build a response that triggers the API-fallback branch."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason = "Forbidden" if status_code == 403 else "Error"
    resp.headers = {"content-type": "text/html"}
    resp.text = "<html><body>Blocked</body></html>"
    resp.content = resp.text.encode()
    resp.url = url
    # fetch_paper_from_url only calls raise_for_status() for non-fallback codes
    # (403/406/418 take the early-return path).  For 4xx that reach raise_for_status
    # the connector expects _CurlError (which it re-raises as requests.HTTPError).
    resp.raise_for_status.side_effect = _CurlError(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# Tests for fetch_paper_from_url: API fallback dispatch
# ---------------------------------------------------------------------------


class TestFetchPaperFromUrlApiFallback:
    """Tests that verify the API-fallback branch is entered on blocking responses."""

    def test_403_triggers_fallback(self) -> None:
        """A 403 response causes _try_api_fallback to be called."""
        connector = WebScrapingConnector()
        with (
            patch.object(
                connector, "_make_html_request", return_value=_mock_blocking_html_response(403)
            ),
            patch.object(connector, "_try_api_fallback", return_value=None) as spy,
        ):
            connector.fetch_paper_from_url("https://zenodo.org/record/123")
        spy.assert_called_once()

    def test_406_triggers_fallback(self) -> None:
        """A 406 response causes _try_api_fallback to be called."""
        connector = WebScrapingConnector()
        with (
            patch.object(
                connector, "_make_html_request", return_value=_mock_blocking_html_response(406)
            ),
            patch.object(connector, "_try_api_fallback", return_value=None) as spy,
        ):
            connector.fetch_paper_from_url("https://academic.oup.com/article/12345")
        spy.assert_called_once()

    def test_418_triggers_fallback(self) -> None:
        """A 418 response causes _try_api_fallback to be called."""
        connector = WebScrapingConnector()
        with (
            patch.object(
                connector, "_make_html_request", return_value=_mock_blocking_html_response(418)
            ),
            patch.object(connector, "_try_api_fallback", return_value=None) as spy,
        ):
            connector.fetch_paper_from_url("https://ieeexplore.ieee.org/document/123")
        spy.assert_called_once()

    def test_404_does_not_trigger_fallback(self) -> None:
        """A 404 is re-raised as an HTTPError (no fallback)."""
        connector = WebScrapingConnector()
        with (
            patch.object(
                connector, "_make_html_request", return_value=_mock_blocking_html_response(404)
            ),
            pytest.raises(requests.HTTPError),
        ):
            connector.fetch_paper_from_url("https://example.com/missing")

    def test_fallback_return_value_propagated(self) -> None:
        """The Paper returned by _try_api_fallback is returned to the caller."""
        connector = WebScrapingConnector()
        fake_paper = MagicMock()
        with (
            patch.object(
                connector, "_make_html_request", return_value=_mock_blocking_html_response(403)
            ),
            patch.object(connector, "_try_api_fallback", return_value=fake_paper),
        ):
            result = connector.fetch_paper_from_url("https://zenodo.org/record/123")
        assert result is fake_paper


# ---------------------------------------------------------------------------
# Tests for _try_api_fallback routing
# ---------------------------------------------------------------------------


class TestTryApiFallbackRouting:
    """Tests that _try_api_fallback dispatches to the correct host-specific method."""

    def test_zenodo_record_url_routes_to_zenodo(self) -> None:
        """A zenodo.org/record/... URL calls _fetch_from_zenodo_api."""
        connector = WebScrapingConnector()
        with patch.object(WebScrapingConnector, "_fetch_from_zenodo_api", return_value=None) as spy:
            connector._try_api_fallback(
                "https://doi.org/10.5281/zenodo.7602012",
                "https://zenodo.org/record/7602012",
                10.0,
            )
        spy.assert_called_once_with("7602012", "https://zenodo.org/record/7602012", 10.0)

    def test_zenodo_records_url_routes_to_zenodo(self) -> None:
        """A zenodo.org/records/... URL (current format) also calls _fetch_from_zenodo_api."""
        connector = WebScrapingConnector()
        with patch.object(WebScrapingConnector, "_fetch_from_zenodo_api", return_value=None) as spy:
            connector._try_api_fallback(
                "https://doi.org/10.5281/zenodo.9999",
                "https://zenodo.org/records/9999",
                10.0,
            )
        spy.assert_called_once_with("9999", "https://zenodo.org/records/9999", 10.0)

    def test_biorxiv_url_routes_to_biorxiv(self) -> None:
        """A biorxiv.org/content/... URL calls _fetch_from_biorxiv_api with server='biorxiv'."""
        connector = WebScrapingConnector()
        biorxiv_url = "https://www.biorxiv.org/content/10.1101/2021.03.01.433431v2"
        with patch.object(
            WebScrapingConnector, "_fetch_from_biorxiv_api", return_value=None
        ) as spy:
            connector._try_api_fallback(biorxiv_url, biorxiv_url, 10.0)
        spy.assert_called_once_with(
            "10.1101/2021.03.01.433431", biorxiv_url, 10.0, server="biorxiv"
        )

    def test_medrxiv_url_routes_to_biorxiv_api_with_medrxiv_server(self) -> None:
        """A medrxiv.org/content/... URL calls _fetch_from_biorxiv_api with server='medrxiv'."""
        connector = WebScrapingConnector()
        medrxiv_url = "https://www.medrxiv.org/content/10.1101/2020.05.01.20087619v1"
        with patch.object(
            WebScrapingConnector, "_fetch_from_biorxiv_api", return_value=None
        ) as spy:
            connector._try_api_fallback(medrxiv_url, medrxiv_url, 10.0)
        spy.assert_called_once_with(
            "10.1101/2020.05.01.20087619", medrxiv_url, 10.0, server="medrxiv"
        )

    def test_unknown_url_returns_none(self) -> None:
        """An unrecognised URL returns None without calling any fallback."""
        connector = WebScrapingConnector()
        result = connector._try_api_fallback(
            "https://dl.acm.org/doi/10.1145/3287560.3287596",
            "https://dl.acm.org/doi/10.1145/3287560.3287596",
            10.0,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _fetch_from_zenodo_api
# ---------------------------------------------------------------------------

_ZENODO_API_RESPONSE: dict = {
    "id": 7602012,
    "doi": "10.5281/zenodo.7602012",
    "metadata": {
        "title": "AI in Business",
        "doi": "10.5281/zenodo.7602012",
        "publication_date": "2022-12-31",
        "description": "<p>Abstract text here.</p>",
        "creators": [{"name": "Santos, A. R.", "affiliation": "University of Example"}],
        "keywords": ["Artificial Intelligence", "Business"],
        "resource_type": {"type": "publication", "subtype": "article"},
        "journal": {"title": "Int. Journal of AI", "issn": "1234-5678", "volume": "4"},
    },
}


class TestFetchFromZenodoApi:
    """Tests for _fetch_from_zenodo_api."""

    def test_returns_paper_on_success(self) -> None:
        """Returns a Paper with all fields populated on a 200 response."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(_ZENODO_API_RESPONSE),
        ):
            paper = WebScrapingConnector._fetch_from_zenodo_api(
                "7602012", "https://zenodo.org/record/7602012", 10.0
            )
        assert paper is not None
        assert paper.title == "AI in Business"
        assert paper.doi == "10.5281/zenodo.7602012"
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Santos, A. R."
        assert paper.source is not None
        assert paper.source.title == "Int. Journal of AI"

    def test_abstract_html_stripped(self) -> None:
        """HTML tags in the description are stripped from the abstract."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(_ZENODO_API_RESPONSE),
        ):
            paper = WebScrapingConnector._fetch_from_zenodo_api(
                "7602012", "https://zenodo.org/record/7602012", 10.0
            )
        assert paper is not None
        assert "<p>" not in paper.abstract
        assert "Abstract text here" in paper.abstract

    def test_returns_none_when_title_missing(self) -> None:
        """Returns None when the API response lacks a title."""
        data = {"id": 1, "metadata": {}}
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            result = WebScrapingConnector._fetch_from_zenodo_api(
                "1", "https://zenodo.org/record/1", 10.0
            )
        assert result is None

    def test_returns_none_on_api_error(self) -> None:
        """Returns None when the API call raises an exception."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            side_effect=requests.ConnectionError("unreachable"),
        ):
            result = WebScrapingConnector._fetch_from_zenodo_api(
                "999", "https://zenodo.org/record/999", 5.0
            )
        assert result is None

    def test_keywords_as_list(self) -> None:
        """Keywords stored as a list are correctly parsed."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(_ZENODO_API_RESPONSE),
        ):
            paper = WebScrapingConnector._fetch_from_zenodo_api(
                "7602012", "https://zenodo.org/record/7602012", 10.0
            )
        assert paper is not None
        assert paper.keywords is not None
        assert "Artificial Intelligence" in paper.keywords

    def test_no_source_when_journal_absent(self) -> None:
        """Source is None when the metadata has no journal block."""
        data = {
            **_ZENODO_API_RESPONSE,
            "metadata": {**_ZENODO_API_RESPONSE["metadata"], "journal": None},
        }
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            paper = WebScrapingConnector._fetch_from_zenodo_api(
                "7602012", "https://zenodo.org/record/7602012", 10.0
            )
        assert paper is not None
        assert paper.source is None


# ---------------------------------------------------------------------------
# Tests for _fetch_from_biorxiv_api
# ---------------------------------------------------------------------------

_BIORXIV_API_RESPONSE: dict = {
    "messages": [{"status": "ok"}],
    "collection": [
        {
            "title": "SARS-CoV-2 in H522 cells",
            "authors": "Puray-Chavez, M.; Lapak, K. M.; Kutluay, S. B.",
            "doi": "10.1101/2021.03.01.433431",
            "date": "2021-03-01",
            "abstract": "We identified H522 cells as permissive to SARS-CoV-2.",
            "category": "microbiology",
            "funder": "NIH",
            "server": "bioRxiv",
        }
    ],
}


class TestFetchFromBiorxivApi:
    """Tests for _fetch_from_biorxiv_api."""

    def test_returns_paper_on_success(self) -> None:
        """Returns a Paper with correct title, authors, and abstract."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(_BIORXIV_API_RESPONSE),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2021.03.01.433431",
                "https://www.biorxiv.org/content/10.1101/2021.03.01.433431v2",
                10.0,
            )
        assert paper is not None
        assert paper.title == "SARS-CoV-2 in H522 cells"
        assert len(paper.authors) == 3
        assert paper.authors[0].name == "Puray-Chavez, M."
        assert "H522" in paper.abstract
        assert paper.keywords == {"microbiology"}
        assert paper.paper_type == PaperType.UNPUBLISHED
        assert paper.funders == {"NIH"}

    def test_uses_latest_version(self) -> None:
        """When multiple versions exist, the last entry in the collection is used."""
        multi = {
            "messages": [{"status": "ok"}],
            "collection": [
                {
                    "title": "v1 Title",
                    "authors": "Author, A.",
                    "doi": "10.1101/x",
                    "date": "2021-01-01",
                    "abstract": "",
                },
                {
                    "title": "v2 Title",
                    "authors": "Author, A.",
                    "doi": "10.1101/x",
                    "date": "2021-02-01",
                    "abstract": "",
                },
            ],
        }
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(multi),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/x", "https://www.biorxiv.org/content/10.1101/xv2", 10.0
            )
        assert paper is not None
        assert paper.title == "v2 Title"

    def test_returns_none_when_collection_empty(self) -> None:
        """Returns None when the collection list is empty (DOI not found)."""
        data = {"messages": [{"status": "no posts found"}], "collection": []}
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            result = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/unknown", "https://www.biorxiv.org/content/10.1101/unknown", 10.0
            )
        assert result is None

    def test_returns_none_on_api_error(self) -> None:
        """Returns None when the API call raises an exception."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            side_effect=requests.ConnectionError("timeout"),
        ):
            result = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/x", "https://biorxiv.org/...", 5.0
            )
        assert result is None

    def test_source_is_none(self) -> None:
        """bioRxiv preprints have no formal source."""
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(_BIORXIV_API_RESPONSE),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2021.03.01.433431",
                "https://www.biorxiv.org/content/10.1101/2021.03.01.433431v2",
                10.0,
            )
        assert paper is not None
        assert paper.source is None

    def test_medrxiv_server_slug_used_in_api_url(self) -> None:
        """Passing server='medrxiv' queries the medRxiv endpoint."""
        _MEDRXIV_RESPONSE: dict = {
            "messages": [{"status": "ok"}],
            "collection": [
                {
                    "title": "COVID-19 Vaccine Effectiveness",
                    "authors": "Smith, J.; Jones, B.",
                    "doi": "10.1101/2020.05.01.20087619",
                    "date": "2020-05-01",
                    "abstract": "Effectiveness of mRNA vaccines.",
                    "category": "epidemiology",
                    "funder": "NA",
                    "server": "medRxiv",
                }
            ],
        }
        captured_urls: list[str] = []

        def _fake_get(url: str, **kwargs):
            captured_urls.append(url)
            return _mock_api_response(_MEDRXIV_RESPONSE)

        with patch("findpapers.connectors.web_scraping.requests.get", side_effect=_fake_get):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2020.05.01.20087619",
                "https://www.medrxiv.org/content/10.1101/2020.05.01.20087619v1",
                10.0,
                server="medrxiv",
            )
        assert paper is not None
        assert paper.title == "COVID-19 Vaccine Effectiveness"
        assert len(paper.authors) == 2
        assert "medrxiv" in captured_urls[0]
        assert paper.source is None
        assert paper.keywords == {"epidemiology"}
        assert paper.paper_type == PaperType.UNPUBLISHED
        assert paper.funders == set()  # funder == "NA" -> empty set

    def test_keywords_empty_when_category_missing(self) -> None:
        """keywords is an empty set when the record has no category field."""
        data: dict = {
            "messages": [{"status": "ok"}],
            "collection": [
                {
                    "title": "No Category Paper",
                    "authors": "Author, A.",
                    "doi": "10.1101/2021.01.01.000001",
                    "date": "2021-01-01",
                    "abstract": "Abstract text.",
                    "server": "bioRxiv",
                    # no "category" key
                }
            ],
        }
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2021.01.01.000001",
                "https://www.biorxiv.org/content/10.1101/2021.01.01.000001v1",
                10.0,
            )
        assert paper is not None
        assert paper.keywords == set()
        assert paper.paper_type == PaperType.UNPUBLISHED

    def test_funders_populated_when_funder_not_na(self) -> None:
        """funders is a set with the funder name when funder != 'NA'."""
        data: dict = {
            "messages": [{"status": "ok"}],
            "collection": [
                {
                    "title": "Funded Paper",
                    "authors": "Author, A.",
                    "doi": "10.1101/2021.01.01.000002",
                    "date": "2021-01-01",
                    "abstract": "Abstract text.",
                    "category": "genetics",
                    "funder": "Wellcome Trust",
                    "server": "bioRxiv",
                }
            ],
        }
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2021.01.01.000002",
                "https://www.biorxiv.org/content/10.1101/2021.01.01.000002v1",
                10.0,
            )
        assert paper is not None
        assert paper.funders == {"Wellcome Trust"}

    def test_funders_empty_when_funder_is_na(self) -> None:
        """funders is an empty set when the funder field is the placeholder 'NA'."""
        data: dict = {
            "messages": [{"status": "ok"}],
            "collection": [
                {
                    "title": "Unfunded Paper",
                    "authors": "Author, A.",
                    "doi": "10.1101/2021.01.01.000003",
                    "date": "2021-01-01",
                    "abstract": "Abstract text.",
                    "funder": "NA",
                    "server": "bioRxiv",
                }
            ],
        }
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2021.01.01.000003",
                "https://www.biorxiv.org/content/10.1101/2021.01.01.000003v1",
                10.0,
            )
        assert paper is not None
        assert paper.funders == set()

    def test_paper_type_always_unpublished(self) -> None:
        """paper_type is always PaperType.UNPUBLISHED regardless of the 'type' field."""
        data: dict = {
            "messages": [{"status": "ok"}],
            "collection": [
                {
                    "title": "Published Elsewhere Paper",
                    "authors": "Author, A.",
                    "doi": "10.1101/2021.01.01.000004",
                    "date": "2021-01-01",
                    "abstract": "Abstract text.",
                    "type": "new results",
                    "published": "10.1038/s41586-021-00001-0",  # published in a journal
                    "server": "bioRxiv",
                }
            ],
        }
        with patch(
            "findpapers.connectors.web_scraping.requests.get",
            return_value=_mock_api_response(data),
        ):
            paper = WebScrapingConnector._fetch_from_biorxiv_api(
                "10.1101/2021.01.01.000004",
                "https://www.biorxiv.org/content/10.1101/2021.01.01.000004v1",
                10.0,
            )
        assert paper is not None
        assert paper.paper_type == PaperType.UNPUBLISHED


# ---------------------------------------------------------------------------
# Tests for _merge_ieee_metadata: publicationYear fallback + isOpenAccess
# ---------------------------------------------------------------------------


def _ieee_html(*fields_kv: tuple[str, object]) -> str:
    """Return minimal HTML containing an IEEE JS metadata blob with the given fields."""
    import json

    blob = json.dumps(dict(fields_kv))
    return f"<html><script>xplGlobal.document.metadata = {blob};</script></html>"


class TestMergeIeeeMetadataPublicationYear:
    """Tests for publicationYear fallback and isOpenAccess in _merge_ieee_metadata."""

    def test_publication_year_used_when_date_absent(self) -> None:
        """publicationYear is stored when publicationDate is missing."""
        content = _ieee_html(("publicationYear", "2022"))
        meta = WebScrapingConnector._extract_metadata_from_html(content)
        assert meta.get("citation_publication_date") == "2022"

    def test_publication_date_takes_priority_over_year(self) -> None:
        """publicationDate wins over publicationYear when both are present."""
        content = _ieee_html(("publicationDate", "2022-03"), ("publicationYear", "2022"))
        meta = WebScrapingConnector._extract_metadata_from_html(content)
        assert meta.get("citation_publication_date") == "2022-03"

    def test_is_open_access_true_extracted(self) -> None:
        """isOpenAccess=True from the IEEE blob is stored as _is_open_access."""
        content = _ieee_html(("isOpenAccess", True))
        meta = WebScrapingConnector._extract_metadata_from_html(content)
        assert meta.get("_is_open_access") is True

    def test_is_open_access_false_extracted(self) -> None:
        """isOpenAccess=False from the IEEE blob is stored as _is_open_access."""
        content = _ieee_html(("isOpenAccess", False))
        meta = WebScrapingConnector._extract_metadata_from_html(content)
        assert meta.get("_is_open_access") is False

    def test_is_open_access_propagated_to_paper(self) -> None:
        """_is_open_access=True in the metadata dict is propagated to Paper.is_open_access."""
        meta = {
            "citation_title": "Test Paper",
            "citation_author": "Doe, J.",
            "_is_open_access": True,
        }
        paper = WebScrapingConnector.build_paper_from_metadata(meta, "https://example.com")
        assert paper is not None
        assert paper.is_open_access is True

    def test_is_open_access_false_propagated_to_paper(self) -> None:
        """_is_open_access=False in the metadata dict is propagated to Paper.is_open_access."""
        meta = {
            "citation_title": "Test Paper",
            "citation_author": "Doe, J.",
            "_is_open_access": False,
        }
        paper = WebScrapingConnector.build_paper_from_metadata(meta, "https://example.com")
        assert paper is not None
        assert paper.is_open_access is False

    def test_is_open_access_none_when_absent(self) -> None:
        """Paper.is_open_access is None when _is_open_access is not in the metadata."""
        meta = {"citation_title": "Test Paper", "citation_author": "Doe, J."}
        paper = WebScrapingConnector.build_paper_from_metadata(meta, "https://example.com")
        assert paper is not None
        assert paper.is_open_access is None


# ---------------------------------------------------------------------------
# Tests for _merge_jsonld_metadata: @id DOI, editor fallback, isAccessibleForFree
# ---------------------------------------------------------------------------


def _jsonld_html(data: dict) -> str:
    """Return minimal HTML with a JSON-LD script block of the given data."""
    import json

    payload = {"@type": "ScholarlyArticle", **data}
    script = json.dumps(payload)
    return f'<html><head><script type="application/ld+json">{script}</script></head></html>'


class TestMergeJsonldMetadata:
    """Tests for DOI from @id, editor fallback, and isAccessibleForFree in _merge_jsonld_metadata."""

    def test_doi_extracted_from_degruyter_at_id(self) -> None:
        """DOI is extracted from a De Gruyter-style @id URL."""
        html = _jsonld_html(
            {
                "@id": "https://www.degruyterbrill.com/document/doi/10.1515/9783110750584/html",
                "name": "Test Book",
            }
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.1515/9783110750584"

    def test_doi_extracted_from_doi_org_at_id(self) -> None:
        """DOI is extracted from a doi.org @id URL."""
        html = _jsonld_html(
            {
                "@id": "https://doi.org/10.1234/test.456",
                "name": "Test",
            }
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.1234/test.456"

    def test_at_id_doi_does_not_overwrite_explicit_doi(self) -> None:
        """An explicit doi/identifier field takes priority over the @id URL."""
        html = _jsonld_html(
            {
                "@id": "https://doi.org/10.9999/wrong",
                "doi": "10.1234/correct",
                "name": "Test",
            }
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.1234/correct"

    def test_editor_used_when_author_empty(self) -> None:
        """Editor list is used for citation_author when author is empty."""
        html = _jsonld_html(
            {
                "name": "Edited Book",
                "author": [],
                "editor": [{"@type": "Person", "name": "Jane Editor"}],
            }
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_author") == "Jane Editor"

    def test_author_takes_priority_over_editor(self) -> None:
        """When author is present, editor is ignored."""
        html = _jsonld_html(
            {
                "name": "Authored Book",
                "author": [{"@type": "Person", "name": "John Author"}],
                "editor": [{"@type": "Person", "name": "Jane Editor"}],
            }
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_author") == "John Author"

    def test_is_accessible_for_free_true(self) -> None:
        """isAccessibleForFree=True sets _is_open_access to True."""
        html = _jsonld_html({"name": "Open Article", "isAccessibleForFree": True})
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("_is_open_access") is True

    def test_is_accessible_for_free_false(self) -> None:
        """isAccessibleForFree=False sets _is_open_access to False."""
        html = _jsonld_html({"name": "Paywalled Article", "isAccessibleForFree": False})
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("_is_open_access") is False


# ---------------------------------------------------------------------------
# Tests for _merge_arxiv_subjects
# ---------------------------------------------------------------------------


class TestMergeArxivSubjects:
    """Tests for the ArXiv subjects-as-keywords extraction."""

    def test_subjects_extracted_as_keywords(self) -> None:
        """Subjects cell contents become citation_keywords."""
        html = (
            "<html><body><table><tr>"
            '<td class="tablecell subjects">Computer Vision (cs.CV); Machine Learning (cs.LG)</td>'
            "</tr></table></body></html>"
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert "citation_keywords" in meta
        assert "cs.CV" in meta["citation_keywords"]

    def test_subjects_not_overwritten_when_keywords_already_present(self) -> None:
        """Subjects are skipped when citation_keywords already exists in the page."""
        html = (
            '<html><head><meta name="citation_keywords" content="existing keyword"></head>'
            "<body><table><tr>"
            '<td class="tablecell subjects">cs.CV</td>'
            "</tr></table></body></html>"
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_keywords") == "existing keyword"

    def test_no_subjects_element_is_noop(self) -> None:
        """No citation_keywords is set when there is no subjects cell."""
        html = "<html><body><p>No subjects here</p></body></html>"
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert "citation_keywords" not in meta


# ---------------------------------------------------------------------------
# Tests for DOI extraction from visible "DOI: ..." text in HTML
# ---------------------------------------------------------------------------


class TestDoiFromTextPattern:
    """Tests for the last-resort DOI extraction from plain-text 'DOI: ...' labels."""

    def test_doi_extracted_from_doi_label(self) -> None:
        """DOI is extracted when preceded by 'DOI:' in the page text."""
        html = "<html><body><span>DOI: 10.3837/tiis.2022.12.005</span></body></html>"
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.3837/tiis.2022.12.005"

    def test_doi_trailing_punctuation_stripped(self) -> None:
        """Trailing commas and similar punctuation are stripped from the extracted DOI."""
        html = "<html><body><p>DOI: 10.3837/tiis.2022.12.005,</p></body></html>"
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.3837/tiis.2022.12.005"

    def test_doi_case_insensitive(self) -> None:
        """The 'DOI:' label is matched case-insensitively."""
        html = "<html><body><p>doi: 10.1234/test</p></body></html>"
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.1234/test"

    def test_meta_tag_doi_takes_priority(self) -> None:
        """A citation_doi meta tag is preferred over the plain-text fallback."""
        html = (
            '<html><head><meta name="citation_doi" content="10.1234/correct"></head>'
            "<body><p>DOI: 10.9999/wrong</p></body></html>"
        )
        meta = WebScrapingConnector._extract_metadata_from_html(html)
        assert meta.get("citation_doi") == "10.1234/correct"


class TestWebScrapingConnectorURLLookupDelegation:
    """Tests for URL-lookup connector delegation in fetch_paper_from_url."""

    def _make_url_lookup_connector(self, url_pattern_str: str, paper: object) -> MagicMock:
        """Build a mock URLLookupConnectorBase that returns *paper* for matching URLs."""
        import re

        pattern = re.compile(url_pattern_str)
        connector = MagicMock()
        connector.url_pattern = pattern
        connector.name = "mock_connector"
        connector.supports_url.side_effect = lambda url: bool(pattern.search(url))
        connector.fetch_paper_by_url.return_value = paper
        return connector

    def test_matching_connector_is_used_instead_of_scraping(self) -> None:
        """When a URL-lookup connector matches, fetch_paper_from_url delegates to it."""
        expected_paper = MagicMock()
        url_connector = self._make_url_lookup_connector(r"arxiv\.org/abs/(\d+)", expected_paper)

        scraper = WebScrapingConnector(url_lookup_connectors=[url_connector])
        result = scraper.fetch_paper_from_url("https://arxiv.org/abs/1706.03762")

        url_connector.fetch_paper_by_url.assert_called_once_with("https://arxiv.org/abs/1706.03762")
        assert result is expected_paper

    def test_non_matching_connector_falls_through_to_scraping(self) -> None:
        """When no URL-lookup connector matches, scraping proceeds normally."""
        url_connector = self._make_url_lookup_connector(r"arxiv\.org/abs/(\d+)", None)
        url_connector.fetch_paper_by_url.return_value = None

        scraper = WebScrapingConnector(url_lookup_connectors=[url_connector])
        html = '<html><head><meta name="citation_title" content="Test Paper"></head></html>'
        with patch.object(
            scraper,
            "_make_html_request",
            return_value=_mock_html_response(html, url="https://example.com/paper"),
        ):
            result = scraper.fetch_paper_from_url("https://example.com/paper")

        # Scraping was performed and returned a paper.
        assert result is not None
        assert result.title == "Test Paper"

    def test_first_matching_connector_wins(self) -> None:
        """When multiple connectors match, the first one's result is used."""
        paper_a = MagicMock()
        paper_b = MagicMock()
        connector_a = self._make_url_lookup_connector(r"example\.com/paper/(\w+)", paper_a)
        connector_b = self._make_url_lookup_connector(r"example\.com/paper/(\w+)", paper_b)

        scraper = WebScrapingConnector(url_lookup_connectors=[connector_a, connector_b])
        result = scraper.fetch_paper_from_url("https://example.com/paper/123")

        assert result is paper_a
        connector_b.fetch_paper_by_url.assert_not_called()

    def test_no_url_lookup_connectors_by_default(self) -> None:
        """WebScrapingConnector has an empty url_lookup_connectors list by default."""
        scraper = WebScrapingConnector()
        assert scraper._url_lookup_connectors == []

    def test_url_lookup_connectors_stored(self) -> None:
        """url_lookup_connectors passed at construction are stored on the instance."""
        mock_connector = MagicMock()
        scraper = WebScrapingConnector(url_lookup_connectors=[mock_connector])
        assert scraper._url_lookup_connectors == [mock_connector]
