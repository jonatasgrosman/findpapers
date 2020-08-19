import os
import datetime
from typing import Optional, List
from findpapers.models.search import Search
import findpapers.scrapper.scopus_scrapper as scopus_scrapper


def get(query: str, since: Optional[datetime.date] = None, areas: Optional[List[str]] = None, scopus_api_token: Optional[str] = None) -> Search:

    search = Search(query, since, areas)

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')

    print(scopus_api_token)

    scopus_scrapper.run(search, scopus_api_token)

    return []

# remember to get bibliometrics from ACM too, e.g., https://dl.acm.org/journal/csur
# and show those values (from ACM and SCOPUS) in a segmented way while selecting papers
