from __future__ import annotations
import datetime
import itertools
import edlib
from typing import List, Optional
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication


class Search():
    """
    Class that represents a search
    """

    def __init__(self, query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
                 limit: Optional[int] = None, limit_per_database: Optional[int] = None, processed_at: Optional[datetime.datetime] = None,
                 papers: Optional[set] = None):
        """
        Class constructor

        Parameters
        ----------
        query : str
            The query used to fetch the papers
        since : datetime.date, optional
            The lower bound (inclusive) date of search, by default None
        until : datetime.date, optional
            The upper bound (inclusive) date of search, by default None
        limit : int, optional
            The max number of papers that can be returned in the search, 
            when the limit is not provided the search will retrieve all the papers that it can, by default None
        limit_per_database : int, optional
            The max number of papers that can be returned in the search for each database
            when the limit is not provided the search will retrieve all the papers that it can, by default None
        processed_at : datetime.datetime, optional
            The datetime when the search was performed
        papers : set, optional
            A list of papers already collected
        """

        self.query = query
        self.since = since
        self.until = until
        self.limit = limit
        self.limit_per_database = limit_per_database
        self.processed_at = processed_at if processed_at is not None else datetime.datetime.utcnow()
        self.papers = set()

        self.paper_by_key = {}
        self.publication_by_key = {}
        self.paper_by_doi = {}
        self.papers_by_database = {}

        if papers is not None:
            for paper in papers:
                self.add_paper(paper)

    def get_paper_key(self, paper_title: str, publication_date: datetime.date, paper_doi: Optional[str] = None) -> str:
        """
        We have a map called paper_by_key that is filled using the string this method returns

        Parameters
        ----------
        paper_title : str
            The paper title
        publication_date : datetime.date
            The paper publication date
        paper_doi : str, optional
            The paper DOI, by default None

        Returns
        -------
        str
            A string that represents a unique key for each paper, that will be used to fill and retrieve values from paper_by_key
        """

        if paper_doi is not None:
            return f'DOI-{paper_doi}'
        else:
            return f'{paper_title.lower()}|{publication_date.year if publication_date is not None else ""}'

    def get_publication_key(self, publication_title: str, publication_issn: Optional[str] = None, publication_isbn: Optional[str] = None) -> str:
        """
        We have a map called publication_by_key that is filled using the string this method returns

        Parameters
        ----------
        publication_title : str
            The publication title
        publication_issn : Optional[str], optional
            The publication issn, by default None
        publication_isbn : Optional[str], optional
            The publication isbn, by default None

        Returns
        -------
        str
            A string that represents a unique key for each publication, that will be used to fill and retrieve values from publication_by_key
        """

        if publication_isbn is not None:
            return f'ISBN-{publication_isbn.lower()}'
        elif publication_issn is not None:
            return f'ISSN-{publication_issn.lower()}'
        else:
            return f'TITLE-{publication_title.lower()}'

    def add_paper(self, paper: Paper):
        """
        Method that handle the action to add a paper to the list of already collected papers, 
        dealing with possible paper's duplications

        Parameters
        ----------
        paper : Paper
            A new collected paper instance
        Raises
        ------
        ValueError
            - Paper cannot be added to search without at least one defined database
        OverflowError
            - When the papers limit is provided, you cannot exceed it
        """

        if len(paper.databases) == 0:
            raise ValueError(
                'Paper cannot be added to search without at least one defined database')

        for database in paper.databases:
            if self.reached_its_limit(database):
                raise OverflowError(
                    'When the papers limit is provided, you cannot exceed it')

        if paper.publication is not None:

            publication_key = self.get_publication_key(
                paper.publication.title, paper.publication.issn, paper.publication.isbn)
            already_collected_publication = self.publication_by_key.get(
                publication_key, None)

            if already_collected_publication is not None:
                already_collected_publication.enrich(paper.publication)
                paper.publication = already_collected_publication
            else:
                self.publication_by_key[publication_key] = paper.publication

        paper_key = self.get_paper_key(
            paper.title, paper.publication_date, paper.doi)

        already_collected_paper = self.paper_by_key.get(paper_key, None)

        if (self.since is None or paper.publication_date >= self.since) \
                and (self.until is None or paper.publication_date <= self.until):

            if already_collected_paper is None:
                self.papers.add(paper)
                self.paper_by_key[paper_key] = paper

                if paper.doi is not None:
                    self.paper_by_doi[paper.doi] = paper

                for database in paper.databases:
                    if database not in self.papers_by_database:
                        self.papers_by_database[database] = set()
                    self.papers_by_database[database].add(paper)

            else:
                self.papers_by_database[database].add(already_collected_paper)
                already_collected_paper.enrich(paper)

    def get_paper(self, paper_title: str, publication_date: str, paper_doi: Optional[str] = None) -> Paper:
        """
        Get a collected paper by paper's title and publication date

        Parameters
        ----------
        paper_title : str
            The paper title
        publication_date : datetime.date
            The paper publication date
        paper_doi : str, optional
            The paper DOI, by default None

        Returns
        -------
        Paper
            The wanted paper, or None if there isn't a paper given by the provided arguments
        """

        paper_key = self.get_paper_key(
            paper_title, publication_date, paper_doi)

        return self.paper_by_key.get(paper_key, None)

    def get_publication(self, title: str, issn: Optional[str] = None, isbn: Optional[str] = None) -> Publication:
        """
        Get a collected publication by publication's title, issn and isbn

        Parameters
        ----------
        title : str
            The publication title
        issn : Optional[str]
            The publication ISSN, by default None
        isbn : Optional[str]
            The publication ISBN, by default None

        Returns
        -------
        Publication
            The wanted publication, or None if there isn't a publication given by the provided arguments
        """

        publication_key = self.get_publication_key(title, issn, isbn)

        return self.publication_by_key.get(publication_key, None)

    def remove_paper(self, paper: Paper):
        """
        Remove a collected paper

        Parameters
        ----------
        paper : Paper
            A paper instance
        """

        paper_key = self.get_paper_key(
            paper.title, paper.publication_date, paper.doi)

        if paper_key in self.paper_by_key:
            del self.paper_by_key[paper_key]

        for database in paper.databases:
            self.papers_by_database[database].remove(paper)

        self.papers.remove(paper)

    def merge_duplications(self, similarity_threshold: float = 0.95):
        """
        In some cases, a same paper is represented with tiny differences between some databases, 
        this method try to deal with this situation merging those instances of the paper,
        using a similarity threshold, by default 0.95 (95%), i.e., if two papers titles
        are similar by 95% or more, and if the papers have the same year of publication
        this papers are considered duplications of a same paper.

        Parameters
        ----------
        max_similarity_threshold : float, optional
            A value between 0 and 1 that represents a threshold that says if a pair of papers is a duplication or not, by default 0.95 (95%)
        """

        paper_key_pairs = list(
            itertools.combinations(self.paper_by_key.keys(), 2))

        for i, pair in enumerate(paper_key_pairs):

            paper_1_key = pair[0]
            paper_2_key = pair[1]
            paper_1 = self.paper_by_key.get(paper_1_key)
            paper_2 = self.paper_by_key.get(paper_2_key)

            if (paper_1.publication_date is None or paper_2.publication_date is None) or \
                (paper_1.publication_date.year != paper_2.publication_date.year): 
                # We cannot merge paper from different years or without a year defined
                break

            max_title_length = max(len(paper_1.title), len(paper_2.title))

            # creating the max valid edit distance using the max title length between the two papers and the provided similarity threshold
            max_edit_distance = int(
                max_title_length * (1 - similarity_threshold))

            # calculating the edit distance between the titles
            titles_edit_distance = edlib.align(
                paper_1.title, paper_2.title)['editDistance']

            if (paper_1.doi is not None and paper_1.doi == paper_2.doi) or (titles_edit_distance <= max_edit_distance):

                # using the information of paper_2 to enrich paper_1
                paper_1.enrich(paper_2)

                # removing the paper_2 instance
                self.remove_paper(paper_2)

    def reached_its_limit(self, database: str) -> bool:
        """
        Returns a flag that says if the search has reached its limit

        Parameters
        ----------
        database : str, optional
            The database name that will be used to check the limit

        Returns
        -------
        bool
            a flag that says if the search has reached its limit
        """

        reached_general_limit = self.limit is not None and len(
            self.papers) >= self.limit
        reached_database_limit = self.limit_per_database is not None and database in self.papers_by_database and len(
            self.papers_by_database.get(database)) >= self.limit_per_database

        return reached_general_limit or reached_database_limit

    @classmethod
    def from_dict(cls, search_dict: dict) -> Search:
        """
        A method that returns a Search instance based on the provided dict object

        Parameters
        ----------
        search_dict : dict
            A dict that represents a Search instance

        Returns
        -------
        Search
            A Search instance based on the provided dict object
        """

        query = search_dict.get('query')
        limit = search_dict.get('limit')
        limit_per_database = search_dict.get('limit_per_database')

        since = search_dict.get('since')
        if since is not None:
            since = datetime.datetime.strptime(since, '%Y-%m-%d').date()

        until = search_dict.get('until')
        if until is not None:
            until = datetime.datetime.strptime(until, '%Y-%m-%d').date()

        processed_at = search_dict.get('processed_at')
        if processed_at is not None:
            processed_at = datetime.datetime.strptime(processed_at, '%Y-%m-%d %H:%M:%S')

        papers = set()
        for paper in search_dict.get('papers', []):
            papers.add(Paper.from_dict(paper))

        return cls(query, since, until, limit, limit_per_database, processed_at, papers)

    @staticmethod
    def to_dict(search: Search) -> dict:
        """
        A method that returns a dict object based on the provided Search instance

        Parameters
        ----------
        search : Search
            A Search instance

        Returns
        -------
        dict
            A dict that represents a Search instance
        """

        papers = []
        for paper in search.papers:
            papers.append(Paper.to_dict(paper))

        return {
            'query': search.query,
            'since': search.since.strftime('%Y-%m-%d') if search.since is not None else None,
            'until': search.until.strftime('%Y-%m-%d') if search.until is not None else None,
            'limit': search.limit,
            'limit_per_database': search.limit_per_database,
            'processed_at': search.processed_at.strftime('%Y-%m-%d %H:%M:%S') if search.processed_at is not None else None,
            'papers': papers,
        }
