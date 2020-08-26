import requests
import datetime
import logging
import re
import math
from lxml import html
from typing import Optional
from fake_useragent import UserAgent
import findpapers.util as util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication

logger = logging.getLogger(__name__)


def _get_url(search: Search, api_token: str, start_record: Optional[int] = 1):
    """
    This method return the URL to be used to retrieve data from IEEE database

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from IEEE database,
    start_record : str
        Sequence number of first record to fetch, by default 1

    Returns
    -------
    str
        a URL to be used to retrieve data from IEEE database
    """

    url = f'http://ieeexploreapi.ieee.org/api/v1/search/articles?querytext={search.query}&format=json&apikey={api_token}&max_records=200'

    if search.since is not None:
        url += f'&start_year={search.since.year}'
    
    if search.until is not None:
        url += f'&end_year={search.until.year}'

    if start_record is not None:
        url += f'&start_record={start_record}'

    return url


def _get_api_result(search: Search, api_token: str, start_record: Optional[int] = 1): # pragma: no cover

    """
    This method return results from IEEE database using the provided search parameters

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from IEEE database,
    start_record : str
        Sequence number of first record to fetch, by default 1

    Returns
    -------
    dict
        a result from IEEE database
    """

    url = _get_url(search, api_token, start_record)

    return util.try_success(lambda: requests.get(url).json())


def _get_publication(paper_entry: dict) -> Publication:
    """
    Using a paper entry provided, this method builds a publication instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from scopus API

    Returns
    -------
    Publication
        A publication instance
    """

    publication_title = paper_entry.get('publication_title', None)
    publication_isbn = paper_entry.get('isbn', None)
    publication_issn = paper_entry.get('issn', None)
    publication_publisher = paper_entry.get('publisher', None)
    publication_category = paper_entry.get('content_type', None)

    publication = Publication(publication_title, publication_isbn,
                              publication_issn, publication_publisher, publication_category)

    return publication


def _get_paper(paper_entry: dict, publication: Publication) -> Paper:
    """
    Using a paper entry provided, this method builds a paper instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from IEEE API
    publication : Publication
        A publication instance that will be associated with the paper

    Returns
    -------
    Paper
        A paper instance
    """

    paper_title = paper_entry.get('title', None)
    paper_publication_date = paper_entry.get('publication_date', None)
    paper_doi = paper_entry.get('doi', None)
    paper_citations = paper_entry.get('citing_paper_count', None)
    paper_abstract = paper_entry.get('abstract', None)
    paper_urls = {paper_entry.get('pdf_url')}
    
    try:
        paper_keywords = set(paper_entry.get('index_terms').get('author_terms').get('terms'))
    except Exception as e:
        paper_keywords = set()
    
    if paper_publication_date is not None:
        try:
            paper_publication_date_split = paper_publication_date.split(' ')
            day = int(paper_publication_date_split[0].split('-')[0])
            month = int(util.get_numeric_month_by_string(paper_publication_date_split[1]))
            year = int(paper_publication_date_split[2])

            paper_publication_date = datetime.date(year, month, day)
        except Exception as e:
            pass
    
    if not isinstance(paper_publication_date, datetime.date):
        paper_publication_date = datetime.date(paper_entry.get('publication_year'), 1, 1)

    paper_authors = []
    for author in paper_entry.get('authors').get('authors'):
        paper_authors.append(author.get('full_name'))

    paper = Paper(paper_title, paper_abstract, paper_authors, publication,
                  paper_publication_date, paper_urls, paper_doi, paper_citations, paper_keywords)

    return paper


def run(search: Search, api_token: str):
    """
    This method fetch papers from IEEE database using the provided search parameters
    After fetch the data from IEEE, the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from IEEE database,

    Raises
    ------
    AttributeError
        - The API token cannot be null
    """

    if api_token is None or len(api_token.strip()) == 0:
        raise AttributeError('The API token cannot be null')
    
    start_record = 1
    result = _get_api_result(search, api_token, start_record)
    total_papers = result.get('total_records')
    total_pages = int(math.ceil(total_papers / 200))

    logging.info(f'{total_papers} papers to fetch')

    for i in range(total_pages):

        if search.has_reached_its_limit():
            break

        for paper_entry in result.get('articles'):

            if search.has_reached_its_limit():
                break

            logging.info(paper_entry.get('title'))

            start_record = paper_entry.get('rank') + 1

            publication = _get_publication(paper_entry)
            paper = _get_paper(paper_entry, publication)
            paper.add_library('IEEE')

            search.add_paper(paper)

            logging.info(f'{start_record-1}/{total_papers} papers fetched')
        
        if start_record < total_papers and not search.has_reached_its_limit(): 
            result = _get_api_result(search, api_token, start_record)
    