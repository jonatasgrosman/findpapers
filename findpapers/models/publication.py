from typing import List, Optional
from datetime import date
from findpapers.models.bibliometrics import Bibliometrics


class Publication():
    """
    Class that represents a publication (journal, conference proceedings, book) instance
    """

    def __init__(self, title: str, isbn: Optional[str] = None, issn: Optional[str] = None, publisher: Optional[str] = None,
                 category: Optional[str] = None, bibliometrics: Optional[List[Bibliometrics]] = None):
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
            publication category (journal, conference proceedings, book), by default None
        bibliometrics : list[Bibliometrics], optional
            publication bibliometrics given by, by default None
        """

        self.title = title
        self.isbn = isbn
        self.issn = issn
        self.publisher = publisher
        self.category = category
        self.bibliometrics = bibliometrics
