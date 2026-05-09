"""Web of Science Starter API connector."""

from __future__ import annotations

import contextlib
import datetime
import logging
import re
from collections.abc import Callable
from typing import Any

import requests

from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.search_base import SearchConnectorBase
from findpapers.connectors.url_lookup_base import URLLookupConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Database, Paper, PaperType
from findpapers.core.query import Query
from findpapers.core.source import Source, SourceType
from findpapers.exceptions import MissingApiKeyError
from findpapers.query.builder import QueryBuilder
from findpapers.query.builders.wos import WosQueryBuilder

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1"
# WoS Starter Free Trial allows 1 req/s; institutional plans allow up to 5
# req/s.  We use the conservative Free Trial rate as the default.
_MIN_REQUEST_INTERVAL = 1.0
# Maximum results per page (API hard limit is 50).
_PAGE_SIZE = 50

# Regex matching Web of Science record URLs.  Captures the WoS UID (e.g.
# ``WOS:000282418500002``) from both the modern and legacy URL formats:
#   https://www.webofscience.com/wos/woscc/full-record/WOS:000282418500002
#   https://webofscience.com/wos/woscc/full-record/WOS:000282418500002
#   https://www.webofscience.com/wos/WOS:000282418500002
_WOS_URL_RE = re.compile(
    r"webofscience\.com/.*(?:full-record/|/wos/)?(WOS:[A-Z0-9]+)",
    re.IGNORECASE,
)

# Mapping from WoS document type strings (lowered) to PaperType.
_WOS_PAPER_TYPE_MAP: dict[str, PaperType] = {
    "article": PaperType.ARTICLE,
    "review": PaperType.ARTICLE,
    "review article": PaperType.ARTICLE,
    "letter": PaperType.ARTICLE,
    "editorial material": PaperType.ARTICLE,
    "editorial": PaperType.ARTICLE,
    "correction": PaperType.ARTICLE,
    "retraction": PaperType.ARTICLE,
    "note": PaperType.ARTICLE,
    "proceedings paper": PaperType.INPROCEEDINGS,
    "meeting": PaperType.INPROCEEDINGS,
    "meeting abstract": PaperType.INPROCEEDINGS,
    "conference paper": PaperType.INPROCEEDINGS,
    "book": PaperType.BOOK,
    "book chapter": PaperType.INBOOK,
    "book review": PaperType.INBOOK,
    "dissertation": PaperType.PHDTHESIS,
    "thesis": PaperType.PHDTHESIS,
    "phd thesis": PaperType.PHDTHESIS,
    "masters thesis": PaperType.MASTERSTHESIS,
    "technical report": PaperType.TECHREPORT,
    "report": PaperType.TECHREPORT,
    "preprint": PaperType.UNPUBLISHED,
    "data paper": PaperType.MISC,
    "software review": PaperType.MISC,
    "bibliography": PaperType.MISC,
    "other": PaperType.MISC,
}

# Mapping from WoS sourceType strings (lowered) to SourceType.
# The Starter API returns document-oriented values in sourceTypes (e.g.
# "Article", "Review", "Proceedings Paper") rather than publication-venue
# values ("Journal", "Conference").  Both sets are mapped here so that
# all known real-world responses are handled correctly.
_WOS_SOURCE_TYPE_MAP: dict[str, SourceType] = {
    # Venue-oriented values (older / institutional plan responses)
    "journal": SourceType.JOURNAL,
    "conference": SourceType.CONFERENCE,
    "conference proceedings": SourceType.CONFERENCE,
    "book": SourceType.BOOK,
    "book series": SourceType.BOOK,
    # Document-oriented values as returned by the Starter API in practice
    "article": SourceType.JOURNAL,
    "review": SourceType.JOURNAL,
    "proceedings paper": SourceType.CONFERENCE,
    "meeting": SourceType.CONFERENCE,
}

# Textual month abbreviations returned by WoS (including seasons and
# bi-monthly periods) mapped to a representative calendar month number.
_WOS_MONTH_MAP: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
    # Seasons
    "WIN": 1,
    "SPR": 4,
    "SUM": 7,
    "FAL": 10,
    "FALL": 10,
    "AUT": 10,
    # Bi-monthly periods
    "JAN-FEB": 1,
    "MAR-APR": 3,
    "MAY-JUN": 5,
    "JUL-AUG": 7,
    "SEP-OCT": 9,
    "NOV-DEC": 11,
}


