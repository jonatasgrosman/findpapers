from typing import List, Optional
from datetime import date
from findpapers.models.publication import Publication


class Paper():
    """
    Class that represents a paper instance
    """

    def __init__(self, title: str, abstract: str, authors: List[str], publication: Publication,
                 publication_date: date, urls: List[str], doi: Optional[str] = None, citations: Optional[int] = None,
                 keywords: Optional[List[str]] = None, comments: Optional[str] = None):
        """
        Paper class constructor

        Parameters
        ----------
        title : str
            Paper title
        abstract : str
            Paper abstract
        authors : List[str]
            A list of paper authors
        publication: Publication
            The publication where the paper were published
        publication_date : date
            Paper publication date
        urls : List[str]
            Paper urls (one from each scientific library)
        doi : str, optional
            Paper DOI, by default None
        citations : int, optional
            Paper citation count given by scientific libraries, by default None
        keywords : List[str], optional
            Paper keywords, by default None
        comments : str, optional
            Paper comments, by default None
        """

        self.title = title
        self.abstract = abstract
        self.authors = authors
        self.publication = publication
        self.publication_date = publication_date
        self.urls = urls
        self.doi = doi
        self.citations = citations
        self.keywords = keywords
        self.comments = comments
        self.libraries = []

    def add_library(self, library_name: str):
        """Adds library name where the paper was found

        Parameters
        ----------
        library_name : str
            The library name where the paper was found

        Raises
        ------
        ValueError
            - Nowadays only ACM, arXiv or Scopus are valid library names
        """

        if library_name not in ['ACM', 'arXiv', 'Scopus']:
            raise ValueError(
                f'Invalid library name "{library_name}". Nowadays only ACM, arXiv or Scopus are valid library names')

        self.catalogues.append(library_name)
