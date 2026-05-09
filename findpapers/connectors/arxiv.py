"""arXiv searcher implementation."""

from __future__ import annotations

import contextlib
import datetime
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import requests
from defusedxml import ElementTree as ET

if TYPE_CHECKING:
    # Element is the concrete type returned by defusedxml at runtime;
    # we import it from stdlib only for static type annotations.
    from xml.etree.ElementTree import Element  # nosec B405

from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.search_base import SearchConnectorBase
from findpapers.connectors.url_lookup_base import URLLookupConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Database, Paper, PaperType
from findpapers.core.query import Query
from findpapers.core.source import Source, SourceType
from findpapers.query.builder import QueryBuilder
from findpapers.query.builders.arxiv import ArxivQueryBuilder
from findpapers.utils.arxiv_taxonomy import arxiv_category_to_field, arxiv_category_to_subject
from findpapers.utils.normalization import parse_date

logger = logging.getLogger(__name__)

_BASE_URL = "https://export.arxiv.org/api/query"
_PAGE_SIZE = 100
# arXiv recommends at least 3 seconds between requests
_MIN_REQUEST_INTERVAL = 3.0
_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# Regex to extract the arXiv paper ID from the Atom <id> element.
# Example: http://arxiv.org/abs/1706.03762v5 → 1706.03762
_ARXIV_ID_RE = re.compile(r"arxiv\.org/abs/([\d.]+)", re.IGNORECASE)

# Regex to extract arXiv paper ID from an arXiv-assigned DOI.
# arXiv assigns DOIs under the 10.48550 prefix: 10.48550/arXiv.1706.03762
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.([\d.]+)$", re.IGNORECASE)

# Regex that matches arXiv abstract or PDF landing-page URLs and captures the
# paper ID (without version suffix).  Used by URLLookupConnectorBase.
# Examples:
#   https://arxiv.org/abs/1706.03762
#   https://arxiv.org/abs/1706.03762v3
#   https://arxiv.org/pdf/1706.03762v5
_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)

# Mapping from SourceType to PaperType for arXiv entries.
_ARXIV_PAPER_TYPE_MAP: dict[SourceType, PaperType] = {
    SourceType.JOURNAL: PaperType.ARTICLE,
    SourceType.CONFERENCE: PaperType.INPROCEEDINGS,
    SourceType.BOOK: PaperType.INBOOK,
    SourceType.REPOSITORY: PaperType.UNPUBLISHED,
}


