"""Scopus searcher implementation."""

from __future__ import annotations

import contextlib
import datetime
import logging
from collections.abc import Callable
from typing import Any

import requests

from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.search_base import SearchConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Database, Paper, PaperType
from findpapers.core.query import Query
from findpapers.core.source import Source, SourceType
from findpapers.exceptions import MissingApiKeyError
from findpapers.query.builder import QueryBuilder
from findpapers.query.builders.scopus import ScopusQueryBuilder

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.elsevier.com/content/search/scopus"
_PAGE_SIZE = 25  # Scopus max results per request (in standard view)
# Conservative interval — actual limit varies by institution
_MIN_REQUEST_INTERVAL = 0.5

# Mapping from Scopus prism:aggregationType values to SourceType.
_SCOPUS_AGGREGATION_TYPE_MAP: dict[str, SourceType] = {
    "journal": SourceType.JOURNAL,
    "conference proceeding": SourceType.CONFERENCE,
    "book": SourceType.BOOK,
    "book series": SourceType.BOOK,
    "trade journal": SourceType.JOURNAL,
}

# Mapping from Scopus subtypeDescription (lowered) to PaperType.
_SCOPUS_PAPER_TYPE_MAP: dict[str, PaperType] = {
    "article": PaperType.ARTICLE,
    "review": PaperType.ARTICLE,
    "short survey": PaperType.ARTICLE,
    "letter": PaperType.ARTICLE,
    "note": PaperType.ARTICLE,
    "editorial": PaperType.ARTICLE,
    "erratum": PaperType.ARTICLE,
    "business article": PaperType.ARTICLE,
    "conference paper": PaperType.INPROCEEDINGS,
    "conference review": PaperType.INPROCEEDINGS,
    "book": PaperType.BOOK,
    "book chapter": PaperType.INBOOK,
    "report": PaperType.TECHREPORT,
    "data paper": PaperType.MISC,
}


