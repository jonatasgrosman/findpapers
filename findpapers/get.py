import os
from typing import Optional, List
from findpapers.model.paper import Paper


def get(query: str, since: Optional[int] = None, area: Optional[str] = None, scopus_api_token: Optional[str] = None) -> List[Paper]:

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')

    print(scopus_api_token)

    return []

# remember to get bibliometrics from ACM too, e.g., https://dl.acm.org/journal/csur
# and show those values (from ACM and SCOPUS) in a segmented way while selecting papers
