from __future__ import annotations
from typing import List, Optional
from datetime import date


class Publication():
    """
    Class that represents a publication (journal, conference proceeding, book) instance
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
            publication category (Journal, Conference Proceeding, Book, Other), by default None
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
        """

        self.title = title
        self.isbn = isbn
        self.issn = issn
        self.publisher = publisher
        self.category = category
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
        to a valid one [Journal, Conference Proceeding, Book, Other]

        Parameters
        ----------
        value : str
            A category string
        """

        if value is not None:

            # trying to convert a provided invalid category to a valid one [Journal, Conference Proceeding, Book, Other]
            if 'journal' in value.lower():
                value = 'Journal'
            elif 'conference' in value.lower() or 'proceeding' in value.lower():
                value = 'Conference Proceeding'
            elif 'book' in value.lower():
                value = 'Book'
            else:
                value = 'Other'

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

        if self.isbn is None:
            self.isbn = publication.isbn

        if self.issn is None:
            self.issn = publication.issn

        if self.publisher is None:
            self.publisher = publication.publisher

        if self.category is None or (self.category == 'Other' and publication.category is not None):
            self.category = publication.category

        if self.cite_score is None:
            self.cite_score = publication.cite_score
        
        if self.sjr is None:
            self.sjr = publication.sjr

        if self.snip is None:
            self.snip = publication.snip

        for subject_area in publication.subject_areas:
            self.subject_areas.add(subject_area)
