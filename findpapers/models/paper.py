from __future__ import annotations
from typing import List, Set, Optional
from datetime import date
from findpapers.models.publication import Publication


class Paper():
    """
    Class that represents a paper instance
    """

    def __init__(self, title: str, abstract: str, authors: List[str], publication: Publication,
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
        authors : List[str]
            A list of paper authors
        publication: Publication
            The publication where the paper were published
        publication_date : date
            Paper publication date
        urls : Set[str]
            Paper urls (one from each scientific database)
        doi : str, optional
            Paper DOI, by default None
        citations : int, optional
            Paper citation count given by scientific databases, by default None
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
        self.databases = set()

    def add_database(self, database_name: str):
        """
        Adds database name where the paper was found

        Parameters
        ----------
        database_name : str
            The database name where the paper was found

        Raises
        ------
        ValueError
            - Nowadays only ACM, arXiv, IEEE, PubMed or Scopus are valid database names
        """

        if database_name not in ['ACM', 'arXiv', 'IEEE', 'PubMed', 'Scopus']:
            raise ValueError(
                f'Invalid database name "{database_name}". Nowadays only ACM, arXiv, IEEE, PubMed, or Scopus are valid database names')

        self.databases.add(database_name)

    def add_url(self, url: str):
        """
        Some paper have URL from many database, this method add this kind of reference to a paper

        Parameters
        ----------
        url : str
            A URL that makes a reference to the paper
        """
        self.urls.add(url)

    def enrich(self, paper: Paper):
        """
        We can enrich some paper information using a duplication of it found in another database.
        This method do this using a provided instance of a duplicated paper

        Parameters
        ----------
        paper : Paper
            A duplication of the "self" paper
        """

        if self.publication_date is None:
            self.publication_date = paper.publication_date

        if self.abstract is None or len(self.abstract) < len(paper.abstract):
            self.abstract = paper.abstract
        
        if self.authors is None or len(self.authors) < len(paper.authors):
            self.authors = paper.authors

        if self.doi is None:
            self.doi = paper.doi

        if self.citations is None or self.citations <= paper.citations:
            self.citations = paper.citations
        
        if self.keywords is None or len(self.keywords) < len(paper.keywords):
            self.keywords = paper.keywords

        if self.comments is None:
            self.comments = paper.comments
        
        for url in paper.urls:
            self.add_url(url)
        
        for database in paper.databases:
            self.add_database(database)

        self.publication.enrich(self.publication)
