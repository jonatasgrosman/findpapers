import os
import datetime
import logging
from typing import Optional, List
from findpapers.models.search import Search
import findpapers.searcher.scopus_searcher as scopus_searcher

logger = logging.getLogger(__name__)


def get(query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, scopus_api_token: Optional[str] = None) -> Search:

    search = Search(query, since, until, limit)

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')

    if scopus_api_token is not None:
        logger.info('Fetching papers from Scopus library...')
        scopus_searcher.run(search, scopus_api_token)

    return search

# remember to get bibliometrics from ACM too, e.g., https://dl.acm.org/journal/csur
# and show those values (from ACM and SCOPUS) in a segmented way while selecting papers
