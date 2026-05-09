"""CrossRef connector for fetching paper metadata by DOI.

CrossRef is the authoritative DOI registration agency and provides a free,
key-less REST API that returns rich structured metadata for most academic
DOIs.  This module wraps the ``/works/{doi}`` endpoint and converts the
response into a :class:`~findpapers.core.paper.Paper` instance ready for
merging.

API documentation: https://api.crossref.org/swagger-ui/index.html
"""

from __future__ import annotations

import datetime
import logging
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote as _url_quote

import requests

from findpapers.connectors.citation_base import CitationConnectorBase
from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Paper
from findpapers.core.source import Source, SourceType

logger = logging.getLogger(__name__)

_CROSSREF_API_URL = "https://api.crossref.org/works"

# Minimum interval between requests — CrossRef polite pool recommends
# keeping traffic moderate; 0.1 s (10 req/s) is well within limits.
_MIN_REQUEST_INTERVAL = 0.1

# Mapping from CrossRef ``type`` values to :class:`SourceType`.
_CROSSREF_TYPE_MAP: dict[str, SourceType] = {
    "journal-article": SourceType.JOURNAL,
    "proceedings-article": SourceType.CONFERENCE,
    "book": SourceType.BOOK,
    "book-chapter": SourceType.BOOK,
    "monograph": SourceType.BOOK,
    "edited-book": SourceType.BOOK,
    "book-section": SourceType.BOOK,
    "book-part": SourceType.BOOK,
    "reference-book": SourceType.BOOK,
    "posted-content": SourceType.REPOSITORY,
    "dissertation": SourceType.OTHER,
    "report": SourceType.OTHER,
    "dataset": SourceType.OTHER,
    "peer-review": SourceType.OTHER,
    "standard": SourceType.OTHER,
    "component": SourceType.OTHER,
}

# Simple regex to strip JATS/HTML tags from CrossRef abstract text.
_TAG_RE = re.compile(r"<[^>]+>")


