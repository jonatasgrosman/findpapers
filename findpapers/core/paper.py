"""Paper domain model representing an academic publication."""

from __future__ import annotations

import contextlib
import datetime
import logging
import re
from enum import StrEnum
from typing import Any

from findpapers.exceptions import ModelValidationError

from ..utils.merge import merge_authors, merge_value
from .author import Author
from .source import Source

logger = logging.getLogger(__name__)


class PaperType(StrEnum):
    """BibTeX-aligned classification of a paper.

    Each value corresponds directly to a standard BibTeX entry type,
    enabling accurate bibliography generation.

    Attributes
    ----------
    ARTICLE : str
        Journal article (``@article``).
    INPROCEEDINGS : str
        Paper published in conference proceedings (``@inproceedings``).
    INBOOK : str
        Chapter or section in a book (``@inbook``).
    INCOLLECTION : str
        A self-contained part of a book with its own title (``@incollection``).
    BOOK : str
        A complete book (``@book``).
    PHDTHESIS : str
        PhD thesis or doctoral dissertation (``@phdthesis``).
    MASTERSTHESIS : str
        Master's thesis (``@mastersthesis``).
    TECHREPORT : str
        Technical report issued by an institution (``@techreport``).
    UNPUBLISHED : str
        Work not formally published, such as preprints (``@unpublished``).
    MISC : str
        Anything that does not fit the other categories (``@misc``).
    """

    ARTICLE = "article"
    INPROCEEDINGS = "inproceedings"
    INBOOK = "inbook"
    INCOLLECTION = "incollection"
    BOOK = "book"
    PHDTHESIS = "phdthesis"
    MASTERSTHESIS = "mastersthesis"
    TECHREPORT = "techreport"
    UNPUBLISHED = "unpublished"
    MISC = "misc"


class Database(StrEnum):
    """Supported academic database identifiers.

    As a :class:`StrEnum`, each member compares equal to its string value,
    so code such as ``database == "arxiv"`` works without modification.

    ``"web_scraping"`` is intentionally absent: web scraping is a retrieval
    mechanism, not an academic database, and must never be added to a
    :attr:`Paper.databases` set.
    """

    ARXIV = "arxiv"
    """arXiv preprint server."""

    CROSSREF = "crossref"
    """CrossRef DOI registration authority."""

    IEEE = "ieee"
    """IEEE Xplore digital library."""

    OPENALEX = "openalex"
    """OpenAlex open scholarly graph."""

    PUBMED = "pubmed"
    """PubMed biomedical literature database."""

    SCOPUS = "scopus"
    """Elsevier Scopus abstract and citation database."""

    SEMANTIC_SCHOLAR = "semantic_scholar"
    """Semantic Scholar AI-powered research database."""

    WOS = "wos"
    """Web of Science (Clarivate) bibliographic database."""


# Maximum number of days into the future that a publication date is considered
# plausible.  Dates beyond this threshold are treated as data-quality errors
# from upstream APIs and silently replaced with ``None``.
_MAX_FUTURE_DAYS: int = 365