def _parse_wos_date(year: int | None, month_str: str | None) -> datetime.date | None:
    """Convert WoS year and month string to a :class:`datetime.date`.

    Parameters
    ----------
    year : int | None
        Publication year as returned by the WoS API.
    month_str : str | None
        Textual month (e.g. ``"JUN"``, ``"SPR"``, ``"JAN-FEB"``) or ``None``.

    Returns
    -------
    datetime.date | None
        First day of the resolved month, or ``None`` when *year* is absent.
    """
    if not year:
        return None
    month = 1
    if month_str:
        month = _WOS_MONTH_MAP.get(month_str.upper().strip(), 1)
    with contextlib.suppress(ValueError, TypeError):
        return datetime.date(int(year), month, 1)
    return None


def _extract_citation_count(citations_list: list[dict]) -> int | None:
    """Extract the WoS Core times-cited count from the citations list.

    Parameters
    ----------
    citations_list : list[dict]
        The ``citations`` array from a WoS document hit.

    Returns
    -------
    int | None
        Citation count, or ``None`` when absent (e.g. Free Trial plan).
    """
    for entry in citations_list:
        if entry.get("db", "").upper() == "WOS":
            count = entry.get("count")
            if count is not None:
                with contextlib.suppress(ValueError, TypeError):
                    return int(count)
    return None