class ScopusConnector(SearchConnectorBase, DOILookupConnectorBase):
    """Connector for the Elsevier Scopus database.

    Requires a Scopus API key:
    https://dev.elsevier.com/sc_search_tips.html

    Rate limit: varies by institution (typically 2-9 req/s).

    .. note::

        The Scopus *Search API* returns only the first author
        (``dc:creator``) per entry.  Full author lists require the
        *Abstract Retrieval API*, which is not used here.  Papers
        fetched through this connector will therefore have an
        incomplete ``authors`` list.
    """

    def __init__(
        self,
        query_builder: ScopusQueryBuilder | None = None,
        api_key: str | None = None,
    ) -> None:
        """Create a Scopus searcher.

        Parameters
        ----------
        query_builder : ScopusQueryBuilder | None
            Builder used to validate and convert queries.  When ``None`` a
            default :class:`ScopusQueryBuilder` is created automatically.
        api_key : str | None
            Elsevier API key (required for production use).
        """
        super().__init__()
        self._query_builder: ScopusQueryBuilder = query_builder or ScopusQueryBuilder()
        if not api_key or not api_key.strip():
            raise MissingApiKeyError(
                "ScopusConnector requires an api_key. Obtain one at https://dev.elsevier.com/"
            )
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database name.
        """
        return Database.SCOPUS.value

    @property
    def query_builder(self) -> QueryBuilder:
        """Return the Scopus query builder.

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
            Interval in seconds.
        """
        return _MIN_REQUEST_INTERVAL

    def _prepare_headers(self, headers: dict) -> dict:
        """Inject Scopus-required HTTP headers including Accept type and API key.

        Parameters
        ----------
        headers : dict
            Raw HTTP headers.

        Returns
        -------
        dict
            Headers with ``Accept`` set to JSON and optionally
            ``X-ELS-APIKey`` added.
        """
        updated = super()._prepare_headers(headers)
        updated["Accept"] = "application/json"
        if self._api_key:
            updated["X-ELS-APIKey"] = self._api_key
        return updated

    # ------------------------------------------------------------------
    # DOI lookup
    # ------------------------------------------------------------------

    def fetch_paper_by_doi(self, doi: str) -> Paper | None:
        """Fetch a single paper by its DOI from Scopus.

        Uses the Scopus Search API with the ``doi({doi})`` query term, which
        returns the same JSON structure as a regular search.  The
        *Abstract Retrieval* endpoint (``/content/abstract/doi/{doi}``) is
        not used here because the ``FULL`` view requires institutional
        entitlements beyond a basic API key.

        Parameters
        ----------
        doi : str
            Bare DOI identifier (e.g. ``"10.1038/nature12373"``).

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when no API key is configured, the DOI is not found in Scopus,
            or the response cannot be parsed.
        """
        params = {"query": f"doi({doi})", "count": 1}
        try:
            response = self._get(_BASE_URL, params=params)
            data = response.json()
        except (requests.RequestException, ValueError):
            logger.debug("Scopus: failed to fetch DOI %s.", doi)
            return None

        entries = (data.get("search-results") or {}).get("entry") or []
        if not entries:
            logger.debug("Scopus: DOI %s not found.", doi)
            return None

        # A Scopus result with an error key means no results were found.
        first = entries[0]
        if first.get("error"):
            logger.debug("Scopus: DOI %s returned error: %s", doi, first["error"])
            return None

        return self._parse_paper(first)

    @staticmethod
    def _parse_scopus_authors(entry: dict[str, Any]) -> list[Author]:
        """Extract authors from a Scopus search result entry.

        Scopus returns only the first author via ``dc:creator``.  When a
        single author is returned, the first affiliation (if any) is assigned
        to that author.

        Parameters
        ----------
        entry : dict
            Scopus entry dict.

        Returns
        -------
        list[Author]
            Parsed author list.
        """
        raw_creator = entry.get("dc:creator") or ""
        if isinstance(raw_creator, list):
            authors = [Author(name=a.strip()) for a in raw_creator if (a or "").strip()]
        elif raw_creator:
            authors = [Author(name=raw_creator.strip())]
        else:
            authors = []

        if len(authors) == 1:
            raw_affiliation = entry.get("affiliation")
            if isinstance(raw_affiliation, list) and raw_affiliation:
                affilname = (raw_affiliation[0].get("affilname") or "").strip()
                if affilname:
                    authors[0] = Author(name=authors[0].name, affiliation=affilname)
        return authors

    @staticmethod
    def _parse_scopus_source(entry: dict[str, Any]) -> Source | None:
        """Build a :class:`~findpapers.core.source.Source` from Scopus metadata.

        Parameters
        ----------
        entry : dict
            Scopus entry dict.

        Returns
        -------
        Source | None
            Populated source or ``None`` when no title is present.
        """
        pub_title = (
            entry.get("prism:publicationName") or entry.get("prism:issueName") or ""
        ).strip()
        if not pub_title:
            return None
        issn = (entry.get("prism:issn") or entry.get("prism:eIssn") or "").strip() or None
        raw_isbn = entry.get("prism:isbn")
        if isinstance(raw_isbn, list):
            isbn = raw_isbn[0].get("$", "").strip() if raw_isbn else None
        else:
            isbn = (raw_isbn or "").strip() or None
        publisher = (entry.get("dc:publisher") or "").strip() or None
        raw_agg_type = (entry.get("prism:aggregationType") or "").strip().lower()
        return Source(
            title=pub_title,
            issn=issn,
            isbn=isbn,
            publisher=publisher,
            source_type=_SCOPUS_AGGREGATION_TYPE_MAP.get(raw_agg_type),
        )

    @staticmethod
    def _parse_scopus_is_open_access(entry: dict[str, Any]) -> bool | None:
        """Determine open-access status from Scopus flags.

        Prefers the boolean ``openaccessFlag`` when present; falls back to
        the integer ``openaccess`` field (``1`` = OA, ``0`` = not OA).

        Parameters
        ----------
        entry : dict
            Scopus entry dict.

        Returns
        -------
        bool | None
            Open-access flag or ``None`` when unknown.
        """
        raw_oa_flag = entry.get("openaccessFlag")
        if isinstance(raw_oa_flag, bool):
            return raw_oa_flag
        raw_oa_int = entry.get("openaccess")
        if raw_oa_int is not None:
            with contextlib.suppress(ValueError, TypeError):
                return bool(int(raw_oa_int))
        return None

    def _parse_paper(self, entry: dict[str, Any]) -> Paper | None:
        """Parse a single Scopus search result entry.

        Parameters
        ----------
        entry : dict
            Entry dictionary from Scopus JSON response.

        Returns
        -------
        Paper | None
            Parsed paper or ``None`` when required fields are missing.
        """
        title = (entry.get("dc:title") or "").strip()
        if not title:
            return None

        abstract = (entry.get("dc:description") or entry.get("prism:teaser") or "").strip()
        authors = self._parse_scopus_authors(entry)

        # Publication date
        cover_date = (entry.get("prism:coverDate") or "").strip()
        pub_date: datetime.date | None = None
        if cover_date:
            with contextlib.suppress(ValueError):
                pub_date = datetime.date.fromisoformat(cover_date[:10])

        # DOI / URL
        doi: str | None = (entry.get("prism:doi") or "").strip() or None
        url: str | None = None
        for link_item in entry.get("link", []):
            if isinstance(link_item, dict) and link_item.get("@ref") == "scopus":
                url = (link_item.get("@href") or "").strip() or None
                break

        # Citations
        citations: int | None = None
        cite_count = entry.get("citedby-count")
        if cite_count is not None:
            with contextlib.suppress(ValueError, TypeError):
                citations = int(cite_count)

        source = self._parse_scopus_source(entry)
        raw_subtype = (entry.get("subtypeDescription") or "").strip().lower()
        paper_type = _SCOPUS_PAPER_TYPE_MAP.get(raw_subtype)
        pages: str | None = (entry.get("prism:pageRange") or "").strip() or None
        is_open_access = self._parse_scopus_is_open_access(entry)

        try:
            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                source=source,
                publication_date=pub_date,
                url=url,
                doi=doi,
                citations=citations,
                page_range=pages,
                databases={self.name},
                paper_type=paper_type,
                is_open_access=is_open_access,
            )
        except ValueError:
            return None

        return paper

    def _fetch_papers(
        self,
        query: Query,
        max_papers: int | None,
        progress_callback: Callable[[int, int | None], None] | None,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
    ) -> list[Paper]:
        """Fetch papers from Scopus with pagination.

        Parameters
        ----------
        query : Query
            Validated query object.
        max_papers : int | None
            Maximum papers to retrieve.
        progress_callback : Callable[[int, int | None], None] | None
            Progress callback.
        since : datetime.date | None
            Only return papers published on or after this date.
        until : datetime.date | None
            Only return papers published on or before this date.

        Returns
        -------
        list[Paper]
            Retrieved papers.
        """
        scopus_query = self._query_builder.convert_query(query)
        papers: list[Paper] = []
        processed = 0
        offset = 0
        total: int | None = None

        while True:
            remaining = (max_papers - len(papers)) if max_papers is not None else _PAGE_SIZE
            page_size = min(_PAGE_SIZE, remaining)

            params: dict[str, Any] = {
                "query": scopus_query,
                "start": offset,
                "count": page_size,
                "sort": "-coverDate",
                "view": "STANDARD",
            }
            date_param = ScopusConnector._build_scopus_date_param(since, until)
            if date_param is not None:
                params["date"] = date_param

            try:
                response = self._get(_BASE_URL, params)
            except requests.RequestException as exc:
                logger.warning("Scopus request failed (offset=%d): %s", offset, exc)
                logger.debug("Scopus request exception details:", exc_info=True)
                break

            entries, page_total, api_error = ScopusConnector._parse_scopus_page_response(response)
            if api_error:
                logger.warning("Scopus API error (offset=%d): %s", offset, api_error)
                logger.debug("Full Scopus error body (offset=%d): %s", offset, response.json())
                break
            if page_total is not None and total is None:
                total = page_total
            if not entries:
                break

            for entry in entries:
                paper = self._parse_paper(entry)
                if paper is not None:
                    papers.append(paper)

            processed += len(entries)
            if progress_callback is not None:
                progress_callback(processed, total)

            if max_papers is not None and len(papers) >= max_papers:
                break

            if len(entries) < page_size:
                break

            offset += len(entries)

        if progress_callback is not None:
            progress_callback(processed, total)

        return papers[:max_papers] if max_papers is not None else papers

    @staticmethod
    def _build_scopus_date_param(
        since: datetime.date | None, until: datetime.date | None
    ) -> str | None:
        """Build the Scopus ``date`` query parameter from date range.

        Parameters
        ----------
        since : datetime.date | None
            Start date.
        until : datetime.date | None
            End date.

        Returns
        -------
        str | None
            ``"YYYY"`` or ``"YYYY-YYYY"`` string, or ``None`` when no filter is needed.
        """
        if since is None and until is None:
            return None
        from_year = str(since.year) if since else "1900"
        to_year = str(until.year) if until else "9999"
        if from_year == to_year:
            return from_year
        return f"{from_year}-{to_year}"

    @staticmethod
    def _parse_scopus_page_response(
        response: requests.Response,
    ) -> tuple[list[dict[str, Any]], int | None, Any]:
        """Parse a Scopus search-results page response.

        Parameters
        ----------
        response : requests.Response
            Raw HTTP response from Scopus.

        Returns
        -------
        tuple[list[dict], int | None, Any]
            ``(entries, total, api_error)`` — ``api_error`` is non-falsy
            when the response body contains an API-level error dict.
        """
        data = response.json()
        api_error = data.get("service-error") or data.get("error-response")
        if api_error:
            return [], None, api_error
        search_results = data.get("search-results", {})
        total_str = search_results.get("opensearch:totalResults", "0")
        total: int | None = None
        with contextlib.suppress(ValueError, TypeError):
            total = int(total_str)
        entries: list[dict[str, Any]] = search_results.get("entry", [])
        return entries, total, None
