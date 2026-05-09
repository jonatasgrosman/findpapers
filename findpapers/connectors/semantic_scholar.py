"""Semantic Scholar searcher implementation."""

from __future__ import annotations

import contextlib
import datetime
import logging
import re
from collections.abc import Callable
from typing import Any

import requests

from findpapers.connectors.citation_base import CitationConnectorBase
from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.search_base import SearchConnectorBase
from findpapers.connectors.url_lookup_base import URLLookupConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Database, Paper, PaperType
from findpapers.core.query import Query
from findpapers.core.source import Source, SourceType
from findpapers.query.builder import QueryBuilder
from findpapers.query.builders.semantic_scholar import SemanticScholarQueryBuilder

logger = logging.getLogger(__name__)

_BULK_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
_AUTHOR_BATCH_URL = "https://api.semanticscholar.org/graph/v1/author/batch"
_PAGE_SIZE = 100  # Semantic Scholar max per request
_CITATION_PAGE_SIZE = 1000  # Max per page for citations/references endpoints
_AUTHOR_BATCH_SIZE = 1000  # Max authors per batch request

# Rate limits: 1000 req/s without key (shared among all unauthenticated users),
# 1 req/s with key (introductory; can be increased upon request)
_MIN_REQUEST_INTERVAL_DEFAULT = 1.1  # conservative for shared pool
_MIN_REQUEST_INTERVAL_WITH_KEY = 1.1  # respects 1 RPS introductory limit

# Fields to retrieve in each paper record
_PAPER_FIELDS = (
    "paperId,externalIds,title,abstract,authors,year,publicationDate,"
    "journal,venue,citationCount,openAccessPdf,url,fieldsOfStudy,"
    "s2FieldsOfStudy,publicationTypes,publicationVenue,isOpenAccess"
)

# Mapping from Semantic Scholar publicationVenue.type to SourceType.
_SS_VENUE_TYPE_MAP: dict[str, SourceType] = {
    "journal": SourceType.JOURNAL,
    "conference": SourceType.CONFERENCE,
    "book": SourceType.BOOK,
    "repository": SourceType.REPOSITORY,
}

# Regex that matches Semantic Scholar paper landing-page URLs and captures the
# 40-character hexadecimal paper ID.
# Handles:
#   https://www.semanticscholar.org/paper/Attention-is-All-you-Need/204e3073870fae3d05bcbc2f6a8e263d9b72e776
#   https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776
_SS_URL_RE = re.compile(
    r"semanticscholar\.org/paper/(?:[^/]+/)?([0-9a-f]{40})",
    re.IGNORECASE,
)

# Mapping from publicationTypes list entries to SourceType (fallback).
_SS_PUB_TYPE_MAP: dict[str, SourceType] = {
    "JournalArticle": SourceType.JOURNAL,
    "Review": SourceType.JOURNAL,
    "Conference": SourceType.CONFERENCE,
    "Book": SourceType.BOOK,
    "BookSection": SourceType.BOOK,
}

# Mapping from Semantic Scholar publicationTypes entries to PaperType.
_SS_PAPER_TYPE_MAP: dict[str, PaperType] = {
    "JournalArticle": PaperType.ARTICLE,
    "Review": PaperType.ARTICLE,
    "CaseReport": PaperType.ARTICLE,
    "ClinicalTrial": PaperType.ARTICLE,
    "Editorial": PaperType.ARTICLE,
    "LettersAndComments": PaperType.ARTICLE,
    "MetaAnalysis": PaperType.ARTICLE,
    "Study": PaperType.ARTICLE,
    "Conference": PaperType.INPROCEEDINGS,
    "Book": PaperType.BOOK,
    "BookSection": PaperType.INBOOK,
    "Dataset": PaperType.MISC,
    "News": PaperType.MISC,
}