class WosConnector(SearchConnectorBase, DOILookupConnectorBase, URLLookupConnectorBase):
    """Connector for the Clarivate Web of Science Starter API.

    Implements search, DOI lookup, and URL lookup against the
    ``/documents`` endpoint.  An API key is required; free trial keys
    are available at https://developer.clarivate.com/apis/wos-starter.

    Limitations
    -----------
    - Abstracts are **not** returned by the Starter API.  The
      ``abstract`` field will be ``None`` unless filled by enrichment.
    - Author affiliations are not available from this endpoint.
    - Citation counts are only returned for institutional-plan keys.
      Free Trial keys always receive no citation data.
    - Snowball / citation graph lookups are not supported; the Starter
      API provides only UI links for citing articles and references.
    """

    def __init__(
        self,
        query_builder: WosQueryBuilder | None = None,
        api_key: str | None = None,
    ) -> None:
        """Create a Web of Science Starter connector.

        Parameters
        ----------
        query_builder : WosQueryBuilder | None
            Builder used to validate and convert queries.  When ``None`` a
            default :class:`WosQueryBuilder` is created automatically.
        api_key : str | None
            Clarivate API key (required).

        Raises
        ------
        MissingApiKeyError
            When *api_key* is ``None`` or blank.
        """
        super().__init__()
        self._query_builder: WosQueryBuilder = query_builder or WosQueryBuilder()
        if not api_key or not api_key.strip():
            raise MissingApiKeyError(
                "WosConnector requires an api_key. "
                "Obtain one at https://developer.clarivate.com/apis/wos-starter"
            )
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database name string (``"wos"``).
        """
        return Database.WOS.value

    @property
    def query_builder(self) -> QueryBuilder:
        """Return the WoS query builder.

        Returns
        -------
        QueryBuilder
            The underlying builder instance.
        """
        return self._query_builder

    @property
    def min_request_interval(self) -> float:
        """Return the minimum seconds between HTTP requests.

        Returns
        -------
        float
            Interval in seconds (defaults to 1.0 for Free Trial rate limit).
        """
        return _MIN_REQUEST_INTERVAL

    # ------------------------------------------------------------------
    # Credential injection
    # ------------------------------------------------------------------

    def _prepare_headers(self, headers: dict) -> dict:
        """Inject the WoS API key header.

        Parameters
        ----------
        headers : dict
            Raw HTTP headers.

        Returns
        -------
        dict
            Headers with ``X-ApiKey`` added.
        """
        updated = super()._prepare_headers(headers)
        updated["X-ApiKey"] = self._api_key
        return updated

    # ------------------------------------------------------------------
    # URL lookup
    # ------------------------------------------------------------------

    @property
    def url_pattern(self) -> re.Pattern[str]:
        """Return the regex matching Web of Science record URLs.

        Returns
        -------
        re.Pattern[str]
            Compiled pattern whose first capture group is the WoS UID.
        """
        return _WOS_URL_RE

    def fetch_paper_by_id(self, paper_id: str) -> Paper | None:
        """Fetch a single paper by its WoS accession number (UID).

        Parameters
        ----------
        paper_id : str
            WoS UID (e.g. ``"WOS:000282418500002"``).

        Returns
        -------
        Paper | None
            Populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the record is not found or cannot be parsed.
        """
        url = f"{_BASE_URL}/documents/{paper_id}"
        try:
            response = self._get(url)
            data = response.json()
        except (requests.RequestException, ValueError):
            logger.debug("WoS: failed to fetch UID %s.", paper_id)
            return None

        # The single-document endpoint returns the document object directly
        # (not wrapped in a ``hits`` array).
        return self._parse_document(data)

    # ------------------------------------------------------------------
    # DOI lookup
    # ------------------------------------------------------------------

    def fetch_paper_by_doi(self, doi: str) -> Paper | None:
        """Fetch a single paper by its DOI from Web of Science.

        Parameters
        ----------
        doi : str
            Bare DOI identifier (e.g. ``"10.1038/nature14539"``).

        Returns
        -------
        Paper | None
            Populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the DOI is not found or the response cannot be parsed.
        """
        params = {"q": f"DO={doi}", "limit": 1, "db": "WOS"}
        try:
            response = self._get(f"{_BASE_URL}/documents", params=params)
            data = response.json()
        except (requests.RequestException, ValueError):
            logger.debug("WoS: failed to fetch DOI %s.", doi)
            return None

        hits = data.get("hits") or []
        if not hits:
            logger.debug("WoS: DOI %s not found.", doi)
            return None

        return self._parse_document(hits[0])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _fetch_papers(
        self,
        query: Query,
        max_papers: int | None,
        progress_callback: Callable[[int, int | None], None] | None,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
    ) -> list[Paper]:
        """Fetch papers from WoS with pagination.

        Parameters
        ----------
        query : Query
            Validated query object.
        max_papers : int | None
            Maximum papers to retrieve.
        progress_callback : Callable[[int, int | None], None] | None
            Progress callback invoked with ``(fetched, total)``.
        since : datetime.date | None
            Lower-bound publication date filter (inclusive).
        until : datetime.date | None
            Upper-bound publication date filter (inclusive).

        Returns
        -------
        list[Paper]
            Retrieved papers in reverse-publication-year order.
        """
        wos_query = self._query_builder.convert_query(query)

        # Date filter: append ``PY=(since_year-until_year)`` to the query
        # string rather than using the ``publishTimeSpan`` request parameter.
        # ``publishTimeSpan`` filters by the "early access" / online-first
        # date, which can pre-date the formal ``publishYear`` by months or
        # years.  Because we parse ``publishYear`` into ``publication_date``,
        # using ``publishTimeSpan`` causes the engine's post-fetch filter to
        # drop valid "early access" papers (e.g. a paper online in 2023 that
        # has ``publishYear=2024``).  The ``PY`` query field maps 1-to-1 to
        # ``publishYear`` so the API and post-fetch filters agree.
        if since is not None or until is not None:
            since_year = since.year if since is not None else 1900
            until_year = until.year if until is not None else datetime.date.today().year + 1
            wos_query = f"({wos_query}) AND PY=({since_year}-{until_year})"

        base_params: dict[str, Any] = {
            "q": wos_query,
            "db": "WOS",
            "limit": _PAGE_SIZE,
            # Sort newest-first so the most recent papers are retrieved when
            # max_papers caps the search.
            "sortField": "PY+D",
        }

        papers: list[Paper] = []
        processed = 0
        page = 1
        total: int | None = None

        while True:
            remaining = (max_papers - len(papers)) if max_papers is not None else _PAGE_SIZE
            page_size = min(_PAGE_SIZE, remaining)

            params = {**base_params, "limit": page_size, "page": page}

            try:
                response = self._get(f"{_BASE_URL}/documents", params=params)
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                logger.warning("WoS request failed (page=%d): %s", page, exc)
                logger.debug("WoS request exception details:", exc_info=True)
                break

            metadata = data.get("metadata") or {}
            if total is None:
                total = metadata.get("total")

            hits = data.get("hits") or []
            if not hits:
                break

            for hit in hits:
                paper = self._parse_document(hit)
                if paper is not None:
                    papers.append(paper)

            processed += len(hits)
            if progress_callback is not None:
                progress_callback(processed, total)

            if max_papers is not None and len(papers) >= max_papers:
                break

            if len(hits) < page_size:
                break

            page += 1

        # Ensure progress callback is always called at least once so that
        # callers see a final update even when the first page is empty.
        if progress_callback is not None:
            progress_callback(processed, total)

        return papers[:max_papers] if max_papers is not None else papers

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_wos_source(doc: dict[str, Any]) -> Source | None:
        """Build a :class:`~findpapers.core.source.Source` from WoS metadata.

        Parameters
        ----------
        doc : dict
            WoS ``hit`` document dict.

        Returns
        -------
        Source | None
            Populated source or ``None`` when no title is present.
        """
        source_meta = doc.get("source") or {}
        source_title = (source_meta.get("sourceTitle") or "").strip()
        if not source_title:
            return None
        issn, eissn, isbn = WosConnector._parse_wos_issn_isbn(doc)
        source_type = WosConnector._parse_wos_source_type(doc)
        return Source(
            title=source_title,
            issn=issn or eissn or None,
            isbn=isbn,
            source_type=source_type,
        )

    @staticmethod
    def _parse_wos_issn_isbn(
        doc: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None]:
        """Extract ISSN, eISSN, and ISBN from WoS identifiers.

        Parameters
        ----------
        doc : dict
            WoS ``hit`` document dict.

        Returns
        -------
        tuple[str | None, str | None, str | None]
            ``(issn, eissn, isbn)``.
        """
        identifiers = doc.get("identifiers") or {}
        issn = (identifiers.get("issn") or "").strip() or None
        eissn = (identifiers.get("eissn") or "").strip() or None
        isbn = (identifiers.get("isbn") or "").strip() or None
        return issn, eissn, isbn

    @staticmethod
    def _parse_wos_source_type(doc: dict[str, Any]) -> SourceType | None:
        """Determine the :class:`~findpapers.core.source.SourceType` for a WoS record.

        Parameters
        ----------
        doc : dict
            WoS ``hit`` document dict.

        Returns
        -------
        SourceType | None
            Matched source type or ``None``.
        """
        raw_types: list[str] = [(t or "").lower() for t in (doc.get("sourceTypes") or [])]
        return next(
            (_WOS_SOURCE_TYPE_MAP[t] for t in raw_types if t in _WOS_SOURCE_TYPE_MAP),
            None,
        )

    @staticmethod
    def _parse_wos_pages(doc: dict[str, Any]) -> tuple[str | None, int | None]:
        """Extract page range and page count from WoS metadata.

        Parameters
        ----------
        doc : dict
            WoS ``hit`` document dict.

        Returns
        -------
        tuple[str | None, int | None]
            ``(page_range, page_count)`` pair.
        """
        source_meta = doc.get("source") or {}
        pages_meta = source_meta.get("pages") or {}
        page_range: str | None = (pages_meta.get("range") or "").strip() or None
        page_count: int | None = None
        raw_count = pages_meta.get("count")
        if raw_count is not None:
            with contextlib.suppress(ValueError, TypeError):
                page_count = int(raw_count)
        return page_range, page_count

    def _parse_document(self, doc: dict[str, Any]) -> Paper | None:
        """Parse a single WoS API document object into a :class:`Paper`.

        Parameters
        ----------
        doc : dict
            A ``hit`` object from the WoS ``/documents`` endpoint.

        Returns
        -------
        Paper | None
            Parsed paper, or ``None`` when required fields are missing or
            the paper object cannot be constructed.
        """
        title = (doc.get("title") or "").strip()
        if not title:
            return None

        authors = WosConnector._parse_wos_authors(doc)
        source_meta = doc.get("source") or {}
        pub_date = _parse_wos_date(
            source_meta.get("publishYear"),
            source_meta.get("publishMonth"),
        )
        identifiers = doc.get("identifiers") or {}
        doi: str | None = (identifiers.get("doi") or "").strip() or None
        links = doc.get("links") or {}
        url: str | None = (links.get("record") or "").strip() or None
        keywords = WosConnector._parse_wos_keywords(doc)
        citations = _extract_citation_count(doc.get("citations") or [])
        source = self._parse_wos_source(doc)
        raw_types: list[str] = [(t or "").lower() for t in (doc.get("types") or [])]
        paper_type: PaperType | None = next(
            (_WOS_PAPER_TYPE_MAP[t] for t in raw_types if t in _WOS_PAPER_TYPE_MAP),
            None,
        )
        page_range, page_count = self._parse_wos_pages(doc)

        try:
            paper = Paper(
                title=title,
                abstract="",
                authors=authors,
                source=source,
                publication_date=pub_date,
                url=url,
                doi=doi,
                citations=citations,
                keywords=keywords if keywords else None,
                page_range=page_range,
                page_count=page_count,
                databases={self.name},
                paper_type=paper_type,
            )
        except ValueError:
            return None

        return paper

    @staticmethod
    def _parse_wos_authors(doc: dict[str, Any]) -> list[Author]:
        """Extract authors from WoS document metadata.

        Parameters
        ----------
        doc : dict
            WoS ``hit`` document dict.

        Returns
        -------
        list[Author]
            Parsed author list.
        """
        authors: list[Author] = []
        names = doc.get("names") or {}
        for author_entry in names.get("authors") or []:
            display_name = (author_entry.get("displayName") or "").strip()
            if display_name:
                authors.append(Author(name=display_name))
        return authors

    @staticmethod
    def _parse_wos_keywords(doc: dict[str, Any]) -> set[str]:
        """Extract author-provided keywords from WoS document metadata.

        Parameters
        ----------
        doc : dict
            WoS ``hit`` document dict.

        Returns
        -------
        set[str]
            Set of cleaned keyword strings.
        """
        keywords_data = doc.get("keywords") or {}
        keywords: set[str] = set()
        for kw in keywords_data.get("authorKeywords") or []:
            kw_clean = (kw or "").strip()
            if kw_clean:
                keywords.add(kw_clean)
        return keywords
