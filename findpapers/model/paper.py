from typing import List, Optional
from datetime import date


class Paper():
    """
    Class that represents a paper instance
    """

    def __init__(self, title: str, abstract: str, authors: List[str], publication_date: date, urls: List[str],
                 doi: Optional[str] = None, isbn: Optional[str] = None, issn: Optional[str] = None,
                 category: Optional[str] = None, subcategory: Optional[str] = None, citations: Optional[int] = None):
        """
        Paper class constructor

        Parameters
        ----------
        title : str
            paper's title
        abstract : str
            paper's abstract
        authors : List[str]
            a list of paper's authors
        publication_date : date
            paper's publication date
        urls : List[str]
            paper's urls (one from each database)
        doi : Optional[str], optional
            paper's DOI, by default None
        isbn : Optional[str], optional
            paper's ISBN, by default None
        issn : Optional[str], optional
            paper's ISSN, by default None
        category : Optional[str], optional
            paper's category given by the databases, by default None
        subcategory : Optional[str], optional
            paper's subcategory given by the databases, by default None
        citations : Optional[int], optional
            paper's citation count given by the databases, by default None
        """

        self.title = title
        self.abstract = abstract
        self.authors = authors
        self.publication_date = publication_date
        self.urls = urls
        self.doi = doi
        self.isbn = isbn
        self.issn = issn
        self.category = category
        self.subcategory = subcategory
        self.citations = citations
