"""PubMed searcher implementation."""

from __future__ import annotations

import contextlib
import datetime
import logging
from collections.abc import Callable
from typing import ClassVar
import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

import requests

from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.search_base import SearchConnectorBase
from findpapers.core.author import Author
from findpapers.core.paper import Paper, PaperType
from findpapers.core.query import Query
from findpapers.core.search_result import Database
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


class PubmedConnector(SearchConnectorBase, DOILookupConnectorBase):
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

        try:
            articles = self._fetch_details(ids[:1])
        except (requests.RequestException, ET.ParseError, DefusedXmlException):
            logger.warning("PubMed: efetch failed for DOI %s (pmid=%s).", doi, ids[0])
            return None

        if not articles:
            return None

        return self._parse_paper(articles[0])

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

    def _fetch_details(self, pmids: list[str]) -> list[ET.Element]:
        """Fetch full records for a list of PMIDs via efetch.

        Parameters
        ----------
        pmids : list[str]
            PubMed IDs to fetch.

        Returns
        -------
        list[ET.Element]
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

    def _parse_paper(self, article_el: ET.Element) -> Paper | None:
        """Parse a PubmedArticle element into a :class:`Paper`.

        Parameters
        ----------
        article_el : ET.Element
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

        # Authors
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
            # PubMed provides affiliation info inside AffiliationInfo.
            aff_parts = [
                (aff_el.text or "").strip()
                for aff_el in author_el.findall(".//AffiliationInfo/Affiliation")
                if aff_el is not None and (aff_el.text or "").strip()
            ]
            affiliation = "; ".join(aff_parts) if aff_parts else None
            authors.append(Author(name=name, affiliation=affiliation))

        # Publication date
        # Prefer ArticleDate (electronic publication) over Journal/JournalIssue/PubDate
        # (print issue date).  PubMed's esearch ``pdat`` filter matches against
        # the electronic publication date, so using the same date here avoids a
        # mismatch where esearch returns a paper within the requested range but
        # the parsed date falls outside it (common with epub-ahead-of-print).
        pub_date: datetime.date | None = None

        article_date_el = article.find("ArticleDate")
        if article_date_el is not None:
            pub_date = _parse_date_element(article_date_el)

        if pub_date is None:
            pub_date_el = article.find(".//PubDate")
            if pub_date_el is not None:
                pub_date = _parse_date_element(pub_date_el)

        # DOI
        doi: str | None = None
        for id_el in article_el.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi" and id_el.text and id_el.text.strip():
                doi = id_el.text.strip()
                break

        # URL via PMID
        pmid_el = medline.find("PMID")
        url: str | None = None
        if pmid_el is not None and pmid_el.text and pmid_el.text.strip():
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid_el.text.strip()}/"

        # Keywords
        keywords: set[str] = set()
        for kw_el in article_el.findall(".//Keyword"):
            kw = (kw_el.text or "").strip()
            if kw:
                keywords.add(kw)
        for mh_el in article_el.findall(".//DescriptorName"):
            kw = (mh_el.text or "").strip()
            if kw:
                keywords.add(kw)

        # Subjects: MeSH descriptors marked as major topics of the paper.
        subjects: set[str] = set()
        for mh_el in article_el.findall(".//MeshHeading/DescriptorName"):
            if mh_el.get("MajorTopicYN") == "Y":
                descriptor = (mh_el.text or "").strip()
                if descriptor:
                    subjects.add(descriptor)

        # Pages
        pages: str | None = None
        pagination_el = article.find(".//Pagination")
        if pagination_el is not None:
            medline_pgn = (pagination_el.findtext("MedlinePgn") or "").strip()
            if medline_pgn:
                pages = medline_pgn
            else:
                start_pg = (pagination_el.findtext("StartPage") or "").strip()
                end_pg = (pagination_el.findtext("EndPage") or "").strip()
                if start_pg and end_pg:
                    pages = f"{start_pg}\u2013{end_pg}"
                elif start_pg:
                    pages = start_pg

        # Source (journal)
        journal_el = article.find(".//Journal")
        source: Source | None = None
        if journal_el is not None:
            journal_title = journal_el.findtext("Title") or ""
            abbrev = journal_el.findtext("ISOAbbreviation") or ""
            pub_title = journal_title or abbrev
            issn_el = journal_el.find("ISSN")
            issn = (issn_el.text or "").strip() if issn_el is not None else None
            if pub_title.strip():
                source = Source(
                    title=pub_title.strip(),
                    issn=issn,
                    source_type=SourceType.JOURNAL,
                )

        # Publication type (paper_type)
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

        # is_retracted — "Retracted Publication" means this paper was retracted.
        # ("Retraction of Publication" means the paper IS the retraction notice — not what we want.)
        is_retracted = "retracted publication" in pub_type_texts

        # Language — first <Language> element inside the Article
        language: str | None = None
        lang_el = article.find(".//Language")
        if lang_el is not None and lang_el.text:
            language = normalize_language(lang_el.text.strip())

        # Funders — Agency names from GrantList/Grant elements
        funders: set[str] = set()
        for grant_el in article_el.findall(".//GrantList/Grant"):
            agency = (grant_el.findtext("Agency") or "").strip()
            if agency:
                funders.add(agency)

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
            except (requests.RequestException, ValueError):
                logger.exception("PubMed esearch failed (offset=%d).", offset)
                break

            if not ids:
                break

            try:
                article_elements = self._fetch_details(ids)
            except (requests.RequestException, ET.ParseError, DefusedXmlException):
                logger.exception("PubMed efetch failed (pmids=%s).", ids)
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


def _parse_date_element(el: ET.Element) -> datetime.date | None:
    """Parse a date from a PubMed XML element containing Year/Month/Day children.

    Parameters
    ----------
    el : ET.Element
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
