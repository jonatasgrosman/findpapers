from __future__ import annotations
from typing import List, Optional
import json


class Publication():
    """
    Class that represents a publication (journal, conference proceedings, book) instance
    """

    def __init__(self, title: str, isbn: Optional[str] = None, issn: Optional[str] = None, publisher: Optional[str] = None,
                 category: Optional[str] = None, cite_score: Optional[float] = None, sjr: Optional[float] = None,
                 snip: Optional[float] = None, subject_areas: Optional[set] = None):
        """
        Paper class constructor

        Parameters
        ----------
        title : str
            publication title
        isbn : str, optional
            publication ISBN, by default None
        issn : str, optional
            publication ISSN, by default None
        publisher : str, optional
            publication publisher, by default None
        category : str, optional
            publication category (Journal, Conference Proceedings, Book), by default None
        cite_score : float, optional
            CiteScore measures average citations received per document published in the serial, by default None
        sjr : float, optional
            SCImago Journal Rank measures weighted citations received by the serial. 
            Citation weighting depends on subject field and prestige (SJR) of the citing serial, by default None
        snip : float, optional
            Source Normalized Impact per Paper measures actual citations received relative to citations 
            expected for the serial’s subject field, by default None
        subject_areas : float, optional
            Publication subjects areas, by default None
        Raises
        ------
        ValueError
            - Publication's title cannot be null
        """

        if title is None or len(title) == 0:
            raise(ValueError('Publication\'s title cannot be null'))

        self.title = title
        self.isbn = isbn
        self.issn = issn
        self.publisher = publisher
        self.category = category if category is not None else title # trying to figure out what is the category by publication title
        self.cite_score = cite_score
        self.sjr = sjr
        self.snip = snip
        self.subject_areas = subject_areas if subject_areas is not None else set()

    @property
    def category(self):
        return self._category

    @category.setter
    def category(self, value: str):
        """
        Category value setter, this method also try to convert a provided invalid category 
        to a valid one [Journal, Conference Proceedings, Book]

        Parameters
        ----------
        value : str
            A category string
        """

        if value is not None:

            # trying to convert a provided invalid category to a valid one [Journal, Conference Proceedings, Book]
            if 'journal' in value.lower():
                value = 'Journal'
            elif 'conference' in value.lower() or 'proceeding' in value.lower():
                value = 'Conference Proceedings'
            elif 'book' in value.lower():
                value = 'Book'
            else:
                value = None

        self._category = value

    def enrich(self, publication: Publication):
        """
        e can enrich some publication information using a duplication of it found in another database.
        This method do this using a provided instance of a duplicated publication

        Parameters
        ----------
        publication : Publication
            A duplication of the "self" publication
        """

        if self.title is None or (publication.title is not None and len(self.title) < len(publication.title)):
            self.title = publication.title

        if self.isbn is None:
            self.isbn = publication.isbn

        if self.issn is None:
            self.issn = publication.issn

        if self.publisher is None:
            self.publisher = publication.publisher

        if self.category is None and publication.category is not None:
            self.category = publication.category

        if self.cite_score is None:
            self.cite_score = publication.cite_score

        if self.sjr is None:
            self.sjr = publication.sjr

        if self.snip is None:
            self.snip = publication.snip

        for subject_area in publication.subject_areas:
            self.subject_areas.add(subject_area)

    @classmethod
    def from_dict(cls, publication_dict: dict) -> Publication:
        """
        A method that returns a Publication instance based on the provided dict object

        Parameters
        ----------
        publication_dict : dict
            A dict that represents a Publication instance

        Returns
        -------
        Publication
            A Publication instance based on the provided dict object
        """

        title = publication_dict.get('title')
        isbn = publication_dict.get('isbn')
        issn = publication_dict.get('issn')
        publisher = publication_dict.get('publisher')
        category = publication_dict.get('category')
        cite_score = publication_dict.get('cite_score')
        sjr = publication_dict.get('sjr')
        snip = publication_dict.get('snip')
        subject_areas = set(publication_dict.get('subject_areas'))

        return cls(title, isbn, issn, publisher, category, cite_score, sjr, snip, subject_areas)

    @staticmethod
    def to_dict(publication: Publication) -> dict:
        """
        A method that returns a dict object based on the provided Publication instance

        Parameters
        ----------
        publication : Publication
            A Publication instance

        Returns
        -------
        dict
            A dict that represents a Publication instance
        """

        return {
            'title': publication.title,
            'isbn': publication.isbn,
            'issn': publication.issn,
            'publisher': publication.publisher,
            'category': publication.category,
            'cite_score': publication.cite_score,
            'sjr': publication.sjr,
            'snip': publication.snip,
            'subject_areas': list(publication.subject_areas)
        }
