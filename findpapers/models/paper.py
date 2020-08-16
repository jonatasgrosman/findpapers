from typing import List, Set, Optional
from datetime import date
from findpapers.models.publication import Publication


class Paper():
    """
    Class that represents a paper instance
    """

    def __init__(self, title: str, abstract: str, authors: Set[str], publication: Publication,
                 publication_date: date, urls: Set[str], doi: Optional[str] = None, citations: Optional[int] = None,
                 keywords: Optional[Set[str]] = None, comments: Optional[str] = None):
        """
        Paper class constructor

        Parameters
        ----------
        title : str
            Paper title
        abstract : str
            Paper abstract
        authors : Set[str]
            A list of paper authors
        publication: Publication
            The publication where the paper were published
        publication_date : date
            Paper publication date
        urls : Set[str]
            Paper urls (one from each scientific library)
        doi : str, optional
            Paper DOI, by default None
        citations : int, optional
            Paper citation count given by scientific libraries, by default None
        keywords : Set[str], optional
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
        self.libraries = set()

    def add_library(self, library_name: str):
        """
        Adds library name where the paper was found

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

        self.libraries.add(library_name)

    def add_url(self, url: str):
        """
        Some paper have URL from many database, this method add this kind of reference to a paper

        Parameters
        ----------
        url : str
            A URL that makes a reference to the paper
        """
        self.urls.add(url)
