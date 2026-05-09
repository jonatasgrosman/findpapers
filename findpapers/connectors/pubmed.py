"""PubMed searcher implementation."""

from __future__ import annotations

import contextlib
import datetime
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

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
from findpapers.query.builders.pubmed import PubmedQueryBuilder
from findpapers.utils.normalization import normalize_language

logger = logging.getLogger(__name__)

_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_PAGE_SIZE = 100
# Rate limit: 3 req/s without API key, 10 req/s with API key
_MIN_REQUEST_INTERVAL_DEFAULT = 0.34  # ~3 req/s
_MIN_REQUEST_INTERVAL_WITH_KEY = 0.11  # ~10 req/s

# Regex that matches PubMed landing-page URLs and captures the PMID.
# Handles:
#   https://pubmed.ncbi.nlm.nih.gov/12345678
#   https://pubmed.ncbi.nlm.nih.gov/12345678/
#   https://www.ncbi.nlm.nih.gov/pubmed/12345678
_PUBMED_URL_RE = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d+)",
    re.IGNORECASE,
)


class PubmedConnector(SearchConnectorBase, DOILookupConnectorBase, URLLookupConnectorBase):
    """Connector for the PubMed / NCBI database.

    Uses NCBI E-utilities (esearch + efetch):
    https://www.ncbi.nlm.nih.gov/books/NBK25500/

    Rate limits:
    - Without API key: 3 requests/second
    - With API key: 10 requests/second
    """

    # Ordered list of (PubMed PublicationType UI prefix, PaperType) pairs.
    # Checked in priority order; first match wins.
    _PUBMED_PAPER_TYPE_RULES: ClassVar[list[tuple[str, PaperType]]] = [
        ("congress", PaperType.INPROCEEDINGS),
        ("meeting abstract", PaperType.INPROCEEDINGS),
        ("academic dissertation", PaperType.PHDTHESIS),
        ("technical report", PaperType.TECHREPORT),
        ("preprint", PaperType.UNPUBLISHED),
        ("journal article", PaperType.ARTICLE),
        ("review", PaperType.ARTICLE),
        ("systematic review", PaperType.ARTICLE),
        ("meta-analysis", PaperType.ARTICLE),
    ]

    def __init__(
        self,
        query_builder: PubmedQueryBuilder | None = None,
        api_key: str | None = None,
    ) -> None:
        """Create a PubMed searcher.

        Parameters
        ----------
        query_builder : PubmedQueryBuilder | None
            Builder used to validate and convert queries.  When ``None`` a
            default :class:`PubmedQueryBuilder` is created automatically.
        api_key : str | None
            NCBI API key (increases rate limit from 3 to 10 req/s).
        """
        super().__init__()
        self._query_builder: PubmedQueryBuilder = query_builder or PubmedQueryBuilder()
        self._api_key = api_key
        self._request_interval = (
            _MIN_REQUEST_INTERVAL_WITH_KEY if api_key else _MIN_REQUEST_INTERVAL_DEFAULT
        )

        if not api_key:
            logger.warning(
                "No API key provided for PubMed. "
                "Without a key, the rate limit is 3 requests/second "
                "(instead of 10 req/s with a key). Request a free key at "
                "https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/"
            )

    @property
    def name(self) -> str:
        """Return the database identifier.

        Returns
        -------
        str
            Database name.
        """
        return Database.PUBMED.value

    @property
    def query_builder(self) -> QueryBuilder:
        """Return the PubMed query builder.

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

    def _prepare_params(self, params: dict) -> dict:
        """Inject the NCBI API key into query parameters when configured.

        Parameters
        ----------
        params : dict
            Raw query parameters.

        Returns
        -------
        dict
            Parameters with ``api_key`` added when an API key is set.
        """
        if self._api_key:
            return {**params, "api_key": self._api_key}
        return params

    # ------------------------------------------------------------------
    # URL lookup
    # ------------------------------------------------------------------

    @property
    def url_pattern(self) -> re.Pattern[str]:
        """Return the regex matching PubMed landing-page URLs.

        Returns
        -------
        re.Pattern[str]
            Compiled regex whose first capture group is the PMID.
        """
        return _PUBMED_URL_RE

    def fetch_paper_by_id(self, paper_id: str) -> Paper | None:
        """Fetch a single PubMed paper by its PMID.

        Parameters
        ----------
        paper_id : str
            PubMed ID (PMID), e.g. ``"12345678"``.

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the paper is not found or the response cannot be parsed.
        """
        try:
            articles = self._fetch_details([paper_id])
        except (requests.RequestException, ET.ParseError):
            logger.debug("PubMed: efetch failed for PMID %s.", paper_id)
            return None

        if not articles:
            logger.debug("PubMed: PMID %s not found.", paper_id)
            return None

        return self._parse_paper(articles[0])

    # ------------------------------------------------------------------
    # DOI lookup
    # ------------------------------------------------------------------

    def fetch_paper_by_doi(self, doi: str) -> Paper | None:
        """Fetch a single paper by its DOI from PubMed.

        Uses the NCBI E-Search ``{doi}[doi]`` term to locate the PMID,
        then fetches full metadata via E-Fetch.

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
        try:
            ids, _ = self._search_ids(f"{doi}[doi]", retstart=0, retmax=1)
        except (requests.RequestException, ValueError):
            logger.debug("PubMed: esearch failed for DOI %s.", doi)
            return None

        if not ids:
            logger.debug("PubMed: DOI %s not found.", doi)
            return None

        return self.fetch_paper_by_id(ids[0])

    def _search_ids(
        self,
        pubmed_query: str,
        retstart: int,
        retmax: int,
        date_params: dict[str, str] | None = None,
    ) -> tuple[list[str], int]:
        """Fetch PMIDs via esearch.

        Parameters
        ----------
        pubmed_query : str
            Converted PubMed query string.
        retstart : int
            Pagination offset.
        retmax : int
            Maximum results per page.
        date_params : dict[str, str] | None
            Optional date-range filters (datetype, mindate, maxdate).

        Returns
        -------
        tuple[list[str], int]
            List of PMIDs and total result count.
        """
        params = {
            "db": "pubmed",
            "term": pubmed_query,
            "retmode": "json",
            "sort": "pub_date",
            "retstart": retstart,
            "retmax": retmax,
            **(date_params or {}),
        }
        response = self._get(_ESEARCH_URL, params)
        data = response.json()
        esearch_result = data.get("esearchresult", {})
        ids = esearch_result.get("idlist", [])
        total = int(esearch_result.get("count", 0))
        return ids, total

    def _fetch_details(self, pmids: list[str]) -> list[Element]:
        """Fetch full records for a list of PMIDs via efetch.

        Parameters
        ----------
        pmids : list[str]
            PubMed IDs to fetch.

        Returns
        -------
        list[Element]
            List of PubmedArticle XML elements.
        """
        if not pmids:
            return []
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        response = self._get(_EFETCH_URL, params)
        tree = ET.fromstring(response.text)
        return tree.findall(".//PubmedArticle")

    def _parse_paper(self, article_el: Element) -> Paper | None:
        """Parse a PubmedArticle element into a :class:`Paper`.

        Parameters
        ----------
        article_el : Element
            ``PubmedArticle`` XML element.

        Returns
        -------
        Paper | None
            Parsed paper or ``None`` when required fields are missing.
        """
        medline = article_el.find("MedlineCitation")
        if medline is None:
            return None

        article = medline.find("Article")
        if article is None:
            return None

        # Title – use itertext() to handle inline markup (e.g. <i>, <sub>)
        title_el = article.find("ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""
        if not title:
            return None

        # Abstract
        abstract_parts = [
            "".join(text_el.itertext()).strip() for text_el in article.findall(".//AbstractText")
        ]
        abstract = " ".join(filter(None, abstract_parts))

        authors = self._parse_pubmed_authors(article)
        pub_date = self._parse_pubmed_pub_date(article, article_el)
        doi = self._parse_pubmed_doi(article_el)
        url = self._parse_pubmed_url(medline)
        keywords, subjects = self._parse_pubmed_keywords_subjects(article_el)
        pages = self._parse_pubmed_pages(article)
        source = self._parse_pubmed_source(article)
        paper_type, is_retracted = self._parse_pubmed_type_retracted(article)

        # Language — first <Language> element inside the Article
        language: str | None = None
        lang_el = article.find(".//Language")
        if lang_el is not None and lang_el.text:
            language = normalize_language(lang_el.text.strip())

        funders = self._parse_pubmed_funders(article_el)

        try:
            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                source=source,
                publication_date=pub_date,
                url=url,
                doi=doi,
                keywords=keywords if keywords else None,
                page_range=pages,
                databases={self.name},
                paper_type=paper_type,
                subjects=subjects if subjects else None,
                language=language,
                is_retracted=is_retracted,
                funders=funders if funders else None,
            )
        except ValueError:
            return None

        return paper

    @staticmethod
    def _parse_pubmed_authors(article: Element) -> list[Author]:
        """Extract authors with affiliations from a PubMed Article element.

        Parameters
        ----------
        article : Element
            ``Article`` XML element.

        Returns
        -------
        list[Author]
            Parsed author list.
        """
        authors: list[Author] = []
        for author_el in article.findall(".//Author"):
            last = (author_el.findtext("LastName") or "").strip()
            fore = (author_el.findtext("ForeName") or "").strip()
            initials = (author_el.findtext("Initials") or "").strip()
            if last and fore:
                name = f"{fore} {last}"
            elif last and initials:
                name = f"{initials} {last}"
            elif last:
                name = last
            else:
                continue
            aff_parts = [
                (aff_el.text or "").strip()
                for aff_el in author_el.findall(".//AffiliationInfo/Affiliation")
                if aff_el is not None and (aff_el.text or "").strip()
            ]
            affiliation = "; ".join(aff_parts) if aff_parts else None
            authors.append(Author(name=name, affiliation=affiliation))
        return authors

    @staticmethod
    def _parse_pubmed_pub_date(article: Element, article_el: Element) -> datetime.date | None:
        """Resolve the publication date for a PubMed paper.

        Prefers ``ArticleDate`` (electronic) over ``PubDate`` (print).

        Parameters
        ----------
        article : Element
            ``Article`` XML element.
        article_el : Element
            ``PubmedArticle`` root XML element (for ``PubDate`` fallback).

        Returns
        -------
        datetime.date | None
            Parsed date or ``None``.
        """
        article_date_el = article.find("ArticleDate")
        if article_date_el is not None:
            pub_date = _parse_date_element(article_date_el)
            if pub_date is not None:
                return pub_date
        pub_date_el = article_el.find(".//PubDate")
        if pub_date_el is not None:
            return _parse_date_element(pub_date_el)
        return None

    @staticmethod
    def _parse_pubmed_doi(article_el: Element) -> str | None:
        """Extract DOI from PubMed ArticleId elements.

        Parameters
        ----------
        article_el : Element
            ``PubmedArticle`` root XML element.

        Returns
        -------
        str | None
            DOI string or ``None``.
        """
        for id_el in article_el.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi" and id_el.text and id_el.text.strip():
                return id_el.text.strip()
        return None

    @staticmethod
    def _parse_pubmed_url(medline: Element) -> str | None:
        """Build a PubMed URL from the PMID element.

        Parameters
        ----------
        medline : Element
            ``MedlineCitation`` XML element.

        Returns
        -------
        str | None
            Full PubMed URL or ``None``.
        """
        pmid_el = medline.find("PMID")
        if pmid_el is not None and pmid_el.text and pmid_el.text.strip():
            return f"https://pubmed.ncbi.nlm.nih.gov/{pmid_el.text.strip()}/"
        return None

    @staticmethod
    def _parse_pubmed_keywords_subjects(
        article_el: Element,
    ) -> tuple[set[str], set[str]]:
        """Extract keywords and MeSH-based subjects from a PubMed article.

        Parameters
        ----------
        article_el : Element
            ``PubmedArticle`` root XML element.

        Returns
        -------
        tuple[set[str], set[str]]
            ``(keywords, subjects)`` sets.
        """
        keywords: set[str] = set()
        for kw_el in article_el.findall(".//Keyword"):
            kw = (kw_el.text or "").strip()
            if kw:
                keywords.add(kw)
        for mh_el in article_el.findall(".//DescriptorName"):
            kw = (mh_el.text or "").strip()
            if kw:
                keywords.add(kw)
        subjects: set[str] = set()
        for mh_el in article_el.findall(".//MeshHeading/DescriptorName"):
            if mh_el.get("MajorTopicYN") == "Y":
                descriptor = (mh_el.text or "").strip()
                if descriptor:
                    subjects.add(descriptor)
        return keywords, subjects

    @staticmethod
    def _parse_pubmed_pages(article: Element) -> str | None:
        """Extract page range from a PubMed Article element.

        Parameters
        ----------
        article : Element
            ``Article`` XML element.

        Returns
        -------
        str | None
            Page range string or ``None``.
        """
        pagination_el = article.find(".//Pagination")
        if pagination_el is None:
            return None
        medline_pgn = (pagination_el.findtext("MedlinePgn") or "").strip()
        if medline_pgn:
            return medline_pgn
        start_pg = (pagination_el.findtext("StartPage") or "").strip()
        end_pg = (pagination_el.findtext("EndPage") or "").strip()
        if start_pg and end_pg:
            return f"{start_pg}\u2013{end_pg}"
        return start_pg or None

    @staticmethod
    def _parse_pubmed_source(article: Element) -> Source | None:
        """Build a :class:`~findpapers.core.source.Source` from a PubMed Article.

        Parameters
        ----------
        article : Element
            ``Article`` XML element.

        Returns
        -------
        Source | None
            Journal source or ``None`` when no usable journal is found.
        """
        journal_el = article.find(".//Journal")
        if journal_el is None:
            return None
        journal_title = journal_el.findtext("Title") or ""
        abbrev = journal_el.findtext("ISOAbbreviation") or ""
        pub_title = journal_title or abbrev
        issn_el = journal_el.find("ISSN")
        issn = (issn_el.text or "").strip() if issn_el is not None else None
        if pub_title.strip():
            return Source(title=pub_title.strip(), issn=issn, source_type=SourceType.JOURNAL)
        return None

    def _parse_pubmed_type_retracted(self, article: Element) -> tuple[PaperType | None, bool]:
        """Infer paper type and retraction status from PublicationTypeList.

        Parameters
        ----------
        article : Element
            ``Article`` XML element.

        Returns
        -------
        tuple[PaperType | None, bool]
            ``(paper_type, is_retracted)`` pair.
        """
        pub_type_texts = [
            (pt_el.text or "").strip().lower()
            for pt_el in article.findall(".//PublicationTypeList/PublicationType")
            if pt_el.text
        ]
        paper_type: PaperType | None = None
        for rule_key, rule_type in self._PUBMED_PAPER_TYPE_RULES:
            if any(rule_key in pt for pt in pub_type_texts):
                paper_type = rule_type
                break
        is_retracted = "retracted publication" in pub_type_texts
        return paper_type, is_retracted

    @staticmethod
    def _parse_pubmed_funders(article_el: Element) -> set[str]:
        """Extract funder names from PubMed GrantList.

        Parameters
        ----------
        article_el : Element
            ``PubmedArticle`` root XML element.

        Returns
        -------
        set[str]
            Funder name set.
        """
        funders: set[str] = set()
        for grant_el in article_el.findall(".//GrantList/Grant"):
            agency = (grant_el.findtext("Agency") or "").strip()
            if agency:
                funders.add(agency)
        return funders

    def _fetch_papers(
        self,
        query: Query,
        max_papers: int | None,
        progress_callback: Callable[[int, int | None], None] | None,
        since: datetime.date | None = None,
        until: datetime.date | None = None,
    ) -> list[Paper]:
        """Fetch papers from PubMed with pagination (esearch + efetch).

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
        pubmed_query = self._query_builder.convert_query(query)

        # Build date range parameters for PubMed esearch.
        date_params: dict[str, str] = {}
        if since or until:
            date_params["datetype"] = "pdat"  # publication date
            if since:
                date_params["mindate"] = since.strftime("%Y/%m/%d")
            if until:
                date_params["maxdate"] = until.strftime("%Y/%m/%d")
        papers: list[Paper] = []
        processed = 0
        offset = 0
        total: int | None = None

        while True:
            remaining = (max_papers - len(papers)) if max_papers is not None else _PAGE_SIZE
            page_size = min(_PAGE_SIZE, remaining)
            if page_size <= 0:
                break

            try:
                ids, total = self._search_ids(pubmed_query, offset, page_size, date_params)
            except (requests.RequestException, ValueError) as exc:
                logger.warning("PubMed esearch failed (offset=%d): %s", offset, exc)
                logger.debug("PubMed esearch exception details:", exc_info=True)
                break

            if not ids:
                break

            try:
                article_elements = self._fetch_details(ids)
            except (requests.RequestException, ET.ParseError) as exc:
                logger.warning("PubMed efetch failed (pmids=%s): %s", ids, exc)
                logger.debug("PubMed efetch exception details:", exc_info=True)
                break

            for el in article_elements:
                paper = self._parse_paper(el)
                if paper is not None:
                    papers.append(paper)

            processed += len(ids)
            if progress_callback is not None:
                progress_callback(processed, total)

            if max_papers is not None and len(papers) >= max_papers:
                break

            if len(ids) < page_size:
                break

            offset += len(ids)

        # Ensure the progress bar is updated even when the loop exits early
        # (e.g. on the first request returning no IDs or a request error),
        # so the bar never stays frozen at its initial 0-paper state.
        if progress_callback is not None:
            progress_callback(processed, total)

        return papers[:max_papers] if max_papers is not None else papers


def _normalize_month(month: str) -> str:
    """Normalize month string to two-digit format.

    Parameters
    ----------
    month : str
        Month as number string or abbreviated name.

    Returns
    -------
    str
        Zero-padded two-digit month string.
    """
    _month_map = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    lowered = month.lower()[:3]
    if lowered in _month_map:
        return _month_map[lowered]
    try:
        return f"{int(month):02d}"
    except ValueError:
        return "01"


def _parse_date_element(el: Element) -> datetime.date | None:
    """Parse a date from a PubMed XML element containing Year/Month/Day children.

    Parameters
    ----------
    el : Element
        XML element with optional ``Year``, ``Month``, and ``Day`` sub-elements.

    Returns
    -------
    datetime.date | None
        Parsed date, or ``None`` when the year is missing or unparseable.
    """
    year = (el.findtext("Year") or "").strip()
    if not year:
        return None
    month = (el.findtext("Month") or "01").strip()
    day = (el.findtext("Day") or "01").strip()
    month = _normalize_month(month)
    with contextlib.suppress(ValueError):
        return datetime.date.fromisoformat(f"{year}-{month}-{day}")
    return None
