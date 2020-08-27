import os
import datetime
import logging
from typing import Optional, List
from findpapers.models.search import Search
import findpapers.searcher.scopus_searcher as scopus_searcher
import findpapers.searcher.ieee_searcher as ieee_searcher
import findpapers.searcher.pubmed_searcher as pubmed_searcher
import findpapers.searcher.arxiv_searcher as arxiv_searcher


def _database_safe_run(function, search, database_label):
    if not search.has_reached_its_limit():
        logging.info(f'Fetching papers from {database_label} database...')
        try:
            function()
        except Exception:  # pragma: no cover
            logging.error(
                f'Error while fetching papers from {database_label} database', exc_info=True)


def get(query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None) -> Search:

    if ieee_api_token is None:
        ieee_api_token = os.getenv('IEEE_API_TOKEN')

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')

    search = Search(query, since, until, limit)

    _database_safe_run(lambda: arxiv_searcher.run(search), search, 'arXiv')
    _database_safe_run(lambda: pubmed_searcher.run(search), search, 'PubMed')

    if ieee_api_token is not None:
        _database_safe_run(lambda: ieee_searcher.run(
            search, ieee_api_token), search, 'IEEE')

    if scopus_api_token is not None:
        _database_safe_run(lambda: scopus_searcher.run(
            search, scopus_api_token), search, 'Scopus')

        logging.info('Enriching publication data using Scopus database...')
        try:
            scopus_searcher.enrich_publication_data(search, scopus_api_token)
        except Exception:  # pragma: no cover
            logging.error('Error while fetching data from Scopus database', exc_info=True)

    return search
