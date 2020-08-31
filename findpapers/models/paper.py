from __future__ import annotations
import datetime
from typing import List, Set, Optional
from findpapers.models.publication import Publication


class Paper():
    """
    Class that represents a paper instance
    """

    def __init__(self, title: str, abstract: str, authors: List[str], publication: Publication,
                 publication_date: datetime.date, urls: Set[str], doi: Optional[str] = None, citations: Optional[int] = None,
                 keywords: Optional[Set[str]] = None, comments: Optional[str] = None, number_of_pages: Optional[int] = None,
                 pages: Optional[str] = None, databases: Optional[set] = None, selected: Optional[bool] = None,
                 category: Optional[bool] = None):
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
        publication_date : datetime.date
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
        number_of_pages : int, optional
            Paper number of pages, by default None
        pages : str, optional
            Paper page number or range, by default None
        databases : set, optional
            The databases where the paper was found, by default None
        selected : bool, optional
            If a paper was selected by the user, by default None
        category : srt, optional
            The paper category provided by the user, by default None
        """

        self.title = title
        self.abstract = abstract
        self.authors = authors
        self.publication = publication
        self.publication_date = publication_date
        self.urls = urls
        self.doi = doi
        self.citations = citations
        self.keywords = keywords if keywords is not None else set()
        self.comments = comments
        self.number_of_pages = number_of_pages
        self.pages = pages
        self.databases = databases if databases is not None else set()
        self.selected = selected
        self.category = selected

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

        from findpapers.searcher import AVAILABLE_DATABASES

        if database_name not in AVAILABLE_DATABASES:
            raise ValueError(
                f'Invalid database name "{database_name}". Nowadays only {", ".join(AVAILABLE_DATABASES)} are valid database names')

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

        if self.number_of_pages is None:
            self.number_of_pages = paper.number_of_pages

        if self.pages is None:
            self.pages = paper.pages

        for url in paper.urls:
            self.add_url(url)

        for database in paper.databases:
            self.add_database(database)

        if self.publication is None:
            self.publication = paper.publication

        if self.publication is not None and paper.publication is not None:
            self.publication.enrich(paper.publication)

    @classmethod
    def from_dict(cls, paper_dict: dict) -> Paper:
        """
        A method that returns a Paper instance based on the provided dict object

        Parameters
        ----------
        paper_dict : dict
            A dict that represents a Paper instance

        Returns
        -------
        Paper
            A Paper instance based on the provided dict object
        """

        title = paper_dict.get('title')
        abstract = paper_dict.get('abstract')
        authors = paper_dict.get('authors')
        publication = Publication.from_dict(paper_dict.get('publication')) if paper_dict.get('publication') is not None else None
        publication_date = datetime.datetime.strptime(
            paper_dict.get('publication_date'), '%Y-%m-%d').date()
        urls = set(paper_dict.get('urls'))
        doi = paper_dict.get('doi')
        citations = paper_dict.get('citations')
        keywords = set(paper_dict.get('keywords'))
        comments = paper_dict.get('comments')
        number_of_pages = paper_dict.get('number_of_pages')
        pages = paper_dict.get('pages')
        databases = set(paper_dict.get('databases'))
        selected = paper_dict.get('selected')
        category = paper_dict.get('category')

        return cls(title, abstract, authors, publication, publication_date, urls, doi, citations, keywords,
                   comments, number_of_pages, pages, databases, selected, category)

    @staticmethod
    def to_dict(paper: Paper) -> dict:
        """
        A method that returns a dict object based on the provided Paper instance

        Parameters
        ----------
        paper : Paper
            A Paper instance

        Returns
        -------
        dict
            A dict that represents a Paper instance
        """

        return {
            'title': paper.title,
            'abstract': paper.abstract,
            'authors': paper.authors,
            'publication': Publication.to_dict(paper.publication) if paper.publication is not None else None,
            'publication_date': paper.publication_date.strftime('%Y-%m-%d'),
            'urls': list(paper.urls),
            'doi': paper.doi,
            'citations': paper.citations,
            'keywords': list(paper.keywords),
            'comments': paper.comments,
            'number_of_pages': paper.number_of_pages,
            'pages': paper.pages,
            'databases': list(paper.databases),
            'selected': paper.selected,
            'category': paper.category,
        }
