import datetime
from typing import List, Optional


class Search():
    """
    Class that represents a search
    """

    valid_areas = ['computer_science', 'economics', 'engineering', 'mathematics', 'physics', 'biology', 'chemistry', 'humanities']

    def __init__(self, query: str, since_year: Optional[int] = None, areas: List[str] = None):
        """
        Class constructor

        Parameters
        ----------
        query : str
            The query used to fetch the papers
        since_year : int
            The lower bound (inclusive) year of the search , by default None
        areas : List[str]
            List of areas of interest that limited the field of search for papers.
            The available areas are: computer_science, economics, engineering, mathematics, physics, biology, chemistry and humanities

        Raises
        ------
        ValueError
            - Only "computer_science", "economics", "engineering", "mathematics", "physics", "biology", "chemistry" and "humanities" are valid areas' 
        """

        self.query = query
        self.since_year = since_year

        # checking the areas
        if areas is not None:
            for area in areas:
                if area not in Search.valid_areas:
                    raise ValueError(
                        f'Invalid area "{area}". Only {"".join(Search.valid_areas)} are valid areas')
        self.areas = areas

        self.fetched_at = datetime.datetime.utcnow()
        self.papers = []

    # def add_paper(self, paper)
    # def get_paper(self, title, publication_date)
    # def get_publication(self, title, issn, isbn)