class CrossRefConnector(CitationConnectorBase, DOILookupConnectorBase):
    """Connector for the CrossRef REST API (DOI-based metadata lookup).

    Unlike search connectors this class does **not** support free-text
    searches — it only resolves DOIs via the ``/works/{doi}`` endpoint.
    It inherits rate limiting, request/response logging, and header
    management from :class:`~findpapers.connectors.connector_base.ConnectorBase`.

    For citation snowballing it provides **backward** lookups only: the
    ``reference`` list embedded in each work record is parsed for DOIs,
    and each referenced work is fetched individually.  Forward lookups
    (papers that cite a given DOI) are not supported by the CrossRef API
    and return an empty list.

    Parameters
    ----------
    email : str | None
        Contact email for CrossRef polite-pool access.  When provided the
        ``User-Agent`` header includes a ``mailto:`` clause which grants
        higher rate-limits.

    API documentation: https://api.crossref.org/swagger-ui/index.html
    """

    _DATABASE_NAME: str = "crossref"
    """Database identifier used in :attr:`~findpapers.core.paper.Paper.databases`."""

    supports_forward: bool = False
    """CrossRef does not expose a forward-citation (cited-by) endpoint."""

    def __init__(self, email: str | None = None) -> None:
        """Create a CrossRef connector.

        Parameters
        ----------
        email : str | None
            Contact email for the CrossRef polite pool.
        """
        super().__init__()
        self._email = email

    @property
    def name(self) -> str:
        """Return the connector identifier.

        Returns
        -------
        str
            ``"crossref"``.
        """
        return self._DATABASE_NAME

    @property
    def min_request_interval(self) -> float:
        """Return the minimum seconds between HTTP requests.

        Returns
        -------
        float
            Interval in seconds.
        """
        return _MIN_REQUEST_INTERVAL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_paper_by_doi(self, doi: str) -> Paper | None:
        """Fetch a paper by DOI using the CrossRef ``/works/{doi}`` endpoint.

        Convenience wrapper that calls :meth:`fetch_work` then
        :meth:`build_paper`.

        Parameters
        ----------
        doi : str
            Bare DOI (without ``https://doi.org/`` prefix).

        Returns
        -------
        Paper | None
            Populated paper, or ``None`` when the DOI is not found or the
            record is missing required fields.
        """
        work = self.fetch_work(doi)
        if work is None:
            return None
        return self.build_paper(work)

    def fetch_work(self, doi: str) -> dict[str, Any] | None:
        """Fetch the CrossRef ``/works/{doi}`` record.

        Uses the inherited rate-limiting and logging infrastructure.  A 404
        response is treated as a normal "not found" case and returns ``None``.

        Parameters
        ----------
        doi : str
            Bare DOI (without ``https://doi.org/`` prefix),
            e.g. ``10.1038/nature12373``.

        Returns
        -------
        dict[str, Any] | None
            The ``message`` portion of the CrossRef response, or ``None``
            when the DOI is not found (404).

        Raises
        ------
        requests.HTTPError
            On non-404 HTTP errors (propagated so the caller can decide
            on retries).
        """
        url = f"{_CROSSREF_API_URL}/{_url_quote(doi, safe='')}"

        try:
            response = self._get(url)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.debug("CrossRef: DOI %s not found (404)", doi)
                return None
            raise

        data: dict[str, Any] = response.json()
        message = data.get("message")
        return message if isinstance(message, dict) else None

    def build_paper(self, work: dict[str, Any]) -> Paper | None:
        """Build a :class:`~findpapers.core.paper.Paper` from a CrossRef work record.

        Delegates to :meth:`_build_paper`.

        Parameters
        ----------
        work : dict[str, Any]
            The ``message`` dict returned by :meth:`fetch_work`.

        Returns
        -------
        Paper | None
            Populated paper, or ``None`` when required fields (title) are
            missing.
        """
        return self._build_paper(work)

    # ------------------------------------------------------------------
    # Citation interface (CitationConnectorBase)
    # ------------------------------------------------------------------

    def get_expected_counts(self, paper: Paper) -> tuple[int | None, int | None]:
        """Return expected citation and reference counts for *paper*.

        CrossRef does not expose forward citation counts, so
        ``citation_count`` is always ``None``.  The reference count is
        derived from the ``reference`` array in the work record.

        Parameters
        ----------
        paper : Paper
            The paper whose counts are requested.

        Returns
        -------
        tuple[int | None, int | None]
            ``(None, reference_count)``.
        """
        if not paper.doi:
            return None, None

        ref_count: int | None = None
        try:
            work = self.fetch_work(paper.doi)
            if work:
                raw_refs = work.get("reference") or []
                ref_count = sum(
                    1
                    for entry in raw_refs
                    if isinstance(entry, dict) and (entry.get("DOI") or "").strip()
                )
        except requests.RequestException:
            pass

        return None, ref_count

    def fetch_references(
        self,
        paper: Paper,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Fetch papers referenced by *paper* via the CrossRef ``reference`` list.

        Each CrossRef work record may contain a ``reference`` array whose
        entries occasionally carry a ``DOI`` field.  This method extracts
        those DOIs, fetches each one through :meth:`fetch_work`, and
        converts the result to a :class:`~findpapers.core.paper.Paper`.

        Parameters
        ----------
        paper : Paper
            The paper whose references should be retrieved.
        progress_callback : Callable[[int], None] | None
            Optional callback for per-page progress reporting.

        Returns
        -------
        list[Paper]
            Papers corresponding to the DOIs found in the reference list.
            References without a DOI or that fail to resolve are silently
            skipped.
        """
        if not paper.doi:
            return []

        try:
            work = self.fetch_work(paper.doi)
        except requests.RequestException:
            logger.debug("CrossRef: failed to fetch work for DOI %s", paper.doi)
            return []

        if not work:
            return []

        raw_refs = work.get("reference") or []
        ref_dois: list[str] = []
        for entry in raw_refs:
            if isinstance(entry, dict):
                doi_val = (entry.get("DOI") or "").strip()
                if doi_val:
                    ref_dois.append(doi_val)

        papers: list[Paper] = []
        for ref_doi in ref_dois:
            try:
                ref_work = self.fetch_work(ref_doi)
            except requests.RequestException:
                logger.debug("CrossRef: could not fetch reference DOI %s", ref_doi)
            else:
                if ref_work:
                    ref_paper = self.build_paper(ref_work)
                    if ref_paper:
                        papers.append(ref_paper)
            if progress_callback is not None:
                progress_callback(1)

        return papers

    def fetch_cited_by(
        self,
        paper: Paper,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Return papers that cite *paper*.

        The CrossRef REST API does not provide a direct endpoint for
        forward citation lookups, so this method always returns an empty
        list.  Forward snowballing is handled by other connectors
        (OpenAlex, Semantic Scholar).

        Parameters
        ----------
        paper : Paper
            Ignored.
        progress_callback : Callable[[int], None] | None
            Unused.  Accepted for interface compatibility.

        Returns
        -------
        list[Paper]
            Always an empty list.
        """
        return []

    # ------------------------------------------------------------------
    # Static helpers — pure parsing, no instance state needed
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(work: dict[str, Any]) -> datetime.date | None:
        """Extract the best publication date from a CrossRef work record.

        CrossRef stores dates in several fields, each as
        ``{"date-parts": [[year, month, day]]}``.  Not all parts are always
        present, so missing month/day default to 1.

        Priority order: ``published-print`` → ``published-online`` →
        ``published`` → ``issued`` → ``created``.

        Parameters
        ----------
        work : dict[str, Any]
            CrossRef work JSON (the ``message`` dict).

        Returns
        -------
        datetime.date | None
            Parsed date, or ``None`` when no usable date field is available.
        """
        for field in (
            "published-print",
            "published-online",
            "published",
            "issued",
            "created",
        ):
            date_obj = work.get(field)
            if not date_obj or not isinstance(date_obj, dict):
                continue
            parts = date_obj.get("date-parts")
            if not parts or not isinstance(parts, list) or not parts[0]:
                continue
            nums = parts[0]
            if not isinstance(nums, list) or not nums:
                continue
            try:
                year = int(nums[0])
                month = int(nums[1]) if len(nums) > 1 else 1
                day = int(nums[2]) if len(nums) > 2 else 1
                return datetime.date(year, month, day)
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _parse_authors(work: dict[str, Any]) -> list[Author]:
        """Parse authors from a CrossRef work record.

        Each author entry contains ``given`` and ``family`` name fields, and
        optionally an ``affiliation`` list.

        Parameters
        ----------
        work : dict[str, Any]
            CrossRef work JSON.

        Returns
        -------
        list[Author]
            Author objects with affiliations when available.
        """
        authors: list[Author] = []
        for entry in work.get("author", []):
            if not isinstance(entry, dict):
                continue
            given = (entry.get("given") or "").strip()
            family = (entry.get("family") or "").strip()
            if not family:
                # Some records have only ``name`` (e.g. organisational authors).
                name = (entry.get("name") or "").strip()
            else:
                name = f"{given} {family}".strip() if given else family

            if not name:
                continue

            # Affiliations — CrossRef stores them as [{"name": "..."}].
            aff_parts: list[str] = []
            for aff in entry.get("affiliation", []):
                if isinstance(aff, dict):
                    aff_name = (aff.get("name") or "").strip()
                    if aff_name:
                        aff_parts.append(aff_name)
            affiliation = "; ".join(aff_parts) if aff_parts else None
            authors.append(Author(name=name, affiliation=affiliation))
        return authors

    @staticmethod
    def _strip_jats_tags(text: str) -> str:
        """Remove JATS/HTML markup from CrossRef abstract text.

        CrossRef often returns abstracts wrapped in JATS XML tags such as
        ``<jats:p>`` or ``<jats:title>``.

        Parameters
        ----------
        text : str
            Raw abstract text potentially containing XML tags.

        Returns
        -------
        str
            Plain text with tags removed.
        """
        return _TAG_RE.sub("", text).strip()

    @staticmethod
    def _parse_keywords(work: dict[str, Any]) -> set[str]:
        """Extract keywords/subjects from a CrossRef work record.

        CrossRef stores keywords in the ``subject`` field (list of strings).

        Parameters
        ----------
        work : dict[str, Any]
            CrossRef work JSON.

        Returns
        -------
        set[str]
            Keyword set, possibly empty.
        """
        keywords: set[str] = set()
        for subj in work.get("subject", []):
            if isinstance(subj, str) and subj.strip():
                keywords.add(subj.strip())
        return keywords

    @staticmethod
    def _parse_pdf_url(work: dict[str, Any]) -> str | None:
        """Extract a direct PDF link from CrossRef ``link`` entries.

        Parameters
        ----------
        work : dict[str, Any]
            CrossRef work JSON.

        Returns
        -------
        str | None
            PDF URL, or ``None`` when no PDF link is available.
        """
        for link in work.get("link", []):
            if not isinstance(link, dict):
                continue
            content_type = (link.get("content-type") or "").lower()
            url = (link.get("URL") or "").strip()
            if "pdf" in content_type and url:
                return url
        return None

    @staticmethod
    def _parse_crossref_source(work: dict[str, Any]) -> Source | None:
        """Build a :class:`~findpapers.core.source.Source` from a CrossRef work.

        Parameters
        ----------
        work : dict[str, Any]
            CrossRef work record.

        Returns
        -------
        Source | None
            Populated source or ``None`` when no container title is present.
        """
        container_titles = work.get("container-title") or []
        source_title = (
            container_titles[0].strip()
            if isinstance(container_titles, list) and container_titles
            else ""
        )
        if not source_title:
            return None
        issn_list = work.get("ISSN") or []
        issn = issn_list[0] if isinstance(issn_list, list) and issn_list else None
        isbn_list = work.get("ISBN") or []
        isbn = isbn_list[0] if isinstance(isbn_list, list) and isbn_list else None
        publisher = (work.get("publisher") or "").strip() or None
        crossref_type = (work.get("type") or "").strip().lower()
        return Source(
            title=source_title,
            issn=issn,
            isbn=isbn,
            publisher=publisher,
            source_type=_CROSSREF_TYPE_MAP.get(crossref_type),
        )

    @staticmethod
    def _build_paper(work: dict[str, Any]) -> Paper | None:
        """Build a :class:`~findpapers.core.paper.Paper` from a CrossRef work record.

        Parameters
        ----------
        work : dict[str, Any]
            The ``message`` dict returned by :meth:`fetch_work`.

        Returns
        -------
        Paper | None
            Populated paper, or ``None`` when required fields (title) are
            missing.
        """
        if not work:
            return None

        # Title — CrossRef returns it as a list of strings.
        titles = work.get("title") or []
        title = titles[0].strip() if isinstance(titles, list) and titles else ""
        if not title:
            return None

        # Abstract
        raw_abstract = (work.get("abstract") or "").strip()
        abstract = CrossRefConnector._strip_jats_tags(raw_abstract) if raw_abstract else ""

        # DOI
        doi: str | None = (work.get("DOI") or "").strip() or None

        # Authors
        authors = CrossRefConnector._parse_authors(work)

        # Publication date
        publication_date = CrossRefConnector._parse_date(work)

        # Keywords / subjects
        keywords = CrossRefConnector._parse_keywords(work)

        # Citations count
        citations: int | None = work.get("is-referenced-by-count")

        # Page range
        pages: str | None = (work.get("page") or "").strip() or None

        # Number of pages — not directly available, but can be inferred from
        # page range when it's in "first-last" format.
        page_count: int | None = None

        # PDF URL
        pdf_url = CrossRefConnector._parse_pdf_url(work)

        # URL — prefer the canonical publisher landing page from
        # ``resource.primary.URL`` (the final redirect target), falling back
        # to ``URL`` which is typically the doi.org resolver URL.
        resource = work.get("resource")
        url: str | None = None
        if isinstance(resource, dict):
            primary = resource.get("primary")
            if isinstance(primary, dict):
                url = (primary.get("URL") or "").strip() or None
        if not url:
            url = (work.get("URL") or "").strip() or None

        source = CrossRefConnector._parse_crossref_source(work)

        return Paper(
            title=title,
            abstract=abstract,
            authors=authors,
            source=source,
            publication_date=publication_date,
            url=url,
            pdf_url=pdf_url,
            doi=doi,
            citations=citations,
            keywords=keywords or None,
            page_range=pages,
            page_count=page_count,
            databases={CrossRefConnector._DATABASE_NAME},
        )
