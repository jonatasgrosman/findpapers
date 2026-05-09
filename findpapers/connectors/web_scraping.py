"""Web scraping connector: fetches HTML pages and extracts academic paper metadata.

Given a landing-page URL the connector performs a browser-like HTTP GET,
parses ``<meta>`` tags (plus IEEE Xplore JS-embedded blobs), and assembles a
:class:`~findpapers.core.paper.Paper` object from the extracted metadata.

All HTML extraction, field parsing, and paper-assembly logic lives inside
:class:`WebScrapingConnector` as class or static methods so that the scraping
knowledge is fully encapsulated in one place.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Any

import requests
from curl_cffi.requests import Response as _CurlResponse
from curl_cffi.requests import Session as _CurlSession
from curl_cffi.requests.errors import RequestsError as _CurlError
from lxml import html
from lxml.html import HtmlElement

from findpapers.connectors.connector_base import ConnectorBase
from findpapers.connectors.url_lookup_base import URLLookupConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Paper, PaperType
from findpapers.core.source import Source, SourceType
from findpapers.utils.normalization import normalize_doi, parse_date

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Meta-tag key constants (priority-ordered for each field)
# ------------------------------------------------------------------

_TITLE_META_KEYS: list[str] = [
    "citation_title",
    "dc.title",
    "dc.title.alternative",
    "og:title",
    "twitter:title",
    "title",
]
_ABSTRACT_META_KEYS: list[str] = [
    "citation_abstract",
    "dc.description",
    "dc.description.abstract",
    "description",
    "og:description",
    "twitter:description",
]
_AUTHOR_META_KEYS: list[str] = [
    "citation_author",
    "citation_authors",  # PubMed uses the plural form (semicolon-separated)
    "dc.creator",
    "dc.creator.personalname",  # OpenAlex, Scopus, SemanticScholar
    "dc.contributor",
    "author",
]
_AUTHOR_AFFILIATION_META_KEYS: list[str] = [
    "citation_author_institution",
    "citation_author_affiliation",
]
_DOI_META_KEYS: list[str] = [
    "citation_doi",
    "dc.identifier",
    "dc.identifier.doi",  # OpenAlex, Scopus
    "doi",
    "prism.doi",
]
_KEYWORDS_META_KEYS: list[str] = [
    "citation_keywords",
    "citation_keyword",  # SemanticScholar uses the singular form
    "dc.subject",  # OpenAlex, SemanticScholar
    "book:tag",  # Scopus book chapters
    "keywords",
    "article:tag",
]
_DATE_META_KEYS: list[str] = [
    "citation_publication_date",
    "citation_date",
    "dc.date",
    "dc.date.issued",  # OpenAlex, Scopus, SemanticScholar
    "article:published_time",
    "prism.publicationdate",
    "citation_online_date",  # arXiv and others; used as last-resort fallback
]
_SOURCE_TITLE_KEYS: list[str] = [
    "citation_journal_title",
    "citation_conference_title",
    "citation_book_title",
    "citation_inbook_title",  # Scopus book chapters
]
_SOURCE_PUBLISHER_KEYS: list[str] = [
    "citation_publisher",
    "dc.publisher",
]
_SOURCE_ISSN_KEYS: list[str] = [
    "citation_issn",
    "prism.issn",
]
_SOURCE_ISBN_KEYS: list[str] = [
    "citation_isbn",
    "prism.isbn",
]
_PDF_URL_KEYS: list[str] = [
    "citation_pdf_url",
]

# Mapping from meta-key name to source-type identifier.
_SOURCE_KEY_TYPE_MAP: dict[str, str] = {
    "citation_journal_title": "journal",
    "citation_conference_title": "conference",
    "citation_book_title": "book",
    "citation_inbook_title": "book",
}

_FIRSTPAGE_KEY = "citation_firstpage"
_LASTPAGE_KEY = "citation_lastpage"
_NUM_PAGES_KEY = "citation_num_pages"

# Preprint server names — excluded from formal source detection.
_PREPRINT_SERVERS: frozenset[str] = frozenset({"biorxiv", "medrxiv", "arxiv"})

# Regex that locates the IEEE Xplore JS-embedded metadata blob.
_IEEE_META_RE: re.Pattern[str] = re.compile(
    r"xplGlobal\.document\.metadata\s*=\s*(\{.*?\});",
    re.DOTALL,
)

# Regex that extracts the arXiv numeric ID from an arXiv abstract URL.
# Matches /abs/NNNN.NNNNN and /abs/NNNN.NNNNNv2 (versioned).
_ARXIV_URL_RE: re.Pattern[str] = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# API-fallback regexes
# ---------------------------------------------------------------------------
# These are used when a publisher returns 403/406/418 for direct HTML scraping.
# Each pattern extracts the key needed to call the corresponding open API.

# Extracts the numeric record ID from Zenodo landing-page URLs.
# Handles both the legacy /record/ form and the current /records/ form.
_ZENODO_RECORD_RE: re.Pattern[str] = re.compile(
    r"zenodo\.org/(?:record|records)/(\d+)",
    re.IGNORECASE,
)

# Extracts the server name and DOI embedded in a bioRxiv/medRxiv content URL.
# Examples:
#   https://www.biorxiv.org/content/10.1101/2021.03.01.433431v2
#   https://www.medrxiv.org/content/10.1101/2020.05.01.20087619v1
_BIORXIV_DOI_RE: re.Pattern[str] = re.compile(
    r"(biorxiv|medrxiv)\.org/content/(10\.\d{4,}/\d{4}\.\d{2}\.\d{2}\.\d+)",
    re.IGNORECASE,
)

# HTTP status codes that trigger an API fallback attempt.
_FALLBACK_STATUS_CODES: frozenset[int] = frozenset({403, 406, 418})


def _arxiv_doi_from_url(url: str) -> str | None:
    """Derive the arXiv DOI from a landing-page URL.

    ArXiv does not embed ``citation_doi`` in its HTML meta tags.
    This helper recognises arXiv abstract/PDF URLs and constructs the
    canonical DOI ``10.48550/arXiv.<id>``.

    Parameters
    ----------
    url : str
        Landing-page URL (after any redirects).

    Returns
    -------
    str | None
        Canonical arXiv DOI, or ``None`` when the URL is not an arXiv page.
    """
    match = _ARXIV_URL_RE.search(url)
    if match:
        return f"10.48550/arXiv.{match.group(1)}"
    return None


class WebScrapingConnector(ConnectorBase):
    """Connector that extracts paper metadata directly from HTML landing pages.

    Given a URL the connector issues a browser-like HTTP GET request, parses
    ``<meta>`` tags from the HTML response, and returns a
    :class:`~findpapers.core.paper.Paper` instance built from the extracted
    metadata.

    All HTML extraction and field-parsing logic is encapsulated here as
    private class/static methods.  The only public entry points are:

    * :meth:`fetch_paper_from_url` — full HTTP + parse pipeline.
    * :meth:`build_paper_from_metadata` — assemble a ``Paper`` from a
      pre-parsed metadata dict (useful for testing individual parsers).

    Parameters
    ----------
    proxy : str | None
        Optional HTTP/HTTPS proxy URL.  When supplied all requests are routed
        through this proxy.
    ssl_verify : bool
        Whether to verify SSL certificates.  Set to ``False`` only when
        working behind institutional proxies that perform SSL inspection.
        Defaults to ``True``.
    """

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        proxy: str | None = None,
        ssl_verify: bool = True,
        url_lookup_connectors: list[URLLookupConnectorBase] | None = None,
    ) -> None:
        """Initialise the connector with optional proxy, SSL settings, and URL-lookup connectors.

        Parameters
        ----------
        proxy : str | None
            Optional HTTP/HTTPS proxy URL.  When supplied all requests are
            routed through this proxy.
        ssl_verify : bool
            Whether to verify SSL certificates.  Set to ``False`` only when
            working behind institutional proxies that perform SSL inspection.
            Defaults to ``True``.
        url_lookup_connectors : list[URLLookupConnectorBase] | None
            Optional list of connectors that support URL-based lookup.  When
            a URL passed to :meth:`fetch_paper_from_url` matches one of these
            connectors' URL patterns, the fetch is delegated to that connector
            instead of performing HTML scraping.  Connectors are checked in
            list order; the first match wins.
        """
        super().__init__()
        self._proxy = proxy
        self._ssl_verify = ssl_verify
        self._url_lookup_connectors: list[URLLookupConnectorBase] = url_lookup_connectors or []

    # ------------------------------------------------------------------
    # ConnectorBase abstract interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the connector identifier.

        Returns
        -------
        str
            Always ``"web_scraping"``.
        """
        return "web_scraping"

    @property
    def min_request_interval(self) -> float:
        """Return the minimum interval between requests.

        Web-page scraping typically targets many different hosts, so no
        single-host rate limit is enforced at this level.

        Returns
        -------
        float
            Always ``0.0``.
        """
        return 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_paper_from_url(
        self,
        url: str,
        timeout: float | None = 10.0,
    ) -> Paper | None:
        """Fetch a URL and build a :class:`~findpapers.core.paper.Paper` from its HTML.

        Sends a browser-like HTTP GET to *url*, checks that the response is
        ``text/html``, extracts ``<meta>`` tags (and IEEE JS blobs), and
        assembles a ``Paper`` from the resulting metadata dict.

        Parameters
        ----------
        url : str
            Landing-page URL to scrape.
        timeout : float | None
            HTTP request timeout in seconds.  ``None`` means no timeout.

        Returns
        -------
        Paper | None
            Paper built from the page metadata, or ``None`` when:

            * the response is not ``text/html``,
            * no parseable metadata is found, or
            * the metadata lacks a title.

        Raises
        ------
        requests.RequestException
            On network-level failures (DNS, connection refused, timeout, …).
        requests.HTTPError
            On non-2xx HTTP responses that are not handled by the API fallback
            (i.e. status codes other than 403, 406, and 418).
        """
        logger.debug("GET %s", url)
        # Before making an HTTP request, try to delegate to a structured
        # API connector that recognises this URL.
        for connector in self._url_lookup_connectors:
            if connector.supports_url(url):
                paper = connector.fetch_paper_by_url(url)
                if paper is not None:
                    logger.debug(
                        "URL %s handled by connector '%s' — skipping HTML scraping.",
                        url,
                        connector.name,
                    )
                    return paper
        try:
            response = self._make_html_request(url, timeout)
        except _CurlError as exc:
            raise requests.RequestException(str(exc)) from exc
        content_type = response.headers.get("content-type", "")
        logger.debug(
            "<- %s | content-type: %s | %d bytes",
            response.status_code,
            content_type.split(";")[0].strip() or "unknown",
            len(response.content),
        )
        if response.status_code in _FALLBACK_STATUS_CODES:
            logger.debug(
                "HTTP %s blocked — trying API fallback for %s",
                response.status_code,
                url,
            )
            return self._try_api_fallback(url, str(response.url), timeout)
        try:
            response.raise_for_status()
        except _CurlError as exc:
            raise requests.HTTPError(str(exc)) from exc
        if "text/html" not in content_type.lower():
            return None
        metadata = self._extract_metadata_from_html(response.text)
        if not metadata:
            return None
        # Use response.url (final URL after redirects) as the canonical paper URL.
        return self.build_paper_from_metadata(metadata, str(response.url))

    @classmethod
    def _build_source_from_metadata(
        cls,
        metadata: dict[str, Any],
        source_title: str | None,
    ) -> Source | None:
        """Build a :class:`~findpapers.core.source.Source` from metadata dict.

        Returns ``None`` when ``source_title`` is absent or matches a known
        preprint server name.

        Parameters
        ----------
        metadata : dict
            Metadata extracted from an HTML page.
        source_title : str | None
            Already-resolved source title string (may be ``None``).

        Returns
        -------
        Source | None
            Populated source or ``None``.
        """
        if not source_title or source_title.lower() in _PREPRINT_SERVERS:
            return None
        source_type: SourceType | None = None
        for key in _SOURCE_TITLE_KEYS:
            raw_val = metadata.get(key)
            if raw_val:
                val_str = raw_val[0].strip() if isinstance(raw_val, list) else str(raw_val).strip()
                if val_str:
                    type_str = _SOURCE_KEY_TYPE_MAP.get(key)
                    source_type = SourceType(type_str) if type_str else None
                    break
        return Source(
            title=source_title,
            issn=cls._pick_metadata_value(metadata, _SOURCE_ISSN_KEYS),
            isbn=cls._pick_metadata_value(metadata, _SOURCE_ISBN_KEYS),
            publisher=cls._pick_metadata_value(metadata, _SOURCE_PUBLISHER_KEYS),
            source_type=source_type,
        )

    @classmethod
    def build_paper_from_metadata(cls, metadata: dict[str, Any], page_url: str) -> Paper | None:
        """Assemble a :class:`~findpapers.core.paper.Paper` from a metadata dict.

        This method is public so callers can work with pre-parsed metadata
        (e.g. in tests) without going through a full HTTP fetch.

        Parameters
        ----------
        metadata : dict[str, Any]
            Metadata extracted from an HTML page (typically via
            :meth:`_extract_metadata_from_html`).
        page_url : str
            Final landing-page URL used as the paper URL.

        Returns
        -------
        Paper | None
            Populated paper instance, or ``None`` when the required title
            field is absent in *metadata*.
        """
        title = cls._pick_metadata_value(metadata, _TITLE_META_KEYS)
        if not title:
            return None

        abstract = cls._pick_metadata_value(metadata, _ABSTRACT_META_KEYS)

        # DOI — try each candidate key in priority order; normalise URL prefixes.
        doi: str | None = None
        for doi_key in _DOI_META_KEYS:
            raw = metadata.get(doi_key)
            if isinstance(raw, list):
                raw = max((str(v).strip() for v in raw if v), key=len, default=None)
            if raw:
                doi = normalize_doi(str(raw))
                if doi:
                    break

        # Fallback: derive the arXiv DOI from the landing-page URL when not
        # found in meta tags (arXiv does not embed citation_doi in its pages).
        if doi is None:
            doi = _arxiv_doi_from_url(page_url)

        authors: list[Author] = cls._build_authors_from_metadata(metadata)

        keywords: set[str] = set()
        for kw_key in _KEYWORDS_META_KEYS:
            val = metadata.get(kw_key)
            if val:
                keywords |= cls._parse_keywords(val)

        publication_date = parse_date(cls._pick_metadata_value(metadata, _DATE_META_KEYS))

        # Page range — combine first/last page with an en-dash when both present.
        first_page = (str(metadata.get(_FIRSTPAGE_KEY) or "")).strip()
        last_page = (str(metadata.get(_LASTPAGE_KEY) or "")).strip()
        if first_page and last_page:
            pages: str | None = f"{first_page}\u2013{last_page}"
        elif first_page:
            pages = first_page
        else:
            pages = None

        page_count: int | None = None
        num_pages_raw = metadata.get(_NUM_PAGES_KEY)
        if num_pages_raw:
            with contextlib.suppress(ValueError):
                page_count = int(str(num_pages_raw).strip())

        source_title = cls._pick_metadata_value(metadata, _SOURCE_TITLE_KEYS)
        source = cls._build_source_from_metadata(metadata, source_title)

        pdf_url_val = cls._pick_metadata_value(metadata, _PDF_URL_KEYS)

        # is_open_access — stored as a boolean under the private key
        # ``_is_open_access`` by source-specific parsers (e.g. IEEE, JSON-LD).
        raw_oa = metadata.get("_is_open_access")
        is_open_access: bool | None = bool(raw_oa) if raw_oa is not None else None

        return Paper(
            title=title,
            abstract=abstract or "",
            authors=authors,
            source=source,
            publication_date=publication_date,
            url=page_url,
            pdf_url=pdf_url_val,
            doi=doi,
            keywords=keywords or None,
            page_range=pages,
            page_count=page_count,
            is_open_access=is_open_access,
        )

    # ------------------------------------------------------------------
    # Private helpers — HTTP
    # ------------------------------------------------------------------

    def _get_proxies(self) -> dict[str, str] | None:
        """Build a proxies dict for *requests* when a proxy is configured.

        Returns
        -------
        dict[str, str] | None
            Proxies mapping keyed on ``"http"`` / ``"https"``, or ``None``
            when no proxy is set.
        """
        if self._proxy:
            return {"http": self._proxy, "https": self._proxy}
        return None

    def _make_html_request(self, url: str, timeout: float | None) -> _CurlResponse:
        """Issue a single browser-like HTTP GET and return the raw response.

        Uses :mod:`curl_cffi` with Chrome TLS impersonation so that the JA3
        fingerprint of every request matches a real Chrome browser.  Publishers
        protected by Akamai (PubMed/NCBI), Cloudflare (MDPI), and similar WAFs
        that gate access on the TLS fingerprint are bypassed transparently.
        A fresh :class:`curl_cffi.requests.Session` is created for every call
        so no cookies or TLS session state are shared between fetches —
        publisher CDNs track persistent sessions to bot-score sequential
        requests (e.g. IEEE Xplore sets JSESSIONID/AWSALBAPP and returns 418
        on subsequent requests carrying those cookies), so isolation is critical.

        Parameters
        ----------
        url : str
            Target URL.
        timeout : float | None
            Request timeout in seconds.  ``None`` means no timeout.

        Returns
        -------
        _CurlResponse
            Raw HTTP response (status not yet validated).

        Raises
        ------
        _CurlError
            On network-level failures (DNS, connection refused, timeout, …).
        """
        with _CurlSession(impersonate="chrome") as session:
            return session.get(  # type: ignore[no-any-return]
                url,
                proxies=self._get_proxies(),
                verify=self._ssl_verify,
                allow_redirects=True,
                timeout=timeout,
            )

    def _try_api_fallback(
        self,
        original_url: str,
        final_url: str,
        timeout: float | None,
    ) -> Paper | None:
        """Attempt to retrieve metadata via an open REST API after an HTTP block.

        When a publisher WAF returns 403/406/418, several major publishers and
        preprint servers expose their metadata through a dedicated free REST
        API.  This method checks each known host-specific API in turn.

        Priority order:

        1. **Zenodo** — ``/api/records/{id}`` (no auth, free):
           covers zenodo.org whether accessed via doi.org or directly.
        2. **bioRxiv** — ``api.biorxiv.org/details/biorxiv/{doi}``:
           covers biorxiv.org/content/... URLs.

        Parameters
        ----------
        original_url : str
            URL originally passed to :meth:`fetch_paper_from_url` (may be a
            doi.org redirect).
        final_url : str
            Final URL after redirects (the publisher's own URL).
        timeout : float | None
            Request timeout in seconds forwarded to the API call.

        Returns
        -------
        Paper | None
            Paper assembled from API data, or ``None`` when no known API
            matches the URL.
        """
        # 1. Zenodo — check both original and final URL in case of doi→zenodo
        for candidate in (final_url, original_url):
            if m := _ZENODO_RECORD_RE.search(candidate):
                logger.debug("Falling back to Zenodo API for record %s", m.group(1))
                result = self._fetch_from_zenodo_api(m.group(1), final_url, timeout)
                if result is not None:
                    return result

        # 2. bioRxiv / medRxiv (same API, different server slug)
        if m := _BIORXIV_DOI_RE.search(final_url):
            server = m.group(1).lower()
            doi_match = m.group(2)
            logger.debug("Falling back to %s API for DOI %s", server, doi_match)
            result = self._fetch_from_biorxiv_api(doi_match, final_url, timeout, server=server)
            if result is not None:
                return result

        logger.debug("No API fallback available for %s", final_url)
        return None

    @staticmethod
    def _fetch_from_zenodo_api(
        record_id: str,
        page_url: str,
        timeout: float | None,
    ) -> Paper | None:
        """Fetch paper metadata from the Zenodo REST API.

        Zenodo exposes a free, unauthenticated JSON API at
        ``https://zenodo.org/api/records/{id}`` that returns complete metadata
        even when the HTML landing page returns 403.

        Parameters
        ----------
        record_id : str
            Numeric Zenodo record identifier extracted from the landing URL.
        page_url : str
            Final landing-page URL (used as ``paper.url``).
        timeout : float | None
            Request timeout in seconds.

        Returns
        -------
        Paper | None
            Paper built from the Zenodo record, or ``None`` on error.
        """
        api_url = f"https://zenodo.org/api/records/{record_id}"
        try:
            response = requests.get(
                api_url,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except Exception:
            logger.debug("Zenodo API call failed for record %s", record_id, exc_info=True)
            return None

        meta = data.get("metadata", {})
        title = meta.get("title") or data.get("title")
        if not title:
            return None

        # Abstract — Zenodo stores it as HTML; strip tags to plain text.
        raw_description = meta.get("description") or ""
        abstract = re.sub(r"<[^>]+>", " ", raw_description).strip()

        doi = normalize_doi(meta.get("doi") or data.get("doi") or "")

        # Authors are stored as a list of {"name": ..., "affiliation": ...}
        authors: list[Author] = []
        for creator in meta.get("creators", []):
            name = (creator.get("name") or "").strip()
            if name:
                aff = (creator.get("affiliation") or "").strip()
                authors.append(Author(name=name, affiliation=aff or None))

        # Keywords — Zenodo may store them as a list or as a single
        # comma-separated string depending on the record.
        keywords: set[str] = set()
        kw_raw = meta.get("keywords")
        if isinstance(kw_raw, list):
            for item in kw_raw:
                keywords |= WebScrapingConnector._parse_keywords(item)
        elif isinstance(kw_raw, str):
            keywords = WebScrapingConnector._parse_keywords(kw_raw)

        publication_date = parse_date(meta.get("publication_date"))

        # Source — may be a journal article or conference/book chapter.
        source: Source | None = None
        journal = meta.get("journal") or {}
        if isinstance(journal, dict) and journal.get("title"):
            source = Source(
                title=journal["title"],
                issn=journal.get("issn"),
                publisher=meta.get("publisher"),
                source_type=SourceType.JOURNAL,
            )

        return Paper(
            title=title,
            abstract=abstract,
            authors=authors,
            source=source,
            publication_date=publication_date,
            url=page_url,
            doi=doi,
            keywords=keywords or None,
        )

    @staticmethod
    def _fetch_from_biorxiv_api(
        doi: str,
        page_url: str,
        timeout: float | None,
        *,
        server: str = "biorxiv",
    ) -> Paper | None:
        """Fetch paper metadata from the bioRxiv/medRxiv content API.

        Both bioRxiv and medRxiv share the same API endpoint structure at
        ``https://api.biorxiv.org/details/{server}/{doi}``.  Pass
        ``server='medrxiv'`` to query medRxiv records.

        Parameters
        ----------
        doi : str
            The preprint DOI (e.g. ``10.1101/2021.03.01.433431``), extracted
            from the landing-page URL.  Must not include a version suffix.
        page_url : str
            Final landing-page URL (used as ``paper.url``).
        timeout : float | None
            Request timeout in seconds.
        server : str, optional
            API server slug — ``'biorxiv'`` (default) or ``'medrxiv'``.

        Returns
        -------
        Paper | None
            Paper built from the record, or ``None`` when the DOI is not found
            or the API call fails.
        """
        api_url = f"https://api.biorxiv.org/details/{server}/{doi}"
        try:
            response = requests.get(
                api_url,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except Exception:
            logger.debug("%s API call failed for DOI %s", server, doi, exc_info=True)
            return None

        collection: list[dict] = data.get("collection", [])
        if not collection:
            return None

        # The collection may contain multiple versions; take the latest.
        record = collection[-1]

        title = (record.get("title") or "").strip()
        if not title:
            return None

        abstract = (record.get("abstract") or "").strip()
        record_doi = normalize_doi(record.get("doi") or doi)

        # Authors stored as a single semicolon-separated string:
        # "Doe, J.; Smith, A.; Wang, B."
        authors: list[Author] = []
        raw_authors = record.get("authors") or ""
        for raw in raw_authors.split(";"):
            name = raw.strip().rstrip(",")
            if name:
                authors.append(Author(name=name))

        publication_date = parse_date(record.get("date"))

        # category is a single discipline tag (e.g. "bioinformatics").
        raw_category = (record.get("category") or "").strip()
        keywords: set[str] | None = {raw_category} if raw_category else None

        # All bioRxiv/medRxiv submissions are preprints — they may later be
        # formally published (record["published"] != "NA"), but the entry
        # itself is always an unpublished preprint.
        paper_type = PaperType.UNPUBLISHED

        # funder field is "NA" when not reported; ignore those.
        raw_funder = (record.get("funder") or "").strip()
        funders: set[str] | None = (
            {raw_funder} if raw_funder and raw_funder.upper() != "NA" else None
        )

        # bioRxiv preprints don't have a formal journal source.
        return Paper(
            title=title,
            abstract=abstract,
            authors=authors,
            source=None,
            publication_date=publication_date,
            url=page_url,
            doi=record_doi,
            keywords=keywords,
            paper_type=paper_type,
            funders=funders,
        )

    # ------------------------------------------------------------------
    # Private helpers — HTML extraction
    # ------------------------------------------------------------------

    @classmethod
    def _extract_metadata_from_html(cls, content: str) -> dict[str, Any]:
        """Extract ``<meta>`` tag data and IEEE JS-embedded data from raw HTML.

        In addition to standard ``<meta>`` tags the method also attempts to
        extract metadata from the IEEE Xplore JS-embedded
        ``xplGlobal.document.metadata`` JSON blob.  ``<meta>`` tag values
        always take precedence over JS-derived values.

        Key normalisation applied:

        * All keys are lower-cased.
        * Dublin Core colon-form prefixes are mapped to dot-form
          (``dc:creator`` → ``dc.creator``).

        Parameters
        ----------
        content : str
            Raw HTML content.

        Returns
        -------
        dict[str, Any]
            Mapping of normalised metadata key to value (or list of values
            when the same key appears multiple times).
        """
        if not content or not content.strip():
            return {}
        doc = html.fromstring(content)
        metadata: dict[str, Any] = {}
        elements = doc.xpath("//meta[@name or @property or @itemprop]")
        if not isinstance(elements, list):  # pragma: no cover – lxml xpath always returns a list
            return metadata
        for element in elements:
            if not isinstance(element, HtmlElement):  # pragma: no cover – defensive guard
                continue
            raw_key = (
                (element.get("name") or element.get("property") or element.get("itemprop") or "")
                .strip()
                .lower()
            )
            # Normalise Dublin Core colon-form (dc:creator → dc.creator) while
            # preserving other colon-prefixed namespaces such as og:title.
            if raw_key.startswith("dc:"):
                raw_key = "dc." + raw_key[3:]
            value = (element.get("content") or "").strip()
            if not raw_key or not value:
                continue
            # Preserve multiple values for the same key as a list.
            if raw_key in metadata:
                if not isinstance(metadata[raw_key], list):
                    metadata[raw_key] = [metadata[raw_key]]
                metadata[raw_key].append(value)
            else:
                metadata[raw_key] = value
        # Supplement with IEEE-specific JS-embedded metadata.  Meta tag values
        # already in the dict take priority over JS-derived values.
        cls._merge_ieee_metadata(content, metadata)
        # Supplement with JSON-LD Schema.org data as a last-resort fallback for
        # pages (e.g. Springer books) that carry metadata only in JSON-LD.
        cls._merge_jsonld_metadata(doc, metadata)
        # Extract arXiv subject classifications as keywords when no keywords
        # were found in meta tags (arXiv pages lack citation_keywords entirely).
        cls._merge_arxiv_subjects(doc, metadata)
        # Last-resort DOI extraction: some publishers (e.g. itiis.org) display
        # the DOI as visible text with a "DOI:" prefix rather than embedding it
        # in a meta tag.  Scan the raw HTML for this pattern when no DOI key
        # has been populated by the meta-tag or source-specific parsers.
        if not any(metadata.get(k) for k in _DOI_META_KEYS):
            doi_text_match = re.search(
                r"\bDOI[:\s]+\s*(10\.\d{4,}/[^\s<>\"']+)",
                content,
                re.IGNORECASE,
            )
            if doi_text_match:
                metadata.setdefault("citation_doi", doi_text_match.group(1).rstrip(".,;)"))
        return metadata

    @classmethod
    def _merge_ieee_metadata(cls, content: str, metadata: dict[str, Any]) -> None:
        """Extract IEEE Xplore JS-blob metadata and merge into *metadata* in-place.

        IEEE Xplore pages embed all structured data inside a
        ``xplGlobal.document.metadata`` JavaScript object rather than in
        ``<meta>`` tags.  This method finds and parses that blob, then maps
        fields onto the standard ``citation_*`` key names used throughout the
        parsing pipeline.

        Only keys not already present in *metadata* are written, so that real
        ``<meta>`` tag values always take precedence.

        Parameters
        ----------
        content : str
            Raw HTML page content.
        metadata : dict[str, Any]
            Metadata dict to update in-place.

        Returns
        -------
        None
        """
        match = _IEEE_META_RE.search(content)
        if not match:
            return
        try:
            data: dict = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            return

        def _set_if_absent(key: str, value: Any) -> None:
            """Write *key*/*value* only when key is absent and value is truthy."""
            if key not in metadata and value:
                metadata[key] = value

        cls._extract_ieee_authors_data(data, metadata, _set_if_absent)

        _set_if_absent("citation_doi", data.get("doi"))
        _set_if_absent("citation_title", data.get("title") or data.get("displayDocTitle"))
        _set_if_absent("citation_abstract", data.get("abstract"))

        # Keywords — flatten all keyword groups from the nested structure.
        kw_list: list[str] = []
        for kw_group in data.get("keywords", []):
            kw_list.extend(kw_group.get("kwd", []))
        if kw_list:
            _set_if_absent("citation_keywords", ", ".join(kw_list))

        cls._extract_ieee_pub_title(data, metadata, _set_if_absent)

        _set_if_absent("citation_volume", data.get("volume"))
        _set_if_absent("citation_firstpage", data.get("startPage"))
        _set_if_absent("citation_lastpage", data.get("endPage"))
        _set_if_absent("citation_publication_date", data.get("publicationDate"))
        # IEEE books report only ``publicationYear`` (a 4-digit string such as
        # "2022") instead of a full ``publicationDate``.  Use it as a fallback
        # so the publication year is not lost for book entries.
        _set_if_absent("citation_publication_date", data.get("publicationYear"))

        # Open-access flag — IEEE embeds a boolean ``isOpenAccess`` in the JS
        # blob; store it under a private key so ``build_paper_from_metadata``
        # can pass it to ``Paper(is_open_access=...)``.
        # Use direct assignment (not _set_if_absent) because False is a valid
        # value that _set_if_absent would skip as falsy.
        oa_val = data.get("isOpenAccess")
        if oa_val is not None and "_is_open_access" not in metadata:
            metadata["_is_open_access"] = bool(oa_val)

        # PDF URL — prepend domain for relative paths.
        pdf_path = data.get("pdfPath") or data.get("pdfUrl")
        if pdf_path and str(pdf_path).startswith("/"):
            _set_if_absent("citation_pdf_url", f"https://ieeexplore.ieee.org{pdf_path}")

        # ISSN — pick the first available value.
        for issn_entry in data.get("issn", []):
            val = issn_entry.get("value")
            if val:
                _set_if_absent("citation_issn", val)
                break

        _set_if_absent("citation_publisher", data.get("publisher"))

    @classmethod
    def _extract_ieee_authors_data(
        cls,
        data: dict[str, Any],
        metadata: dict[str, Any],
        _set_if_absent: Any,
    ) -> None:
        """Extract authors and affiliations from an IEEE JS-blob data dict.

        Parameters
        ----------
        data : dict
            Parsed IEEE JS-blob.
        metadata : dict
            Metadata dict to update in-place.
        _set_if_absent : callable
            Helper that writes a key only when absent.

        Returns
        -------
        None
        """
        authors = [a.get("name", "").strip() for a in data.get("authors", []) if a.get("name")]
        if authors:
            _set_if_absent("citation_author", authors if len(authors) > 1 else authors[0])
        affiliations: list[str] = []
        for a in data.get("authors", []):
            if not a.get("name"):
                continue
            raw_aff = a.get("affiliation") or ""
            if isinstance(raw_aff, list):
                aff_str = "; ".join(s.strip() for s in raw_aff if isinstance(s, str) and s.strip())
            else:
                aff_str = str(raw_aff).strip()
            affiliations.append(aff_str)
        if affiliations and any(affiliations):
            _set_if_absent(
                "citation_author_institution",
                affiliations if len(affiliations) > 1 else affiliations[0],
            )

    @classmethod
    def _extract_ieee_pub_title(
        cls,
        data: dict[str, Any],
        metadata: dict[str, Any],
        _set_if_absent: Any,
    ) -> None:
        """Map IEEE publication title to the right citation_* key.

        Parameters
        ----------
        data : dict
            Parsed IEEE JS-blob.
        metadata : dict
            Metadata dict to update in-place.
        _set_if_absent : callable
            Helper that writes a key only when absent.

        Returns
        -------
        None
        """
        pub_title = data.get("displayPublicationTitle") or data.get("publicationTitle")
        if not pub_title:
            return
        if data.get("isJournal") or data.get("contentType", "").lower() == "periodicals":
            _set_if_absent("citation_journal_title", pub_title)
        elif data.get("isConference"):
            _set_if_absent("citation_conference_title", pub_title)
        elif data.get("isBook") or data.get("isBookWithoutChapters"):
            _set_if_absent("citation_book_title", pub_title)
        else:
            _set_if_absent("citation_journal_title", pub_title)

    @classmethod
    def _merge_jsonld_metadata(cls, doc: HtmlElement, metadata: dict[str, Any]) -> None:
        """Extract Schema.org JSON-LD data and merge into *metadata* in-place.

        Many publishers embed structured metadata in a
        ``<script type="application/ld+json">`` block using Schema.org types
        such as ``ScholarlyArticle``, ``Article``, ``Book``, or ``Chapter``.
        This method parses the first usable such block and maps its fields onto
        the standard internal key names.

        Only keys not already present in *metadata* are written, so that real
        ``<meta>`` tag values always take precedence.

        Parameters
        ----------
        doc : HtmlElement
            Parsed lxml HTML document.
        metadata : dict[str, Any]
            Metadata dict to update in-place.

        Returns
        -------
        None
        """
        # The types we consider as academic-paper records.
        _SCHOLARLY_TYPES = frozenset(
            {
                "scholarlyarticle",
                "article",
                "chapter",
                "book",
                "creativework",
            }
        )

        def _set_if_absent(key: str, value: Any) -> None:
            """Write *key*/*value* only when key is absent and value is truthy."""
            if key not in metadata and value:
                metadata[key] = value

        scripts = doc.xpath("//script[@type='application/ld+json']/text()")
        if not isinstance(scripts, list):
            return

        for script_text in scripts:
            try:
                data: dict = json.loads(script_text)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            raw_type = data.get("@type", "")
            types = [raw_type] if isinstance(raw_type, str) else raw_type
            types_lower = {str(t).lower() for t in types}
            if not types_lower.intersection(_SCHOLARLY_TYPES):
                # Descend into mainEntity if present (e.g. WebPage wrapping a
                # ScholarlyArticle).
                main_entity = data.get("mainEntity")
                if isinstance(main_entity, dict):
                    inner_type = str(main_entity.get("@type", "")).lower()
                    if inner_type in _SCHOLARLY_TYPES:
                        data = main_entity
                        types_lower = {inner_type}
                    else:
                        continue
                else:
                    continue

            # Title
            title = data.get("headline") or data.get("name") or data.get("title")
            if title:
                _set_if_absent("citation_title", str(title).strip())

            # Abstract
            description = data.get("description") or data.get("abstract")
            if description:
                _set_if_absent("citation_abstract", str(description).strip())

            cls._extract_jsonld_doi(data, metadata, _set_if_absent)
            cls._extract_jsonld_authors(data, metadata, _set_if_absent)

            # Publication date.
            date_raw = data.get("datePublished") or data.get("dateCreated")
            if date_raw:
                _set_if_absent("citation_publication_date", str(date_raw).strip())

            cls._extract_jsonld_keywords(data, metadata, _set_if_absent)
            cls._extract_jsonld_source_fields(data, metadata, _set_if_absent)

            # Open-access flag — Schema.org uses ``isAccessibleForFree``.
            # Use direct assignment (not _set_if_absent) because False is a
            # valid value that _set_if_absent would skip as falsy.
            oa_val = data.get("isAccessibleForFree")
            if oa_val is not None and "_is_open_access" not in metadata:
                metadata["_is_open_access"] = bool(oa_val)

            # Once the first usable JSON-LD block is processed, stop.
            break

    @classmethod
    def _extract_jsonld_doi(
        cls,
        data: dict[str, Any],
        metadata: dict[str, Any],
        _set_if_absent: Any,
    ) -> None:
        """Extract DOI from a JSON-LD data dict and write into *metadata*.

        Parameters
        ----------
        data : dict
            Parsed JSON-LD block.
        metadata : dict
            Metadata dict to update in-place.
        _set_if_absent : callable
            Helper that writes a key only when absent.

        Returns
        -------
        None
        """
        doi_raw = data.get("doi") or data.get("identifier")
        if isinstance(doi_raw, dict):
            if (
                str(doi_raw.get("propertyID", "")).upper() == "DOI"
                or str(doi_raw.get("@type", "")).lower() == "propertyvalue"
            ):
                doi_raw = doi_raw.get("value")
            else:
                doi_raw = None
        elif isinstance(doi_raw, list):
            doi_raw = next(
                (
                    item
                    if isinstance(item, str)
                    else (
                        item.get("value")
                        if isinstance(item, dict)
                        and str(item.get("propertyID", "")).upper() == "DOI"
                        else None
                    )
                    for item in doi_raw
                ),
                None,
            )
        if doi_raw:
            _set_if_absent("citation_doi", str(doi_raw).strip())

        # DOI fallback via @id
        if "citation_doi" not in metadata:
            at_id = str(data.get("@id") or "")
            doi_in_id = re.search(
                r"(?:doi\.org/|/doi/)((10\.\d{4,}/[^/?&#\s]+))",
                at_id,
            )
            if doi_in_id:
                _set_if_absent("citation_doi", doi_in_id.group(1).rstrip("/"))

    @classmethod
    def _extract_jsonld_authors(
        cls,
        data: dict[str, Any],
        metadata: dict[str, Any],
        _set_if_absent: Any,
    ) -> None:
        """Extract authors and affiliations from a JSON-LD data dict.

        Parameters
        ----------
        data : dict
            Parsed JSON-LD block.
        metadata : dict
            Metadata dict to update in-place.
        _set_if_absent : callable
            Helper that writes a key only when absent.

        Returns
        -------
        None
        """
        authors_raw = data.get("author") or data.get("creator")
        if not authors_raw:
            authors_raw = data.get("editor")
        if isinstance(authors_raw, list):
            names = [
                str(a.get("name", "")).strip()
                for a in authors_raw
                if isinstance(a, dict) and a.get("name")
            ]
            if names:
                _set_if_absent("citation_author", names if len(names) > 1 else names[0])
            affiliations: list[str] = []
            for author in authors_raw:
                if not isinstance(author, dict):
                    affiliations.append("")
                    continue
                aff_raw = author.get("affiliation")
                if isinstance(aff_raw, list):
                    aff_str = "; ".join(
                        str(a.get("name", a) if isinstance(a, dict) else a).strip()
                        for a in aff_raw
                        if a
                    )
                elif isinstance(aff_raw, dict):
                    aff_str = str(aff_raw.get("name", "")).strip()
                else:
                    aff_str = str(aff_raw or "").strip()
                affiliations.append(aff_str)
            if any(affiliations):
                _set_if_absent(
                    "citation_author_institution",
                    affiliations if len(affiliations) > 1 else affiliations[0],
                )
        elif isinstance(authors_raw, str):
            _set_if_absent("citation_author", authors_raw.strip())

    @classmethod
    def _extract_jsonld_keywords(
        cls,
        data: dict[str, Any],
        metadata: dict[str, Any],
        _set_if_absent: Any,
    ) -> None:
        """Extract keywords from a JSON-LD data dict.

        Parameters
        ----------
        data : dict
            Parsed JSON-LD block.
        metadata : dict
            Metadata dict to update in-place.
        _set_if_absent : callable
            Helper that writes a key only when absent.

        Returns
        -------
        None
        """
        kw_raw = data.get("keywords")
        if isinstance(kw_raw, list):
            kw_str = ", ".join(str(k).strip() for k in kw_raw if k)
        elif isinstance(kw_raw, str):
            kw_str = kw_raw.strip()
        else:
            kw_str = ""
        if kw_str:
            _set_if_absent("citation_keywords", kw_str)

    @classmethod
    def _extract_jsonld_source_fields(
        cls,
        data: dict[str, Any],
        metadata: dict[str, Any],
        _set_if_absent: Any,
    ) -> None:
        """Extract publisher, ISBN and journal fields from a JSON-LD data dict.

        Parameters
        ----------
        data : dict
            Parsed JSON-LD block.
        metadata : dict
            Metadata dict to update in-place.
        _set_if_absent : callable
            Helper that writes a key only when absent.

        Returns
        -------
        None
        """
        publisher_raw = data.get("publisher")
        if isinstance(publisher_raw, dict):
            _set_if_absent("citation_publisher", str(publisher_raw.get("name", "")).strip())
        elif isinstance(publisher_raw, str):
            _set_if_absent("citation_publisher", publisher_raw.strip())

        isbn_raw = data.get("isbn") or data.get("ISBN")
        if isbn_raw:
            _set_if_absent("citation_isbn", str(isbn_raw).strip())

    # ------------------------------------------------------------------
    # Private helpers — field parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_metadata_value(metadata: dict[str, Any], keys: list[str]) -> str | None:
        """Return the first non-empty value for any of the candidate keys.

        Parameters
        ----------
        metadata : dict[str, Any]
            Metadata mapping.
        keys : list[str]
            Candidate keys in priority order.

        Returns
        -------
        str | None
            First matched value, or ``None``.
        """
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, list):
                values = [str(item).strip() for item in value if item]
                selected = max(values, key=len, default=None)
            else:
                selected = str(value).strip() if value is not None else None
            if selected:
                return selected
        return None

    @classmethod
    def _merge_arxiv_subjects(cls, doc: HtmlElement, metadata: dict[str, Any]) -> None:
        """Extract arXiv subject classifications and store them as keywords.

        ArXiv abstract pages list the subject categories (e.g.
        ``"Computer Vision and Pattern Recognition (cs.CV)"``) in a table cell
        with class ``tablecell subjects`` rather than in any ``<meta>`` tag.
        When no keywords have already been found this method uses those
        classifications as a substitute.

        The method is a no-op for non-arXiv pages because the XPath selector
        will not match any element.

        Only writes ``citation_keywords`` when it is not yet present in
        *metadata* and at least one subject is found.

        Parameters
        ----------
        doc : HtmlElement
            Parsed lxml HTML document.
        metadata : dict[str, Any]
            Metadata dict to update in-place.

        Returns
        -------
        None
        """
        if any(metadata.get(k) for k in _KEYWORDS_META_KEYS):
            return  # keywords already present — nothing to do

        subjects_cells = doc.xpath("//td[contains(@class, 'subjects')]")
        if not isinstance(subjects_cells, list) or not subjects_cells:
            return

        subjects_text = (subjects_cells[0].text_content() or "").strip()
        if subjects_text:
            metadata.setdefault("citation_keywords", subjects_text)

    @staticmethod
    def _parse_authors(value: Any) -> list[str]:
        """Normalise author metadata into a flat list of strings.

        Handles three forms:

        * ``list`` — already split (e.g. multiple ``citation_author`` tags).
          Each list item may itself be semicolon-separated.
        * ``str`` with semicolons — PubMed-style ``"Wang Y;Tian J;..."``.
        * plain ``str`` — a single author name.

        Parameters
        ----------
        value : Any
            Raw author data (str, list, or ``None``).

        Returns
        -------
        list[str]
            Stripped, deduplicated author names in original order.
        """
        if value is None:
            return []
        if isinstance(value, list):
            result: list[str] = []
            seen: set[str] = set()
            for item in value:
                for part in str(item).split(";"):
                    name = part.strip()
                    if name and name not in seen:
                        result.append(name)
                        seen.add(name)
            return result
        return [part.strip() for part in str(value).split(";") if part.strip()]

    @staticmethod
    def _parse_affiliations(value: Any) -> list[str]:
        """Normalise affiliation metadata into a flat list of strings.

        Works similarly to :meth:`_parse_authors`: handles ``list``,
        semicolon-separated ``str``, and single-string forms.

        Parameters
        ----------
        value : Any
            Raw affiliation data (str, list, or ``None``).

        Returns
        -------
        list[str]
            Stripped affiliation strings in original order.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [part.strip() for part in str(value).split(";") if part.strip()]

    @classmethod
    def _build_authors_from_metadata(cls, metadata: dict[str, Any]) -> list[Author]:
        """Build :class:`Author` objects pairing names with affiliations.

        Author names are resolved from :attr:`_AUTHOR_META_KEYS`, and
        affiliations from :attr:`_AUTHOR_AFFILIATION_META_KEYS`.  When both
        lists are present they are paired positionally; surplus names receive
        no affiliation.

        Parameters
        ----------
        metadata : dict[str, Any]
            Extracted HTML metadata.

        Returns
        -------
        list[Author]
            Author objects with affiliations where available.
        """
        names: list[str] = []
        for key in _AUTHOR_META_KEYS:
            raw = metadata.get(key)
            if raw:
                names = cls._parse_authors(raw)
                if names:
                    break

        affiliations: list[str] = []
        for key in _AUTHOR_AFFILIATION_META_KEYS:
            raw = metadata.get(key)
            if raw:
                affiliations = cls._parse_affiliations(raw)
                if affiliations:
                    break

        authors: list[Author] = []
        for idx, name in enumerate(names):
            affiliation = affiliations[idx] if idx < len(affiliations) else None
            authors.append(Author(name=name, affiliation=affiliation))
        return authors

    @staticmethod
    def _parse_keywords(value: str | list | None) -> set[str]:
        """Parse keyword metadata into a set of strings.

        Handles three forms:

        * ``list`` — each item may itself be comma- or semicolon-delimited.
        * ``str`` with commas or semicolons — a delimited keyword string.
        * plain ``str`` — a single keyword.

        Parameters
        ----------
        value : str | list | None
            Raw keyword data.

        Returns
        -------
        set[str]
            Parsed, stripped keyword set.
        """
        if not value:
            return set()
        if isinstance(value, list):
            result: set[str] = set()
            for item in value:
                result |= WebScrapingConnector._parse_keywords(item)
            return result
        if "," in value:
            parts = value.split(",")
        elif ";" in value:
            parts = value.split(";")
        else:
            parts = [value]
        return {part.strip() for part in parts if part.strip()}