class ArxivConnector(SearchConnectorBase, DOILookupConnectorBase, URLLookupConnectorBase):
    """Connector for the arXiv preprint database.

    Uses the arXiv Atom Feed API:
    https://info.arxiv.org/help/api/user-manual.html

    Rate limit: 3 seconds between requests (as recommended by arXiv).
    """

    def __init__(self, query_builder: ArxivQueryBuilder | None = None) -> None:
        """Create an arXiv searcher.

        Parameters
        ----------
        query_builder : ArxivQueryBuilder | None
            Builder used to validate and convert queries.  When ``None`` a
            default :class:`ArxivQueryBuilder` is created automatically.
        """
        super().__init__()
        self._query_builder: ArxivQueryBuilder = query_builder or ArxivQueryBuilder()

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database name.
        """
        return Database.ARXIV.value

    @property
    def query_builder(self) -> QueryBuilder:
        """Return the arXiv query builder.

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

    # ------------------------------------------------------------------
    # URL lookup
    # ------------------------------------------------------------------

    @property
    def url_pattern(self) -> re.Pattern[str]:
        """Return the regex matching arXiv abstract and PDF URLs.

        Returns
        -------
        re.Pattern[str]
            Compiled regex whose first capture group is the arXiv paper ID.
        """
        return _ARXIV_URL_RE

    def fetch_paper_by_id(self, paper_id: str) -> Paper | None:
        """Fetch a single arXiv paper by its native ID.

        Parameters
        ----------
        paper_id : str
            arXiv paper ID (e.g. ``"1706.03762"``), without version suffix.

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the paper is not found or the response cannot be parsed.
        """
        try:
            response = self._get(_BASE_URL, params={"id_list": paper_id, "max_results": 1})
            tree = ET.fromstring(response.text)
        except (requests.RequestException, ET.ParseError):
            logger.debug("arXiv: failed to fetch arXiv ID %s.", paper_id)
            return None

        entries = tree.findall("atom:entry", _NS)
        if not entries:
            logger.debug("arXiv: no entry found for ID %s.", paper_id)
            return None

        return self._parse_paper(entries[0])

    # ------------------------------------------------------------------
    # DOI lookup
    # ------------------------------------------------------------------

    def fetch_paper_by_doi(self, doi: str) -> Paper | None:
        """Fetch a single paper by its DOI from arXiv.

        Only arXiv-assigned DOIs (``10.48550/arXiv.<id>``) are supported.
        For papers whose publisher DOI happens to appear on arXiv the arXiv
        API does not provide a DOI-based search, so ``None`` is returned.

        Parameters
        ----------
        doi : str
            Bare DOI identifier.

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the DOI is not an arXiv-native DOI, the paper is not found,
            or the response cannot be parsed.
        """
        m = _ARXIV_DOI_RE.match(doi.strip())
        if not m:
            # Not an arXiv-native DOI — cannot resolve via arXiv API.
            logger.debug("arXiv: DOI %s is not an arXiv-native DOI — skipping.", doi)
            return None

        return self.fetch_paper_by_id(m.group(1))

    @staticmethod
    def _parse_arxiv_authors(entry: Element) -> list[Author]:
        """Extract authors from an arXiv Atom entry element.

        Parameters
        ----------
        entry : Element
            Atom entry XML element.

        Returns
        -------
        list[Author]
            Parsed author list.
        """
        authors: list[Author] = []
        for author_el in entry.findall("atom:author", _NS):
            name_el = author_el.find("atom:name", _NS)
            if name_el is None or not (name_el.text or "").strip():
                continue
            name = (name_el.text or "").strip()
            affiliation_parts = [
                (aff_el.text or "").strip()
                for aff_el in author_el.findall("arxiv:affiliation", _NS)
                if aff_el is not None and (aff_el.text or "").strip()
            ]
            affiliation = "; ".join(affiliation_parts) if affiliation_parts else None
            authors.append(Author(name=name, affiliation=affiliation))
        return authors

    @staticmethod
    def _parse_arxiv_links(entry: Element) -> tuple[str | None, str | None]:
        """Extract HTML landing-page URL and PDF URL from an arXiv entry.

        Parameters
        ----------
        entry : Element
            Atom entry XML element.

        Returns
        -------
        tuple[str | None, str | None]
            ``(url, pdf_url)`` pair.
        """
        url: str | None = None
        for link_el in entry.findall("atom:link", _NS):
            rel = link_el.get("rel", "")
            href = link_el.get("href", "")
            if rel == "alternate" and href:
                url = href
                break
        if url is None:
            id_el = entry.find("atom:id", _NS)
            if id_el is not None and id_el.text:
                url = id_el.text.strip()
        pdf_url: str | None = None
        for link_el in entry.findall("atom:link", _NS):
            if (link_el.get("title") or "") == "pdf" and link_el.get("href"):
                pdf_url = link_el.get("href") or ""
                break
        return url, pdf_url

    @staticmethod
    def _parse_arxiv_doi(entry: Element, url: str | None) -> str | None:
        """Resolve the DOI for an arXiv entry.

        Prefers the explicit ``<arxiv:doi>`` element (publisher DOI).  When
        absent, derives the canonical arXiv DOI (``10.48550/arXiv.<id>``)
        from the landing-page URL.

        Parameters
        ----------
        entry : Element
            Atom entry XML element.
        url : str | None
            Landing-page URL already extracted from the entry.

        Returns
        -------
        str | None
            Resolved DOI or ``None``.
        """
        doi_el = entry.find("arxiv:doi", _NS)
        if doi_el is not None and doi_el.text:
            return doi_el.text.strip()
        if url:
            m = _ARXIV_ID_RE.search(url)
            if m:
                return f"10.48550/arXiv.{m.group(1)}"
        return None

    @staticmethod
    def _parse_arxiv_source(entry: Element) -> Source:
        """Build a :class:`~findpapers.core.source.Source` from an arXiv entry.

        Papers with a ``<arxiv:journal_ref>`` element were formally published;
        all others are arXiv preprints hosted in a repository.

        Parameters
        ----------
        entry : Element
            Atom entry XML element.

        Returns
        -------
        Source
            Populated source.
        """
        journal_ref_el = entry.find("arxiv:journal_ref", _NS)
        has_journal_ref = (
            journal_ref_el is not None and journal_ref_el.text and journal_ref_el.text.strip()
        )
        if has_journal_ref:
            ref_text = journal_ref_el.text.strip()  # type: ignore[union-attr]
            return Source(
                title=ref_text,
                source_type=_infer_source_type_from_journal_ref(ref_text),
            )
        return Source(title="arXiv", source_type=SourceType.REPOSITORY)

    @staticmethod
    def _parse_arxiv_categories(entry: Element) -> tuple[set[str], set[str]]:
        """Map arXiv category codes to fields of study and subjects.

        Parameters
        ----------
        entry : Element
            Atom entry XML element.

        Returns
        -------
        tuple[set[str], set[str]]
            ``(fields_of_study, subjects)`` sets.
        """
        fields_of_study: set[str] = set()
        subjects: set[str] = set()
        for cat_el in entry.findall("atom:category", _NS):
            term = (cat_el.get("term") or "").strip()
            if not term:
                continue
            field = arxiv_category_to_field(term)
            if field:
                fields_of_study.add(field)
            subject = arxiv_category_to_subject(term)
            if subject:
                subjects.add(subject)
        return fields_of_study, subjects

    def _parse_paper(self, entry: Element) -> Paper | None:
        """Parse a single Atom entry element into a :class:`Paper`.

        Parameters
        ----------
        entry : Element
            Atom entry XML element.

        Returns
        -------
        Paper | None
            Parsed paper or ``None`` when required fields are missing.
        """
        title_el = entry.find("atom:title", _NS)
        abstract_el = entry.find("atom:summary", _NS)
        if title_el is None or not (title_el.text or "").strip():
            return None

        title = (title_el.text or "").strip().replace("\n", " ")
        abstract = (
            (abstract_el.text or "").strip().replace("\n", " ") if abstract_el is not None else ""
        )

        authors = self._parse_arxiv_authors(entry)

        # Published date
        published_el = entry.find("atom:published", _NS)
        pub_date_str = parse_date(
            (published_el.text or "").strip() if published_el is not None else None
        )

        url, pdf_url = self._parse_arxiv_links(entry)
        doi = self._parse_arxiv_doi(entry, url)
        source = self._parse_arxiv_source(entry)

        # Comments — optional free-text note (e.g. "39 pages, 14 figures")
        comment: str | None = None
        comment_el = entry.find("arxiv:comment", _NS)
        if comment_el is not None and comment_el.text and comment_el.text.strip():
            comment = comment_el.text.strip()

        # Infer paper_type from source_type.
        paper_type: PaperType | None = None
        if source is not None and source.source_type is not None:
            paper_type = _ARXIV_PAPER_TYPE_MAP.get(source.source_type)

        fields_of_study, subjects = self._parse_arxiv_categories(entry)

        try:
            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                source=source,
                publication_date=pub_date_str,
                url=url,
                pdf_url=pdf_url,
                doi=doi,
                comments=comment,
                databases={self.name},
                paper_type=paper_type,
                fields_of_study=fields_of_study if fields_of_study else None,
                subjects=subjects if subjects else None,
                # All arXiv papers are open access by design.
                is_open_access=True,
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
        """Fetch papers from arXiv with pagination and rate limiting.

        Parameters
        ----------
        query : Query
            Validated query object.
        max_papers : int | None
            Maximum papers to retrieve.
        progress_callback : Callable[[int, int | None], None] | None
            Progress callback.
        since : datetime.date | None
            Only return papers submitted on or after this date.
        until : datetime.date | None
            Only return papers submitted on or before this date.

        Returns
        -------
        list[Paper]
            Retrieved papers.
        """
        arxiv_query = self._query_builder.convert_query(query)

        # Append arXiv submittedDate range filter when date bounds are given.
        # Use plain spaces – ``requests`` encodes them as ``+`` in the URL,
        # which is what the arXiv API expects.  Literal ``+`` characters were
        # previously double-encoded as ``%2B``, causing the filter to be
        # silently ignored.
        # When ``since`` is not provided we default to 1991-01-01 (arXiv
        # launch year) because year 0000 causes a server error.
        if since or until:
            from_date = since.strftime("%Y%m%d") + "0000" if since else "199101010000"
            to_date = until.strftime("%Y%m%d") + "2359" if until else "999912312359"
            date_filter = f"submittedDate:[{from_date} TO {to_date}]"
            arxiv_query = f"{arxiv_query} AND {date_filter}" if arxiv_query else date_filter
        papers: list[Paper] = []
        processed = 0
        offset = 0

        while True:
            remaining = (max_papers - len(papers)) if max_papers is not None else _PAGE_SIZE
            page_size = min(_PAGE_SIZE, remaining)

            params = {
                "search_query": arxiv_query,
                "start": offset,
                "max_results": page_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            try:
                response = self._get(_BASE_URL, params)
            except requests.RequestException:
                logger.debug("arXiv request failed (offset=%d).", offset, exc_info=True)
                break

            tree = ET.fromstring(response.text)

            total_results_el = tree.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
            total: int | None = None
            if total_results_el is not None and total_results_el.text:
                with contextlib.suppress(ValueError):
                    total = int(total_results_el.text.strip())

            entries = tree.findall("atom:entry", _NS)
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

        # Ensure the progress bar is updated even when the loop exits early
        # (e.g. on the first request returning no entries or a request error),
        # so the bar never stays frozen at its initial 0-paper state.
        if progress_callback is not None:
            progress_callback(processed, total)

        return papers[:max_papers] if max_papers is not None else papers


# ---------------------------------------------------------------------------
# Heuristic patterns to infer source type from arXiv journal_ref text
# ---------------------------------------------------------------------------

_CONFERENCE_RE = re.compile(
    r"\b(?:proceedings?|conference|workshop|symposium)\b" r"|\b(?:proc|conf|symp)\.",
    re.IGNORECASE,
)

_BOOK_RE = re.compile(
    r"\b(?:lecture\s+notes|book|chapter)\b",
    re.IGNORECASE,
)

_JOURNAL_RE = re.compile(
    r"\b(?:"
    r"journal|review[s]?|letters?|transactions?|annals?|bulletin"
    r"|magazine"
    r")\b"
    r"|\bj\."
    r"|\brev\."
    r"|\blett\."
    r"|\btrans\."
    r"|\bann\."
    r"|\bbull\."
    r"|\bmag\.",
    re.IGNORECASE,
)


def _infer_source_type_from_journal_ref(text: str) -> SourceType | None:
    """Infer a :class:`SourceType` from a free-text ``journal_ref`` string.

    The function applies keyword heuristics in priority order:

    1. **CONFERENCE** – contains words like *proceedings*, *conference*,
       *workshop*, or *symposium*.
    2. **BOOK** – contains *lecture notes*, *book*, or *chapter*.
    3. **JOURNAL** – contains common journal indicators such as *journal*,
       *review*, *letters*, *transactions*, abbreviated forms like
       *J.*, *Rev.*, *Lett.*, etc.

    If no pattern matches the text is left unclassified (``None``).

    Parameters
    ----------
    text : str
        The ``journal_ref`` value from an arXiv entry.

    Returns
    -------
    SourceType | None
        Inferred source type or ``None`` when no rule matches.
    """
    if _CONFERENCE_RE.search(text):
        return SourceType.CONFERENCE
    if _BOOK_RE.search(text):
        return SourceType.BOOK
    if _JOURNAL_RE.search(text):
        return SourceType.JOURNAL
    return None