class Paper:
    """Represents a paper instance."""

    def __init__(
        self,
        title: str,
        abstract: str,
        authors: list[Author],
        source: Source | None,
        publication_date: datetime.date | None,
        url: str | None = None,
        pdf_url: str | None = None,
        doi: str | None = None,
        citations: int | None = None,
        keywords: set[str] | None = None,
        comments: str | None = None,
        page_count: int | None = None,
        page_range: str | None = None,
        databases: set[str] | None = None,
        paper_type: PaperType | None = None,
        fields_of_study: set[str] | None = None,
        subjects: set[str] | None = None,
        language: str | None = None,
        is_open_access: bool | None = None,
        is_retracted: bool | None = None,
        funders: set[str] | None = None,
    ) -> None:
        """Create a Paper instance.

        Parameters
        ----------
        title : str
            Paper title.
        abstract : str
            Paper abstract.
        authors : list[Author]
            List of authors.
        source : Source | None
            Source where it was published.
        publication_date : datetime.date | None
            Publication date.
        url : str | None
            URL that references the paper.
        pdf_url : str | None
            Direct URL to PDF file.
        doi : str | None
            Paper DOI.
        citations : int | None
            Citations count.
        keywords : set[str] | None
            Keywords.
        comments : str | None
            Comments.
        page_count : int | None
            Page count.
        page_range : str | None
            Page range (e.g. ``"223-230"``).
        databases : set[str] | None
            Databases where found.
        paper_type : PaperType | None
            BibTeX-aligned paper type (informational, not used for filtering).
        fields_of_study : set[str] | None
            Broad knowledge areas (e.g. "Computer Science", "Mathematics").
        subjects : set[str] | None
            More specific disciplinary classifications
            (e.g. "Artificial Intelligence", "Optimization and Control").
        language : str | None
            ISO 639-1 2-letter language code (e.g. ``"en"``, ``"pt"``).
        is_open_access : bool | None
            ``True`` when the paper is freely available online, ``False``
            when it is known to be behind a paywall, ``None`` when unknown.
        is_retracted : bool | None
            ``True`` when the paper was retracted, ``False`` when it is
            known not to be retracted, ``None`` when unknown.
        funders : set[str] | None
            Names of funding agencies or organisations that supported this
            work (e.g. ``{"National Science Foundation", "NIH"}``).  When no
            funding information is available, defaults to an empty set.

        Raises
        ------
        ModelValidationError
            If title is missing.
        """
        if not title:
            raise ModelValidationError("Paper's title cannot be null")

        self.title = self._normalize_title(title)
        self.abstract = abstract
        self.authors: list[Author] = list(authors or [])
        self.source = source
        self.publication_date = self._sanitize_date(publication_date)
        self.url = url
        self.pdf_url = pdf_url
        self.doi = doi
        self.citations = citations
        self.keywords = keywords if keywords is not None else set()
        self.comments = comments
        self.page_count = (
            page_count if page_count is not None else self._infer_page_count(page_range)
        )
        self.page_range = page_range
        self.databases = databases if databases is not None else set()
        self.paper_type = paper_type
        self.fields_of_study = fields_of_study if fields_of_study is not None else set()
        self.subjects = subjects if subjects is not None else set()
        self.language = language
        self.is_open_access = is_open_access
        self.is_retracted = is_retracted
        self.funders = funders if funders is not None else set()

    def __eq__(self, other: object) -> bool:
        """Check equality by DOI (case-insensitive) or title.

        Two papers are equal if they share the same DOI (case-insensitive)
        or, when neither has a DOI, the same lowercased title.

        Parameters
        ----------
        other : object
            Object to compare against.

        Returns
        -------
        bool
            ``True`` if both are :class:`Paper` with matching identity.
        """
        if not isinstance(other, Paper):
            return NotImplemented
        self_key = self._identity_key()
        other_key = other._identity_key()
        if self_key is None or other_key is None:
            return self is other
        return self_key == other_key

    def __hash__(self) -> int:
        """Return a hash based on DOI or lowercased title.

        Returns
        -------
        int
            Hash value.
        """
        key = self._identity_key()
        if key is None:
            return id(self)
        return hash(key)

    def __repr__(self) -> str:
        """Return a developer-friendly representation.

        Returns
        -------
        str
            Representation string.
        """
        return f"Paper(title={self.title!r}, doi={self.doi!r})"

    def __str__(self) -> str:
        """Return a human-readable citation-like string.

        Format: ``"Author et al. (Year). Title."``
        Falls back gracefully when author or date is missing.

        Returns
        -------
        str
            Friendly citation string.
        """
        parts: list[str] = []
        if self.authors:
            first = self.authors[0].name
            if len(self.authors) > 1:
                parts.append(f"{first} et al.")
            else:
                parts.append(first)
        if self.publication_date is not None:
            parts.append(f"({self.publication_date.year})")
        # Always include the title, terminated with a period
        title = self.title.rstrip(".")
        parts.append(f"{title}.")
        return " ".join(parts)

    def _identity_key(self) -> str | None:
        """Return a unique identity key for this paper, or ``None``.

        Prefers DOI (lowercased); falls back to lowercased title.

        Returns
        -------
        str | None
            A canonical string key, or ``None`` if no identifier available.
        """
        if self.doi:
            return self.doi.strip().lower()
        if self.title:
            return self.title.strip().lower()
        return None

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Strip HTML tags and normalize whitespace in a paper title.

        Removes any HTML markup (e.g. ``<i>...</i>`` injected by publisher
        APIs) and collapses consecutive whitespace characters (including
        newlines and tabs) into a single space.

        Parameters
        ----------
        title : str
            Raw title string, possibly containing HTML tags or newlines.

        Returns
        -------
        str
            Clean title with HTML removed and whitespace normalized.
        """
        # Remove HTML tags (e.g. <i>, <sub>, <sup>, etc.)
        stripped = re.sub(r"<[^>]+>", "", title)
        # Collapse all whitespace (newlines, tabs, multiple spaces) to a single space
        return " ".join(stripped.split())

    @staticmethod
    def _sanitize_date(
        value: datetime.date | None,
    ) -> datetime.date | None:
        """Return *value* unchanged when plausible, otherwise ``None``.

        Dates more than :data:`_MAX_FUTURE_DAYS` in the future are considered
        data-quality errors from upstream APIs (e.g. OpenAlex placeholder
        dates like 2050-01-01) and are replaced with ``None``.

        Parameters
        ----------
        value : datetime.date | None
            The publication date to validate.

        Returns
        -------
        datetime.date | None
            The original date if plausible, otherwise ``None``.
        """
        if value is None:
            return None
        max_allowed = datetime.date.today() + datetime.timedelta(days=_MAX_FUTURE_DAYS)
        if value > max_allowed:
            logger.debug(
                "Discarding implausible future publication date %s (more than %d days from today).",
                value.isoformat(),
                _MAX_FUTURE_DAYS,
            )
            return None
        return value

    @staticmethod
    def _infer_page_count(page_range: str | None) -> int | None:
        """Try to compute a page count from a hyphen-separated page range.

        If *page_range* matches the pattern ``"<start>-<end>"`` where both
        parts are non-negative integers and ``end >= start``, the page count
        is ``end - start + 1``.  Otherwise ``None`` is returned.

        Parameters
        ----------
        page_range : str | None
            Page range string (e.g. ``"223-230"``).

        Returns
        -------
        int | None
            The computed page count, or ``None`` when *page_range* cannot
            be parsed.
        """
        if not page_range:
            return None

        parts = page_range.split("-")
        if len(parts) != 2:
            return None

        try:
            start = int(parts[0].strip())
            end = int(parts[1].strip())
        except ValueError:
            return None

        if end < start or start < 0:
            return None

        return end - start + 1

    def add_database(self, database_name: str) -> None:
        """Add a database name where the paper was found.

        Parameters
        ----------
        database_name : str
            Database name.

        Returns
        -------
        None
        """
        if database_name:
            self.databases.add(database_name)

    def merge(self, paper: Paper) -> None:
        """Merge another paper into this one.

        Parameters
        ----------
        paper : Paper
            Another instance of the same paper.

        Returns
        -------
        None
        """
        # Prefer existing dates; if missing, use the incoming one.
        if self.publication_date is None:
            self.publication_date = paper.publication_date

        # Merge scalar fields using shared rules.
        self.title = merge_value(self.title, paper.title)
        # DOI is never overwritten: the first source wins.
        self.doi = self.doi or paper.doi
        self.abstract = merge_value(self.abstract, paper.abstract)
        self.citations = merge_value(self.citations, paper.citations)
        self.comments = merge_value(self.comments, paper.comments)
        self.page_count = merge_value(self.page_count, paper.page_count)
        self.page_range = merge_value(self.page_range, paper.page_range)

        # If page_count is still unknown, try to infer it from page_range.
        if self.page_count is None:
            self.page_count = self._infer_page_count(self.page_range)

        self.url = merge_value(self.url, paper.url)
        self.pdf_url = merge_value(self.pdf_url, paper.pdf_url)

        # Merge authors/keywords as collections while keeping uniqueness.
        # Authors use a token-aware merge to avoid duplicating the same person
        # when different sources represent the name as "First Last" vs "Last, First".
        self.authors = merge_authors(self.authors or [], paper.authors or [])
        self.keywords = merge_value(self.keywords, paper.keywords)
        self.fields_of_study |= paper.fields_of_study
        self.subjects |= paper.subjects
        self.language = merge_value(self.language, paper.language)
        self.is_open_access = merge_value(self.is_open_access, paper.is_open_access)
        self.is_retracted = merge_value(self.is_retracted, paper.is_retracted)
        self.funders |= paper.funders

        # Always accumulate databases for traceability.
        self.databases |= paper.databases
        if self.source is None:
            self.source = paper.source
        elif paper.source is not None:
            self.source.merge(paper.source)

        self.paper_type = merge_value(self.paper_type, paper.paper_type)

    @staticmethod
    def _from_dict_parse_authors(paper_dict: dict) -> list[Author]:
        """Parse the ``authors`` field from a paper dictionary.

        Parameters
        ----------
        paper_dict : dict
            Raw paper dictionary.

        Returns
        -------
        list[Author]
            Parsed author list.
        """
        raw = paper_dict.get("authors") or []
        if isinstance(raw, (list, set, tuple)):
            return [Author.from_dict(a) for a in raw]
        return [Author.from_dict(raw)]

    @staticmethod
    def _from_dict_parse_date(paper_dict: dict) -> datetime.date | None:
        """Parse the ``publication_date`` field from a paper dictionary.

        Parameters
        ----------
        paper_dict : dict
            Raw paper dictionary.

        Returns
        -------
        datetime.date | None
            Parsed date or ``None``.
        """
        raw = paper_dict.get("publication_date")
        if isinstance(raw, str):
            try:
                return datetime.date.fromisoformat(raw)
            except ValueError:
                return None
        return None

    @staticmethod
    def _from_dict_str_set(paper_dict: dict, key: str) -> set[str]:
        """Parse a string-collection field into a ``set[str]``.

        Handles the case where the raw value is a list/set/tuple, a single
        non-collection value, or missing altogether.

        Parameters
        ----------
        paper_dict : dict
            Raw paper dictionary.
        key : str
            Field name to extract.

        Returns
        -------
        set[str]
            Extracted string set (may be empty).
        """
        raw = paper_dict.get(key) or []
        if isinstance(raw, (list, set, tuple)):
            return {str(item) for item in raw}
        return {str(raw)} if raw else set()

    @staticmethod
    def _from_dict_optional_str(val: Any) -> str | None:
        """Coerce a value to ``str`` or ``None`` when it is already a string.

        Parameters
        ----------
        val : Any
            Raw value to coerce.

        Returns
        -------
        str | None
            String representation or ``None``.
        """
        if val is None:
            return None
        return val if isinstance(val, str) else str(val)

    @staticmethod
    def _from_dict_optional_bool(raw: Any) -> bool | None:
        """Coerce a value to ``bool | None``.

        Parameters
        ----------
        raw : Any
            Raw value.

        Returns
        -------
        bool | None
            ``True``/``False`` or ``None`` when the raw value is ``None``.
        """
        if isinstance(raw, bool):
            return raw
        if raw is not None:
            return bool(raw)
        return None

    @staticmethod
    def _from_dict_paper_type(paper_dict: dict) -> PaperType | None:
        """Parse the ``paper_type`` field from a paper dictionary.

        Parameters
        ----------
        paper_dict : dict
            Raw paper dictionary.

        Returns
        -------
        PaperType | None
            Parsed paper type or ``None``.
        """
        raw = paper_dict.get("paper_type")
        if isinstance(raw, str):
            with contextlib.suppress(ValueError):
                return PaperType(raw)
        return None

    @classmethod
    def from_dict(cls, paper_dict: dict) -> Paper:
        """Create a paper from a dict.

        Parameters
        ----------
        paper_dict : dict
            Paper dictionary.

        Returns
        -------
        Paper
            Paper instance.

        Raises
        ------
        ModelValidationError
            If the title is missing.
        """
        title = paper_dict.get("title")
        if not isinstance(title, str) or not title:
            raise ModelValidationError("Paper's title cannot be null")

        abstract = paper_dict.get("abstract") or ""
        if not isinstance(abstract, str):
            abstract = str(abstract)

        authors = cls._from_dict_parse_authors(paper_dict)

        source_data = paper_dict.get("source")
        source = Source.from_dict(source_data) if isinstance(source_data, dict) else None

        publication_date = cls._from_dict_parse_date(paper_dict)
        url = cls._from_dict_optional_str(paper_dict.get("url"))
        pdf_url = cls._from_dict_optional_str(paper_dict.get("pdf_url"))
        doi = cls._from_dict_optional_str(paper_dict.get("doi"))
        language = cls._from_dict_optional_str(paper_dict.get("language"))

        citations = paper_dict.get("citations")
        comments = paper_dict.get("comments")
        page_count = paper_dict.get("page_count")
        page_range = paper_dict.get("page_range")

        keywords = cls._from_dict_str_set(paper_dict, "keywords")
        databases = cls._from_dict_str_set(paper_dict, "databases")
        fields_of_study = cls._from_dict_str_set(paper_dict, "fields_of_study")
        subjects = cls._from_dict_str_set(paper_dict, "subjects")
        funders = cls._from_dict_str_set(paper_dict, "funders")

        paper_type = cls._from_dict_paper_type(paper_dict)
        is_open_access = cls._from_dict_optional_bool(paper_dict.get("is_open_access"))
        is_retracted = cls._from_dict_optional_bool(paper_dict.get("is_retracted"))

        return cls(
            title=title,
            abstract=abstract,
            authors=authors,
            source=source,
            publication_date=publication_date,
            url=url,
            pdf_url=pdf_url,
            doi=doi,
            citations=citations,
            keywords=keywords,
            comments=comments,
            page_count=page_count,
            page_range=page_range,
            databases=databases,
            paper_type=paper_type,
            fields_of_study=fields_of_study,
            subjects=subjects,
            language=language,
            is_open_access=is_open_access,
            is_retracted=is_retracted,
            funders=funders,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this Paper to a plain dictionary.

        Returns
        -------
        dict[str, Any]
            Paper data suitable for JSON serialization.
        """
        return {
            "title": self.title,
            "abstract": self.abstract,
            "authors": [author.to_dict() for author in self.authors],
            "source": (self.source.to_dict() if self.source is not None else None),
            "publication_date": (
                self.publication_date.isoformat() if self.publication_date is not None else None
            ),
            "url": self.url,
            "pdf_url": self.pdf_url,
            "doi": self.doi,
            "citations": self.citations,
            "keywords": sorted(self.keywords),
            "comments": self.comments,
            "page_count": self.page_count,
            "page_range": self.page_range,
            "databases": sorted(self.databases),
            "paper_type": self.paper_type.value if self.paper_type else None,
            "fields_of_study": sorted(self.fields_of_study),
            "subjects": sorted(self.subjects),
            "language": self.language,
            "is_open_access": self.is_open_access,
            "is_retracted": self.is_retracted,
            "funders": sorted(self.funders),
        }
