from __future__ import annotations
from typing import List, Optional
import json


class Publication():
    """
    Class that represents a publication (journal, conference proceeding, book) instance
    """

    def __init__(self, title: str, isbn: Optional[str] = None, issn: Optional[str] = None, publisher: Optional[str] = None,
                 category: Optional[str] = None, cite_score: Optional[float] = None, sjr: Optional[float] = None,
                 snip: Optional[float] = None, subject_areas: Optional[set] = None):
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
        cite_score : float, optional
            CiteScore measures average citations received per document published in the serial, by default None
        sjr : float, optional
            SCImago Journal Rank measures weighted citations received by the serial. 
            Citation weighting depends on subject field and prestige (SJR) of the citing serial, by default None
        snip : float, optional
            Source Normalized Impact per Paper measures actual citations received relative to citations 
            expected for the serial’s subject field, by default None
        subject_areas : float, optional
            Publication subjects areas, by default None
        """

        self.title = title
        self.isbn = isbn
        self.issn = issn
        self.publisher = publisher
        self.category = category
        self.cite_score = cite_score
        self.sjr = sjr
        self.snip = snip
        self.subject_areas = subject_areas if subject_areas is not None else set()

    @property
    def category(self):
        return self._category

    @category.setter
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

    def enrich(self, publication: Publication):
        """
        e can enrich some publication information using a duplication of it found in another database.
        This method do this using a provided instance of a duplicated publication

        Parameters
        ----------
        publication : Publication
            A duplication of the "self" publication
        """

        if len(self.title) < len(publication.title):
            self.title = publication.title

        if self.isbn is None:
            self.isbn = publication.isbn

        if self.issn is None:
            self.issn = publication.issn

        if self.publisher is None:
            self.publisher = publication.publisher

        if self.category is None or (self.category == 'Other' and publication.category is not None):
            self.category = publication.category

        if self.cite_score is None:
            self.cite_score = publication.cite_score

        if self.sjr is None:
            self.sjr = publication.sjr

        if self.snip is None:
            self.snip = publication.snip

        for subject_area in publication.subject_areas:
            self.subject_areas.add(subject_area)

    @classmethod
    def from_dict(cls, publication_dict: dict) -> Publication:
        """
        A method that returns a Publication instance based on the provided dict object

        Parameters
        ----------
        publication_dict : dict
            A dict that represents a Publication instance

        Returns
        -------
        Publication
            A Publication instance based on the provided dict object
        """

        title = publication_dict.get('title')
        isbn = publication_dict.get('isbn')
        issn = publication_dict.get('issn')
        publisher = publication_dict.get('publisher')
        category = publication_dict.get('category')
        cite_score = publication_dict.get('cite_score')
        sjr = publication_dict.get('sjr')
        snip = publication_dict.get('snip')
        subject_areas = set(publication_dict.get('subject_areas'))

        return cls(title, isbn, issn, publisher, category, cite_score, sjr, snip, subject_areas)

    @staticmethod
    def to_dict(publication: Publication) -> dict:
        """
        A method that returns a dict object based on the provided Publication instance

        Parameters
        ----------
        publication : Publication
            A Publication instance

        Returns
        -------
        dict
            A dict that represents a Publication instance
        """

        return {
            'title': publication.title,
            'isbn': publication.isbn,
            'issn': publication.issn,
            'publisher': publication.publisher,
            'category': publication.category,
            'cite_score': publication.cite_score,
            'sjr': publication.sjr,
            'snip': publication.snip,
            'subject_areas': list(publication.subject_areas)
        }


# https://stackoverflow.com/questions/48991911/how-to-write-a-custom-json-decoder-for-a-complex-object

# class PublicationEncoder(json.JSONEncoder):
#     def default(self, publication):
#         return {
#             'title': publication.title,
#             'isbn': publication.isbn,
#             'issn': publication.issn,
#             'publisher': publication.publisher,
#             'category': publication.category,
#             'cite_score': publication.cite_score,
#             'sjr': publication.sjr,
#             'snip': publication.snip,
#             'subject_areas': list(publication.subject_areas)
#         }

# class EdgeDecoder(json.JSONDecoder):
#     def __init__(self, *args, **kwargs):
#         json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
#     def object_hook(self, dct):
#         if 'Actor' in dct:
#             actor = Actor(dct['Actor']['Name'], dct['Actor']['Age'], '')
#             movie = Movie(dct['Movie']['Title'], dct['Movie']['Gross'], '', dct['Movie']['Year'])
#             return Edge(actor, movie)
#         return dct


# class EdgeEncoder(json.JSONEncoder):
#     def default(self, o):
#         if isinstance(o, Edge):
#             return {
#                     "Actor": {
#                              "Name": o.get_actor().get_name(),
#                              "Age": o.get_actor().get_age()
#                              },
#                     "Movie": {
#                              "Title": o.get_movie().get_title(),
#                              "Gross": o.get_movie().get_gross(),
#                              "Year": o.get_movie().get_year()
#                              }
#                     }
#         return json.JSONEncoder.default(self, o)

# class EdgeDecoder(json.JSONDecoder):
#     def __init__(self, *args, **kwargs):
#         json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
#     def object_hook(self, dct):
#         if 'Actor' in dct:
#             actor = Actor(dct['Actor']['Name'], dct['Actor']['Age'], '')
#             movie = Movie(dct['Movie']['Title'], dct['Movie']['Gross'], '', dct['Movie']['Year'])
#             return Edge(actor, movie)
#         return dct


# filename='test.json'
# movie = Movie('Python', 'many dollars', '', '2000')
# actor = Actor('Casper Van Dien', 49, '')
# edge = Edge(actor, movie)
# with open(filename, 'w') as jsonfile:
#     json.dump(edge, jsonfile, cls=EdgeEncoder)
# with open(filename, 'r') as jsonfile:
#     edge1 = json.load(jsonfile, cls=EdgeDecoder)
# assert edge1 == edge
