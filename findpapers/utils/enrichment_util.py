from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

import requests
from lxml import html
from lxml.html import HtmlElement

from ..models import Paper, Publication

TITLE_META_KEYS = [
    "citation_title",
    "dc.title",
    "dc.title.alternative",
    "og:title",
    "twitter:title",
    "title",
]
ABSTRACT_META_KEYS = [
    "citation_abstract",
    "dc.description",
    "dc.description.abstract",
    "description",
    "og:description",
    "twitter:description",
]
AUTHOR_META_KEYS = [
    "citation_author",
    "dc.creator",
    "dc.contributor",
    "author",
]
DOI_META_KEYS = [
    "citation_doi",
    "dc.identifier",
    "doi",
    "prism.doi",
]
KEYWORDS_META_KEYS = [
    "citation_keywords",
    "keywords",
    "article:tag",
]
DATE_META_KEYS = [
    "citation_publication_date",
    "citation_date",
    "dc.date",
    "article:published_time",
    "prism.publicationdate",
]
PUBLICATION_TITLE_KEYS = [
    "citation_journal_title",
    "citation_conference_title",
    "citation_book_title",
]
PUBLICATION_PUBLISHER_KEYS = [
    "citation_publisher",
    "dc.publisher",
]
PUBLICATION_ISSN_KEYS = [
    "citation_issn",
    "prism.issn",
]
PUBLICATION_ISBN_KEYS = [
    "citation_isbn",
    "prism.isbn",
]
PDF_URL_KEYS = [
    "citation_pdf_url",
]


def fetch_metadata(url: str, timeout: float | None = None) -> dict[str, Any] | None:
    """Fetch metadata from a URL.

    Parameters
    ----------
    url : str
        URL to fetch.
    timeout : float | None
        Request timeout in seconds.

    Returns
    -------
    dict[str, Any] | None
        Parsed metadata or None.

    Raises
    ------
    requests.RequestException
        If the request fails.
    """
    response = requests.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return None
    return extract_metadata_from_html(response.text)


def extract_metadata_from_html(content: str) -> dict[str, Any]:
    """Extract metadata from HTML content.

    Parameters
    ----------
    content : str
        HTML content.

    Returns
    -------
    dict[str, Any]
        Metadata fields.
    """
    doc = html.fromstring(content)
    metadata: dict[str, Any] = {}
    # Collect all metadata tags, normalizing keys to lowercase.
    elements = doc.xpath("//meta[@name or @property or @itemprop]")
    if not isinstance(elements, list):
        return metadata
    for element in elements:
        if not isinstance(element, HtmlElement):
            continue
        key = (
            (element.get("name") or element.get("property") or element.get("itemprop") or "")
            .strip()
            .lower()
        )
        value = (element.get("content") or "").strip()
        if not key or not value:
            continue
        # Preserve multiple values for the same metadata key.
        if key in metadata:
            if not isinstance(metadata.get(key), list):
                metadata[key] = [metadata.get(key)]
            metadata[key].append(value)
        else:
            metadata[key] = value
    return metadata


def _pick_metadata_value(metadata: dict[str, Any], keys: Iterable[str]) -> str | None:
    """Pick the first matching metadata value.

    Parameters
    ----------
    metadata : dict[str, Any]
        Metadata mapping.
    keys : Iterable[str]
        Candidate keys in priority order.

    Returns
    -------
    str | None
        Selected value or None.
    """
    # Pick the first matching key with the richest value.
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


def _parse_date(value: str | None) -> date | None:
    """Parse a date string into a date.

    Parameters
    ----------
    value : str | None
        Date string.

    Returns
    -------
    date | None
        Parsed date or None.
    """
    if not value:
        return None
    value = value.strip()
    # Try common metadata date formats.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(value[:10], fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def _parse_keywords(value: str | None) -> set[str]:
    """Parse keywords from a comma/semicolon separated string.

    Parameters
    ----------
    value : str | None
        Raw keyword string.

    Returns
    -------
    set[str]
        Parsed keyword set.
    """
    if not value:
        return set()
    if "," in value:
        parts = value.split(",")
    elif ";" in value:
        parts = value.split(";")
    else:
        parts = [value]
    return {part.strip() for part in parts if part.strip()}


def _parse_authors(value: Any) -> list[str]:
    """Normalize author values into a list.

    Parameters
    ----------
    value : Any
        Raw author data.

    Returns
    -------
    list[str]
        Normalized author list.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(author).strip() for author in value if str(author).strip()]
    return [str(value).strip()]


def build_paper_from_metadata(metadata: dict[str, Any], page_url: str) -> Paper | None:
    """Build a Paper from metadata.

    Parameters
    ----------
    metadata : dict[str, Any]
        Metadata from the page.
    page_url : str
        Final page URL.

    Returns
    -------
    Paper | None
        Paper instance or None if required fields are missing.
    """
    # Title is required to build a Paper.
    title = _pick_metadata_value(metadata, TITLE_META_KEYS)
    if not title:
        return None
    abstract = _pick_metadata_value(metadata, ABSTRACT_META_KEYS)
    doi = _pick_metadata_value(metadata, DOI_META_KEYS)
    authors = _parse_authors(metadata.get("citation_author") or metadata.get("dc.creator"))
    if not authors:
        authors = _parse_authors(metadata.get("author"))
    keywords = _parse_keywords(_pick_metadata_value(metadata, KEYWORDS_META_KEYS))
    publication_date = _parse_date(_pick_metadata_value(metadata, DATE_META_KEYS))

    # Publication is optional; avoid treating preprint servers as publications.
    publication_title = _pick_metadata_value(metadata, PUBLICATION_TITLE_KEYS)
    publication = None
    if publication_title and publication_title.lower() not in {"biorxiv", "medrxiv", "arxiv"}:
        category = None
        if "citation_journal_title" in metadata:
            category = "Journal"
        elif "citation_conference_title" in metadata:
            category = "Conference Proceedings"
        elif "citation_book_title" in metadata:
            category = "Book"
        publication = Publication(
            title=publication_title,
            issn=_pick_metadata_value(metadata, PUBLICATION_ISSN_KEYS),
            isbn=_pick_metadata_value(metadata, PUBLICATION_ISBN_KEYS),
            publisher=_pick_metadata_value(metadata, PUBLICATION_PUBLISHER_KEYS),
            category=category,
        )

    # Track both the landing page and any explicit PDF URL.
    urls = {page_url}
    pdf_url = _pick_metadata_value(metadata, PDF_URL_KEYS)
    if pdf_url:
        urls.add(pdf_url)

    return Paper(
        title=title,
        abstract=abstract or "",
        authors=authors,
        publication=publication,
        publication_date=publication_date,
        urls=urls,
        doi=doi,
        keywords=keywords or None,
    )


def enrich_from_sources(urls: Iterable[str], timeout: float | None) -> Paper | None:
    """Fetch metadata from URLs and build a Paper.

    Parameters
    ----------
    urls : Iterable[str]
        Candidate URLs.
    timeout : float | None
        Timeout for requests.

    Returns
    -------
    Paper | None
        Enriched Paper if metadata found.
    """
    for url in set(urls):
        if "pdf" in url.lower():
            continue
        metadata = fetch_metadata(url, timeout=timeout)
        if not metadata:
            continue
        paper = build_paper_from_metadata(metadata, url)
        if paper is not None:
            return paper
    return None
