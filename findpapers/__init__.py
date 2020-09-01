import os
import datetime
import logging
import json
from typing import Optional, List
from findpapers.models.search import Search
import findpapers.searcher.scopus_searcher as scopus_searcher
import findpapers.searcher.ieee_searcher as ieee_searcher
import findpapers.searcher.pubmed_searcher as pubmed_searcher
import findpapers.searcher.arxiv_searcher as arxiv_searcher
import findpapers.searcher.acm_searcher as acm_searcher


logging_level = os.getenv('LOGGING_LEVEL')
if logging_level is None:  # pragma: no cover
    logging_level = 'INFO'

logging.basicConfig(level=getattr(logging, logging_level),
                    format='%(asctime)s %(levelname)s: %(message)s')


def run(query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, limit_per_database: Optional[int] = None,
        scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None) -> Search:
    """
    When you have a query and needs to get papers using it, this is the method that you'll need to call.
    This method will find papers from some databases based on the provided query, returning a Search instance when the search completes.

    Parameters
    ----------
    query : str
        A query string that will be used to perform the papers search.

        All the query terms need to be enclosed in quotes and can be associated using boolean operators,
        and grouped using parentheses. 
        E.g.: "term A" AND ("term B" OR "term C") AND NOT "term D"

        You can use some wildcards in the query too. Use ? to replace a single character or * to replace any number of characters. 
        E.g.: "son?" -> will match song, sons, ...
        E.g.: "son*" -> will match song, sons, sonar, songwriting, ...

        Note: All boolean operators needs to be uppercased. The boolean operator "NOT" must be preceded by an "AND" operator.

    since : Optional[datetime.date], optional
        A lower bound (inclusive) date that will be used to filter the search results, by default None

    until : Optional[datetime.date], optional
        A upper bound (inclusive) date that will be used to filter the search results, by default None

    limit : Optional[int], optional
        The max number of papers to collect, by default None

    limit_per_database : Optional[int], optional
        The max number of papers to collect per each database, by default None

    scopus_api_token : Optional[str], optional
        A API token used to fetch data from Scopus database. If you don't have one go to https://dev.elsevier.com and get it, by default None

    ieee_api_token : Optional[str], optional
        A API token used to fetch data from IEEE database. If you don't have one go to https://developer.ieee.org and get it, by default None

    Returns
    -------
    Search
        A Search instance containing the search results
    """

    def _database_safe_run(function: callable, search: Search, database_label: str):
        if not search.reached_its_limit(database_label):
            logging.info(f'Fetching papers from {database_label} database...')
            try:
                function()
            except Exception:  # pragma: no cover
                logging.error(
                    f'Error while fetching papers from {database_label} database', exc_info=True)

    if ieee_api_token is None:
        ieee_api_token = os.getenv('IEEE_API_TOKEN')

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')

    search = Search(query, since, until, limit, limit_per_database)

    _database_safe_run(lambda: arxiv_searcher.run(search),
                       search, arxiv_searcher.DATABASE_LABEL)
    _database_safe_run(lambda: pubmed_searcher.run(search),
                       search, pubmed_searcher.DATABASE_LABEL)
    _database_safe_run(lambda: acm_searcher.run(search),
                       search, acm_searcher.DATABASE_LABEL)

    if ieee_api_token is not None:
        _database_safe_run(lambda: ieee_searcher.run(
            search, ieee_api_token), search, ieee_searcher.DATABASE_LABEL)

    if scopus_api_token is not None:
        _database_safe_run(lambda: scopus_searcher.run(
            search, scopus_api_token), search, scopus_searcher.DATABASE_LABEL)

        logging.info('Enriching publication data using Scopus database...')
        try:
            scopus_searcher.enrich_publication_data(search, scopus_api_token)
        except Exception:  # pragma: no cover
            logging.error(
                'Error while fetching data from Scopus database', exc_info=True)

    return search


def save(search: Search, filepath: str):
    """
    A method used to save a search result in a JSON representation

    Parameters
    ----------
    search : Search
        A Search instance
    filepath : str
        A valid file path used to save the search results
    """

    with open(filepath, 'w') as jsonfile:
        json.dump(Search.to_dict(search), jsonfile, indent=2, sort_keys=True)


def load(filepath: str):
    """
    A method used to load a search result using a JSON representation

    Parameters
    ----------
    filepath : str
        A valid file path containing a JSON representation of the search results
    """

    with open(filepath, 'r') as jsonfile:
        return Search.from_dict(json.load(jsonfile))


def refine(search: Search):
    pass