class SemanticScholarConnector(
    SearchConnectorBase,
    CitationConnectorBase,
    DOILookupConnectorBase,
    URLLookupConnectorBase,
):
    """Connector for the Semantic Scholar research corpus.

    Uses the Bulk Search endpoint:
    https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/bulk_paper_search

    Rate limits:
    - Without API key: up to 1000 req/s (shared among all unauthenticated users)
    - With API key: 1 req/s (introductory; can be increased upon request)
    """

    def __init__(
        self,
        query_builder: SemanticScholarQueryBuilder | None = None,
        api_key: str | None = None,
    ) -> None:
        """Create a Semantic Scholar searcher.

        Parameters
        ----------
        query_builder : SemanticScholarQueryBuilder | None
            Builder used to validate and convert queries.  When ``None`` a
            default :class:`SemanticScholarQueryBuilder` is created automatically.
        api_key : str | None
            Semantic Scholar API key (optional; provides a dedicated 1 RPS quota,
            decoupled from the shared unauthenticated pool, and can be increased
            upon request).
        """
        super().__init__()
        self._query_builder: SemanticScholarQueryBuilder = (
            query_builder or SemanticScholarQueryBuilder()
        )
        self._api_key = api_key
        self._request_interval = (
            _MIN_REQUEST_INTERVAL_WITH_KEY if api_key else _MIN_REQUEST_INTERVAL_DEFAULT
        )

        if not api_key:
            logger.warning(
                "No API key provided for Semantic Scholar. "
                "Without a key, requests share the unauthenticated pool "
                "(up to 1000 req/s shared among all anonymous users). "
                "Request a key at https://www.semanticscholar.org/product/api "
                "for a dedicated quota."
            )

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database name.
        """
        return Database.SEMANTIC_SCHOLAR.value

    @property
    def query_builder(self) -> QueryBuilder:
        """Return the Semantic Scholar query builder.

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
            Interval in seconds (varies with API key).
        """
        return self._request_interval

    def _prepare_headers(self, headers: dict) -> dict:
        """Inject the Semantic Scholar API key header when configured.

        Parameters
        ----------
        headers : dict
            Raw HTTP headers.

        Returns
        -------
        dict
            Headers with ``x-api-key`` added when a key is set.
        """
        updated = super()._prepare_headers(headers)
        if self._api_key:
            updated["x-api-key"] = self._api_key
        return updated

    # ------------------------------------------------------------------
    # URL lookup
    # ------------------------------------------------------------------

    @property
    def url_pattern(self) -> re.Pattern[str]:
        """Return the regex matching Semantic Scholar paper landing-page URLs.

        Returns
        -------
        re.Pattern[str]
            Compiled regex whose first capture group is the 40-char paper ID.
        """
        return _SS_URL_RE

    def fetch_paper_by_id(self, paper_id: str) -> Paper | None:
        """Fetch a single paper by its Semantic Scholar paper ID.

        Parameters
        ----------
        paper_id : str
            40-character hexadecimal Semantic Scholar paper ID.

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the paper is not found or the response cannot be parsed.
        """
        url = f"{_PAPER_URL}/{paper_id}"
        params = {"fields": _PAPER_FIELDS}
        try:
            response = self._get(url, params=params)
            data = response.json()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.debug("Semantic Scholar: paper ID %s not found (404).", paper_id)
                return None
            logger.debug("Semantic Scholar: HTTP error fetching paper ID %s: %s", paper_id, exc)
            return None
        except (requests.RequestException, ValueError):
            logger.debug("Semantic Scholar: failed to fetch paper ID %s.", paper_id)
            return None

        return self._parse_paper(data)

    # ------------------------------------------------------------------
    # DOI lookup
    # ------------------------------------------------------------------

    def fetch_paper_by_doi(self, doi: str) -> Paper | None:
        """Fetch a single paper by its DOI from Semantic Scholar.

        Queries ``GET /graph/v1/paper/DOI:{doi}?fields=...`` and converts
        the response into a :class:`~findpapers.core.paper.Paper`.

        Parameters
        ----------
        doi : str
            Bare DOI identifier (e.g. ``"10.1038/nature12373"``).

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the DOI is not found or the response cannot be parsed.
        """
        url = f"{_PAPER_URL}/DOI:{doi}"
        params = {"fields": _PAPER_FIELDS}
        try:
            response = self._get(url, params=params)
            data = response.json()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.debug("Semantic Scholar: DOI %s not found (404).", doi)
                return None
            logger.debug("Semantic Scholar: HTTP error fetching DOI %s: %s", doi, exc)
            return None
        except (requests.RequestException, ValueError):
            logger.debug("Semantic Scholar: failed to fetch DOI %s.", doi)
            return None

        return self._parse_paper(data)

    # ------------------------------------------------------------------
    # Citation methods (CitationConnectorBase)
    # ------------------------------------------------------------------

    def _fetch_citation_page(
        self,
        doi: str,
        endpoint: str,
        offset: int,
    ) -> tuple[list[Paper], int]:
        """Fetch one page of references or citations for a paper.

        Parameters
        ----------
        doi : str
            DOI of the paper.
        endpoint : str
            ``"references"`` or ``"citations"``.
        offset : int
            Pagination offset.

        Returns
        -------
        tuple[list[Paper], int]
            Parsed papers from this page and the total ``next`` offset
            (``-1`` when there are no more pages).
        """
        url = f"{_PAPER_URL}/DOI:{doi}/{endpoint}"
        params: dict[str, Any] = {
            "fields": _PAPER_FIELDS,
            "limit": _CITATION_PAGE_SIZE,
            "offset": offset,
        }
        try:
            response = self._get(url, params)
        except requests.RequestException:
            logger.debug(
                "Semantic Scholar: failed to fetch %s for DOI %s (offset=%d).",
                endpoint,
                doi,
                offset,
            )
            return [], -1

        data = response.json()
        items = data.get("data") or []
        papers: list[Paper] = []
        for item in items:
            # The citations/references endpoints wrap each paper in
            # {"citedPaper": {...}} or {"citingPaper": {...}}.
            nested_key = "citedPaper" if endpoint == "references" else "citingPaper"
            paper_data = item.get(nested_key) or item
            paper = self._parse_paper(paper_data)
            if paper is not None:
                papers.append(paper)

        next_offset = data.get("next")
        if next_offset is None or len(items) < _CITATION_PAGE_SIZE:
            next_offset = -1

        return papers, next_offset

    def _fetch_paper_counts(self, doi: str) -> tuple[int | None, int | None]:
        """Fetch citation and reference counts for a paper (lightweight).

        Makes a single request with minimal fields to obtain
        ``citationCount`` and ``referenceCount``.

        Parameters
        ----------
        doi : str
            DOI of the paper.

        Returns
        -------
        tuple[int | None, int | None]
            ``(citation_count, reference_count)``.  Either may be ``None``
            on failure.
        """
        url = f"{_PAPER_URL}/DOI:{doi}"
        params = {"fields": "citationCount,referenceCount"}
        try:
            response = self._get(url, params)
            data = response.json()
            return data.get("citationCount"), data.get("referenceCount")
        except Exception:
            logger.debug("Semantic Scholar: could not fetch counts for DOI %s.", doi)
            return None, None

    def _fetch_all_citation_pages(
        self,
        doi: str,
        endpoint: str,
        *,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Paginate through all references or citations for a paper.

        Parameters
        ----------
        doi : str
            DOI of the paper.
        endpoint : str
            ``"references"`` or ``"citations"``.
        progress_callback : Callable[[int], None] | None
            Optional callback invoked after each page with the number
            of new papers fetched in that page.

        Returns
        -------
        list[Paper]
            All papers from the paginated endpoint.
        """
        all_papers: list[Paper] = []
        offset = 0
        page_num = 0

        while offset >= 0:
            page_num += 1
            page_papers, next_offset = self._fetch_citation_page(doi, endpoint, offset)
            all_papers.extend(page_papers)
            if progress_callback is not None:
                progress_callback(len(page_papers))
            offset = next_offset

        logger.info(
            "Semantic Scholar: DOI %s %s — %d pages, %d papers total.",
            doi,
            endpoint,
            page_num,
            len(all_papers),
        )

        return all_papers

    def get_expected_counts(self, paper: Paper) -> tuple[int | None, int | None]:
        """Return expected citation and reference counts for *paper*.

        Uses the locally known ``paper.citations`` when available,
        otherwise makes a lightweight API call to fetch both counts.

        Parameters
        ----------
        paper : Paper
            The paper whose counts are requested.

        Returns
        -------
        tuple[int | None, int | None]
            ``(citation_count, reference_count)``.
        """
        if not paper.doi:
            return None, None
        local_citations = paper.citations
        cit_count, ref_count = self._fetch_paper_counts(paper.doi)
        # Prefer local citation count if we already have it.
        if local_citations is not None:
            cit_count = local_citations
        return cit_count, ref_count

    def fetch_references(
        self,
        paper: Paper,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Return papers cited *by* the given paper (backward snowballing).

        Uses the Semantic Scholar ``/paper/{id}/references`` endpoint.

        Parameters
        ----------
        paper : Paper
            The paper whose references should be fetched.  Must have a DOI.
        progress_callback : Callable[[int], None] | None
            Optional callback for per-page progress reporting.

        Returns
        -------
        list[Paper]
            Papers referenced by *paper*, or empty list on failure.
        """
        if not paper.doi:
            return []

        logger.debug("Semantic Scholar: fetching references for DOI %s.", paper.doi)
        return self._fetch_all_citation_pages(
            paper.doi,
            "references",
            progress_callback=progress_callback,
        )

    def fetch_cited_by(
        self,
        paper: Paper,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Return papers that cite the given paper (forward snowballing).

        Uses the Semantic Scholar ``/paper/{id}/citations`` endpoint.

        Parameters
        ----------
        paper : Paper
            The paper whose citing papers should be fetched.  Must have a DOI.
        progress_callback : Callable[[int], None] | None
            Optional callback for per-page progress reporting.

        Returns
        -------
        list[Paper]
            Papers that cite *paper*, or empty list on failure.
        """
        if not paper.doi:
            return []

        logger.debug("Semantic Scholar: fetching citations for DOI %s.", paper.doi)
        return self._fetch_all_citation_pages(
            paper.doi,
            "citations",
            progress_callback=progress_callback,
        )

    @staticmethod
    def _parse_ss_pub_date(item: dict[str, Any]) -> datetime.date | None:
        """Extract publication date from a Semantic Scholar item.

        Prefers ``publicationDate``; falls back to ``year`` when absent.

        Parameters
        ----------
        item : dict
            Semantic Scholar paper metadata dict.

        Returns
        -------
        datetime.date | None
            Parsed date or ``None``.
        """
        date_str = (item.get("publicationDate") or "").strip()
        if date_str:
            with contextlib.suppress(ValueError):
                return datetime.date.fromisoformat(date_str[:10])
        if item.get("year"):
            with contextlib.suppress(ValueError, TypeError):
                return datetime.date(int(item["year"]), 1, 1)
        return None

    @staticmethod
    def _parse_ss_doi(item: dict[str, Any]) -> str | None:
        """Extract DOI from Semantic Scholar external IDs.

        Prefers the explicit DOI field; falls back to deriving a canonical
        arXiv DOI (``10.48550/arXiv.<id>``) when only the ArXivId is available.

        Parameters
        ----------
        item : dict
            Semantic Scholar paper metadata dict.

        Returns
        -------
        str | None
            DOI string or ``None``.
        """
        external_ids = item.get("externalIds") or {}
        doi = (external_ids.get("DOI") or "").strip() or None
        if doi is None:
            arxiv_id = (external_ids.get("ArXivId") or "").strip()
            if arxiv_id:
                doi = f"10.48550/arXiv.{arxiv_id}"
        return doi

    @staticmethod
    def _parse_ss_fos_subjects(
        item: dict[str, Any],
    ) -> tuple[set[str], set[str]]:
        """Extract fields of study and subjects from a Semantic Scholar item.

        ``fieldsOfStudy`` → broad fields; ``s2FieldsOfStudy`` → subjects
        (categories not already in fields).

        Parameters
        ----------
        item : dict
            Semantic Scholar paper metadata dict.

        Returns
        -------
        tuple[set[str], set[str]]
            ``(fields_of_study, subjects)`` sets.
        """
        fields_of_study: set[str] = set()
        for field in item.get("fieldsOfStudy") or []:
            if isinstance(field, str) and field.strip():
                fields_of_study.add(field.strip())
        subjects: set[str] = set()
        for entry in item.get("s2FieldsOfStudy") or []:
            if isinstance(entry, dict):
                cat = (entry.get("category") or "").strip()
                if cat and cat not in fields_of_study:
                    subjects.add(cat)
        return fields_of_study, subjects

    @staticmethod
    def _parse_ss_source(
        item: dict[str, Any],
    ) -> tuple[Source | None, str | None]:
        """Build a source and page range from a Semantic Scholar item.

        Parameters
        ----------
        item : dict
            Semantic Scholar paper metadata dict.

        Returns
        -------
        tuple[Source | None, str | None]
            ``(source, pages)`` pair.
        """
        journal = item.get("journal") or {}
        venue = (item.get("venue") or "").strip()
        pub_title = (journal.get("name") or venue or "").strip()

        source_type: SourceType | None = None
        pub_venue = item.get("publicationVenue") or {}
        venue_type = (pub_venue.get("type") or "").strip().lower()
        if venue_type:
            source_type = _SS_VENUE_TYPE_MAP.get(venue_type)
        if source_type is None:
            for pt in item.get("publicationTypes") or []:
                if isinstance(pt, str) and pt in _SS_PUB_TYPE_MAP:
                    source_type = _SS_PUB_TYPE_MAP[pt]
                    break

        source: Source | None = (
            Source(title=pub_title, source_type=source_type) if pub_title else None
        )
        pages: str | None = (journal.get("pages") or "").strip() or None
        return source, pages

    @staticmethod
    def _parse_ss_paper_type(item: dict[str, Any]) -> PaperType | None:
        """Infer paper type from Semantic Scholar publication types list.

        Parameters
        ----------
        item : dict
            Semantic Scholar paper metadata dict.

        Returns
        -------
        PaperType | None
            Inferred paper type or ``None``.
        """
        for pt in item.get("publicationTypes") or []:
            if isinstance(pt, str) and pt in _SS_PAPER_TYPE_MAP:
                return _SS_PAPER_TYPE_MAP[pt]
        return None

    def _parse_paper(self, item: dict[str, Any]) -> Paper | None:
        """Parse a single Semantic Scholar paper record.

        Parameters
        ----------
        item : dict
            Paper metadata dictionary from Semantic Scholar API.

        Returns
        -------
        Paper | None
            Parsed paper or ``None`` when required fields are missing.
        """
        title = (item.get("title") or "").strip()
        if not title:
            return None

        abstract = (item.get("abstract") or "").strip()

        # Authors — affiliations are fetched in a batch request after the search.
        authors: list[Author] = []
        for author_entry in item.get("authors", []):
            name = (author_entry.get("name") or "").strip()
            if name:
                authors.append(Author(name=name))

        pub_date = self._parse_ss_pub_date(item)
        doi = self._parse_ss_doi(item)

        # URL
        url: str | None = (item.get("url") or "").strip() or None

        # PDF URL
        pdf_url: str | None = None
        open_access_pdf = item.get("openAccessPdf")
        if isinstance(open_access_pdf, dict):
            pdf_url = (open_access_pdf.get("url") or "").strip() or None

        # Citations
        citations: int | None = item.get("citationCount")

        fields_of_study, subjects = self._parse_ss_fos_subjects(item)
        source, pages = self._parse_ss_source(item)
        paper_type = self._parse_ss_paper_type(item)

        # Open access flag from Semantic Scholar.
        raw_is_oa = item.get("isOpenAccess")
        is_open_access: bool | None = bool(raw_is_oa) if raw_is_oa is not None else None

        try:
            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                source=source,
                publication_date=pub_date,
                url=url,
                pdf_url=pdf_url,
                doi=doi,
                citations=citations,
                keywords=None,
                page_range=pages,
                databases={self.name},
                paper_type=paper_type,
                fields_of_study=fields_of_study if fields_of_study else None,
                subjects=subjects if subjects else None,
                is_open_access=is_open_access,
            )
        except ValueError:  # pragma: no cover — title already validated above
            return None

        return paper

    def _enrich_author_affiliations(
        self,
        author_id_to_authors: dict[str, list[Author]],
    ) -> None:
        """Batch-fetch affiliations from the Semantic Scholar Author API.

        Uses ``POST /author/batch?fields=affiliations`` to retrieve
        affiliation data for up to 1,000 authors per request, then
        updates the corresponding :class:`Author` objects in-place.

        Parameters
        ----------
        author_id_to_authors : dict[str, list[Author]]
            Mapping from Semantic Scholar author ID to :class:`Author`
            instances that share that ID across the retrieved papers.
        """
        all_ids = list(author_id_to_authors.keys())
        logger.info(
            "Fetching affiliations for %d unique authors from Semantic Scholar.",
            len(all_ids),
        )

        for start in range(0, len(all_ids), _AUTHOR_BATCH_SIZE):
            batch_ids = all_ids[start : start + _AUTHOR_BATCH_SIZE]
            try:
                response = self._post(
                    _AUTHOR_BATCH_URL,
                    json_body={"ids": batch_ids},
                    params={"fields": "affiliations"},
                )
            except requests.RequestException:
                logger.debug(
                    "Failed to fetch author affiliations batch (offset=%d).",
                    start,
                )
                continue

            results = response.json()
            for author_data in results:
                if not isinstance(author_data, dict):
                    continue
                author_id = author_data.get("authorId")
                affiliations = author_data.get("affiliations") or []
                if not author_id or not affiliations:
                    continue
                affiliation_str = "; ".join(affiliations)
                for author in author_id_to_authors.get(author_id, []):
                    if not author.affiliation:
                        author.affiliation = affiliation_str

    def _fetch_papers(
        self,
        query: Query,
        max_papers: int | None,
        progress_callback: Callable[[int, int | None], None] | None,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
    ) -> list[Paper]:
        """Fetch papers from Semantic Scholar bulk search with pagination.

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
        ss_params = self._query_builder.convert_query(query)
        date_param = SemanticScholarConnector._build_ss_date_param(since, until)
        if date_param is not None:
            ss_params["publicationDateOrYear"] = date_param

        papers: list[Paper] = []
        author_id_to_authors: dict[str, list[Author]] = {}
        token: str | None = None
        total: int | None = None

        while True:
            remaining = (max_papers - len(papers)) if max_papers is not None else _PAGE_SIZE
            page_size = min(_PAGE_SIZE, remaining)

            params: dict = {
                **ss_params,
                "fields": _PAPER_FIELDS,
                "limit": page_size,
                "sort": "publicationDate:desc",
            }
            if token:
                params["token"] = token

            try:
                response = self._get(_BULK_SEARCH_URL, params)
            except requests.RequestException as exc:
                logger.warning("Semantic Scholar request failed (token=%s): %s", token, exc)
                logger.debug("Semantic Scholar request exception details:", exc_info=True)
                break

            data = response.json()
            if total is None:
                total = data.get("total")

            items = data.get("data") or []
            if not items:
                break

            for item in items:
                paper = self._parse_paper(item)
                if paper is not None:
                    papers.append(paper)
                    SemanticScholarConnector._collect_author_ids(item, paper, author_id_to_authors)

            if progress_callback is not None:
                progress_callback(len(papers), total)

            if max_papers is not None and len(papers) >= max_papers:
                break

            token = data.get("token")
            if not token or len(items) < page_size:
                break

        if progress_callback is not None:
            progress_callback(len(papers), total)

        result = papers[:max_papers] if max_papers is not None else papers

        if author_id_to_authors:
            self._enrich_author_affiliations(author_id_to_authors)

        return result

    @staticmethod
    def _build_ss_date_param(
        since: datetime.date | None, until: datetime.date | None
    ) -> str | None:
        """Build the Semantic Scholar ``publicationDateOrYear`` filter value.

        Parameters
        ----------
        since : datetime.date | None
            Start date.
        until : datetime.date | None
            End date.

        Returns
        -------
        str | None
            ``"FROM:TO"`` ISO-date string or ``None`` when no filter is needed.
        """
        if not since and not until:
            return None
        from_part = since.isoformat() if since else ""
        to_part = until.isoformat() if until else ""
        return f"{from_part}:{to_part}"

    @staticmethod
    def _collect_author_ids(
        item: dict,
        paper: Paper,
        author_id_to_authors: dict[str, list[Author]],
    ) -> None:
        """Accumulate the author-ID → Author mapping from a parsed paper.

        Parameters
        ----------
        item : dict
            Raw Semantic Scholar paper item.
        paper : Paper
            Parsed paper object (authors are indexed positionally).
        author_id_to_authors : dict[str, list[Author]]
            Mapping to accumulate into (mutated in place).

        Returns
        -------
        None
        """
        raw_authors = item.get("authors", [])
        for idx, author_entry in enumerate(raw_authors):
            author_id = author_entry.get("authorId")
            if author_id and idx < len(paper.authors):
                author_id_to_authors.setdefault(author_id, []).append(paper.authors[idx])
