import requests
import datetime
import logging
import re
import math
from lxml import html
from typing import Optional
import findpapers.utils.common_util as util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession


DEFAULT_SESSION = DefaultSession()
DATABASE_LABEL = 'IEEE'
BASE_URL = 'http://ieeexploreapi.ieee.org'
MAX_ENTRIES_PER_PAGE = 200


def _get_search_url(search: Search, api_token: str, start_record: Optional[int] = 1) -> str:
    """
    This method return the URL to be used to retrieve data from IEEE database
    See https://developer.ieee.org/docs/read/Metadata_API_details for query tips

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

    query = search.query.replace(' AND NOT ', ' NOT ')

    url = f'{BASE_URL}/api/v1/search/articles?querytext={query}&format=json&apikey={api_token}&max_records={MAX_ENTRIES_PER_PAGE}'

    if search.since is not None:
        url += f'&start_year={search.since.year}'

    if search.until is not None:
        url += f'&end_year={search.until.year}'

    if start_record is not None:
        url += f'&start_record={start_record}'

    return url


def _get_api_result(search: Search, api_token: str, start_record: Optional[int] = 1) -> dict:  # pragma: no cover
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

    url = _get_search_url(search, api_token, start_record)

    return util.try_success(lambda: DEFAULT_SESSION.get(url).json(), 2)


def _get_publication(paper_entry: dict) -> Publication:
    """
    Using a paper entry provided, this method builds a publication instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from IEEE API

    Returns
    -------
    Publication
        A publication instance or None
    """

    publication_title = paper_entry.get('publication_title', None)

    if publication_title is None or len(publication_title) == 0:
        return None

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
        A paper instance or None
    """

    paper_title = paper_entry.get('title', None)

    if paper_title is None or len(paper_title) == 0:
        return None

    paper_publication_date = paper_entry.get('publication_date', None)
    paper_doi = paper_entry.get('doi', None)
    paper_citations = paper_entry.get('citing_paper_count', None)
    paper_abstract = paper_entry.get('abstract', None)
    paper_urls = {paper_entry.get('pdf_url')}
    paper_pages = None
    paper_number_of_pages = None

    try:
        paper_keywords = set(paper_entry.get(
            'index_terms').get('author_terms').get('terms'))
    except Exception as e:
        paper_keywords = set()

    if paper_publication_date is not None:
        try:
            paper_publication_date_split = paper_publication_date.split(' ')
            day = int(paper_publication_date_split[0].split('-')[0])
            month = int(util.get_numeric_month_by_string(
                paper_publication_date_split[1]))
            year = int(paper_publication_date_split[2])

            paper_publication_date = datetime.date(year, month, day)
        except Exception as e:
            pass

    if not isinstance(paper_publication_date, datetime.date):
        paper_publication_date = datetime.date(
            paper_entry.get('publication_year'), 1, 1)

    paper_authors = []
    for author in paper_entry.get('authors').get('authors'):
        paper_authors.append(author.get('full_name'))

    start_page = paper_entry.get('start_page', None)
    end_page = paper_entry.get('end_page', None)
    

    if start_page is not None and end_page is not None:
        try:
            paper_pages = f"{paper_entry.get('start_page')}-{paper_entry.get('end_page')}"
            paper_number_of_pages = abs(
                int(paper_entry.get('start_page'))-int(paper_entry.get('end_page')))+1
        except Exception:  # pragma: no cover
            pass

    paper = Paper(paper_title, paper_abstract, paper_authors, publication,
                  paper_publication_date, paper_urls, paper_doi, paper_citations, 
                  paper_keywords, None, paper_number_of_pages, paper_pages)

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

    papers_count = 0
    result = _get_api_result(search, api_token)
    total_papers = result.get('total_records')

    logging.info(f'{total_papers} papers to fetch')

    while(papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL)):

        for paper_entry in result.get('articles'):

            if papers_count >= total_papers or search.reached_its_limit(DATABASE_LABEL):
                break
            
            papers_count += 1

            try:

                logging.info(f'({papers_count}/{total_papers}) Fetching IEEE paper: {paper_entry.get("title")}')

                publication = _get_publication(paper_entry)
                paper = _get_paper(paper_entry, publication)

                if paper is not None:
                    paper.add_database(DATABASE_LABEL)
                    search.add_paper(paper)

            except Exception as e:  # pragma: no cover
                logging.debug(e, exc_info=True)

        if papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL):
            result = _get_api_result(search, api_token, papers_count+1)
