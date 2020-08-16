from typing import List, Optional
from datetime import date
from findpapers.models.bibliometrics import Bibliometrics


class Publication():
    """
    Class that represents a publication (journal, conference proceeding, book) instance
    """

    def __init__(self, title: str, isbn: Optional[str] = None, issn: Optional[str] = None, publisher: Optional[str] = None,
                 category: Optional[str] = None, bibliometrics_list: Optional[List[Bibliometrics]] = None):
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
        bibliometrics_list : list[Bibliometrics], optional
            publication bibliometrics list, by default None
        """

        self.title = title
        self.isbn = isbn
        self.issn = issn
        self.publisher = publisher
        self.category = category
        self.bibliometrics_list = bibliometrics_list

    @temperature.setter
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

    def add_bibliometrics(self, bibliometrics: Bibliometrics):
        """
        Adding a new unique bibliometrics to the publication, a uniqueness of a bibliometrics is given by its source_name
        If duplication of bibliometrics is provided, the addition will be skipped.

        Parameters
        ----------
        bibliometrics : Bibliometrics
            A bibliometrics instance to be added to the publication bibliometrics list
        """

        # checking if the provided bibliometrics will break the uniqueness constraint given by its source_name
        for a_bibliometrics in self.bibliometrics_list:
            if a_bibliometrics.source_name == bibliometrics.source_name:
                return

        self.bibliometrics_list.append(bibliometrics)

    def enrich(self, publication: Publication):
        """
        e can enrich some publication information using a duplication of it found in another library.
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

        if self.category is None:
            self.category = publication.category

        for bibliometrics in publication.bibliometrics_list:
            self.add_bibliometrics(bibliometrics)
