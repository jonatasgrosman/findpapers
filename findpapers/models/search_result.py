import datetime
import itertools
import edlib
from typing import List, Optional
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication


class SearchResult():
    """
    Class that represents a search result
    """

    valid_areas = ['computer_science', 'economics', 'engineering',
                   'mathematics', 'physics', 'biology', 'chemistry', 'humanities']

    def __init__(self, query: str, since: Optional[datetime.date] = None, areas: List[str] = None):
        """
        Class constructor

        Parameters
        ----------
        query : str
            The query used to fetch the papers
        since : int
            The lower bound (inclusive) date of search , by default None
        areas : List[str]
            List of areas of interest that limited the field of search for papers.
            The available areas are: computer_science, economics, engineering, mathematics, physics, biology, chemistry and humanities

        Raises
        ------
        ValueError
            - Only "computer_science", "economics", "engineering", "mathematics", "physics", "biology", "chemistry" and "humanities" are valid areas' 
        """

        self.query = query
        self.since = since

        # checking the areas
        if areas is not None:
            for area in areas:
                if area not in SearchResult.valid_areas:
                    raise ValueError(
                        f'Invalid area "{area}". Only {"".join(SearchResult.valid_areas)} are valid areas')
        self.areas = areas

        self.fetched_at = datetime.datetime.utcnow()
        self.papers = set()
        self.paper_by_key = {}
        self.publication_by_key = {}

    def get_paper_key(self, paper_title: str, publication_date: datetime.date) -> str:
        """
        We have a map called paper_by_key that is filled using the string this method returns

        Parameters
        ----------
        paper_title : str
            The paper title
        publication_date : datetime.date
            The paper publication date

        Returns
        -------
        str
            A string that represents a unique key for each paper, that will be used to fill and retrieve values from paper_by_key
        """
        return f'{paper_title.lower()}-{publication_date}'

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

        return f'{publication_title.lower()}-{str(publication_issn).lower()}-{str(publication_isbn).lower()}'

    def add_paper(self, paper: Paper):
        """
        Method that handle the action to add a paper to the list of already collected papers, 
        dealing with possible paper's duplications

        Parameters
        ----------
        paper : Paper
            A new collected paper instance
        """

        publication_key = self.get_publication_key(paper.publication.title, paper.publication.issn, paper.publication.isbn)
        already_collected_publication = self.publication_by_key.get(publication_key, None)

        if already_collected_publication is not None:
            already_collected_publication.enrich(paper.publication)
            paper.publication = already_collected_publication
        else:
            self.publication_by_key[publication_key] = paper.publication

        paper_key = self.get_paper_key(paper.title, paper.publication_date)
        already_collected_paper = self.paper_by_key.get(paper_key, None)

        if self.since is None or paper.publication_date >= self.since:

            if already_collected_paper is None:
                self.papers.add(paper)
                self.paper_by_key[paper_key] = paper
            else:
                already_collected_paper.enrich(paper)

    def get_paper(self, paper_title: str, publication_date: str) -> Paper:
        """
        Get a collected paper by paper's title and publication date

        Parameters
        ----------
        paper_title : str
            The paper title
        publication_date : datetime.date
            The paper publication date

        Returns
        -------
        Paper
            The wanted paper, or None if there isn't a paper given by the provided arguments
        """

        paper_key = self.get_paper_key(paper_title, publication_date)

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

        paper_key = self.get_paper_key(paper.title, paper.publication_date)

        if paper_key in self.paper_by_key:
            del self.paper_by_key[paper_key]

        self.papers.remove(paper)

    def merge_duplications(self, similarity_threshold: float = 0.9):
        """
        In some cases, a same paper is represented with tiny differences between some libraries, 
        this method try to deal with this situation merging those instances of the paper,
        using a similarity threshold, by default 0.9 (90%), i.e., if two papers metadata is similar by 80% or more 
        this papers are considered duplications of a same paper.
        The method use the paper key (see: SearchResult.get_paper_key) to calculate the similarity between the papers

        Parameters
        ----------
        max_similarity_threshold : float, optional
            A value between 0 and 1 that represents a threshold that says if a pair of papers is a duplication or not, by default 0.9 (90%)
        """

        paper_key_pairs = list(itertools.combinations(self.paper_by_key.keys(), 2))

        for i, pair in enumerate(paper_key_pairs):

            paper_1_key = pair[0]
            paper_2_key = pair[1]

            max_key_length = max(len(paper_1_key), len(paper_2_key))

            # creating the max valid edit distance using the max key length between the two papers and the provided similarity threshold
            max_edit_distance = int(max_key_length * (1 - similarity_threshold))

            # calculating the edit distance between the keys
            titles_edit_distance = edlib.align(paper_1_key, paper_2_key)['editDistance']

            if titles_edit_distance <= max_edit_distance:

                paper_1 = self.paper_by_key.get(paper_1_key)
                paper_2 = self.paper_by_key.get(paper_2_key)

                # using the information of paper_2 to enrich paper_1
                paper_1.enrich(paper_2)

                # removing the paper_2 instance
                self.remove_paper(paper_2)
