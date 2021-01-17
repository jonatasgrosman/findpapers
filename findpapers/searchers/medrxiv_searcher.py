from findpapers.models.search import Search
import findpapers.searchers.rxiv_searcher as rxiv_searcher

DATABASE_LABEL = 'medRxiv'

def run(search: Search):
    """
    This method fetch papers from medRxiv database using the provided search parameters
    After fetch the data from medRxiv, the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance
    """

    rxiv_searcher.run(search, DATABASE_LABEL)
