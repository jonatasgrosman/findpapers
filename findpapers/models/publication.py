from __future__ import annotations

from typing import Optional, Set

from ..utils.merge_util import merge_value


class Publication:
    """Represents a publication (journal, conference proceedings, or book)."""

    def __init__(
        self,
        title: str,
        isbn: Optional[str] = None,
        issn: Optional[str] = None,
        publisher: Optional[str] = None,
        category: Optional[str] = None,
        cite_score: Optional[float] = None,
        sjr: Optional[float] = None,
        snip: Optional[float] = None,
        subject_areas: Optional[Set[str]] = None,
        is_potentially_predatory: Optional[bool] = False,
    ) -> None:
        """Create a Publication instance.

        Parameters
        ----------
        title : str
            Publication title.
        isbn : str | None
            Publication ISBN.
        issn : str | None
            Publication ISSN.
        publisher : str | None
            Publication publisher name.
        category : str | None
            Publication category (Journal, Conference Proceedings, Book).
        cite_score : float | None
            CiteScore metric.
        sjr : float | None
            SJR metric.
        snip : float | None
            SNIP metric.
        subject_areas : set[str] | None
            Subject areas.
        is_potentially_predatory : bool | None
            Predatory flag.

        Raises
        ------
        ValueError
            If title is empty.
        """
        if title is None or len(title) == 0:
            raise ValueError("Publication's title cannot be null")

        self.title = title
        self.isbn = isbn
        self.issn = issn
        self.publisher = publisher
        self.category = category if category is not None else title
        self.cite_score = cite_score
        self.sjr = sjr
        self.snip = snip
        self.subject_areas = subject_areas if subject_areas is not None else set()
        self.is_potentially_predatory = is_potentially_predatory

    @property
    def category(self) -> Optional[str]:
        """Return the publication category.

        Returns
        -------
        str | None
            Category name or None.
        """
        return self._category

    @category.setter
    def category(self, value: Optional[str]) -> None:
        """Normalize and set the publication category.

        Parameters
        ----------
        value : str | None
            Category name.
        """
        if value is not None:
            lowered = value.lower()
            if "journal" in lowered:
                value = "Journal"
            elif "conference" in lowered or "proceeding" in lowered:
                value = "Conference Proceedings"
            elif "book" in lowered:
                value = "Book"
            else:
                value = None

        self._category = value

    def merge(self, publication: Publication) -> None:
        """Merge another publication into this one.

        Parameters
        ----------
        publication : Publication
            Publication to merge into this one.

        Returns
        -------
        None
        """
        # Merge scalar and collection fields using shared rules.
        self.title = merge_value(self.title, publication.title)
        self.isbn = merge_value(self.isbn, publication.isbn)
        self.issn = merge_value(self.issn, publication.issn)
        self.publisher = merge_value(self.publisher, publication.publisher)
        self.category = merge_value(self.category, publication.category)
        self.cite_score = merge_value(self.cite_score, publication.cite_score)
        self.sjr = merge_value(self.sjr, publication.sjr)
        self.snip = merge_value(self.snip, publication.snip)
        self.subject_areas = merge_value(self.subject_areas, publication.subject_areas)
        self.is_potentially_predatory = bool(
            self.is_potentially_predatory or publication.is_potentially_predatory
        )

    @classmethod
    def from_dict(cls, publication_dict: dict) -> Publication:
        """Create a Publication from a dict.

        Parameters
        ----------
        publication_dict : dict
            Publication dictionary.

        Returns
        -------
        Publication
            Publication instance.

        Raises
        ------
        ValueError
            If the title is missing.
        """
        title = publication_dict.get("title")
        if not isinstance(title, str) or not title:
            raise ValueError("Publication's title cannot be null")
        return cls(
            title=title,
            isbn=publication_dict.get("isbn"),
            issn=publication_dict.get("issn"),
            publisher=publication_dict.get("publisher"),
            category=publication_dict.get("category"),
            cite_score=publication_dict.get("cite_score"),
            sjr=publication_dict.get("sjr"),
            snip=publication_dict.get("snip"),
            subject_areas=set(publication_dict.get("subject_areas") or []),
            is_potentially_predatory=publication_dict.get("is_potentially_predatory"),
        )

    @staticmethod
    def to_dict(publication: Publication) -> dict:
        """Convert a Publication to dict.

        Parameters
        ----------
        publication : Publication
            Publication instance.

        Returns
        -------
        dict
            Publication dictionary.
        """
        return {
            "title": publication.title,
            "isbn": publication.isbn,
            "issn": publication.issn,
            "publisher": publication.publisher,
            "category": publication.category,
            "cite_score": publication.cite_score,
            "sjr": publication.sjr,
            "snip": publication.snip,
            "subject_areas": sorted(publication.subject_areas),
            "is_potentially_predatory": publication.is_potentially_predatory,
        }
