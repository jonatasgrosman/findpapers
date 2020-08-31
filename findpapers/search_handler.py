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


def _database_safe_run(function, search, database_label):
    if not search.reached_its_limit(database_label):
        logging.info(f'Fetching papers from {database_label} database...')
        try:
            function()
        except Exception:  # pragma: no cover
            logging.error(
                f'Error while fetching papers from {database_label} database', exc_info=True)


def run(query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, limit_per_database: Optional[int] = None,
        scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None) -> Search:

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

    with open(filepath, 'w') as jsonfile:
        json.dump(Search.to_dict(search), jsonfile, indent=4, sort_keys=True)


def load(filepath: str):

    with open(filepath, 'r') as jsonfile:
        return Search.from_dict(json.load(jsonfile))
