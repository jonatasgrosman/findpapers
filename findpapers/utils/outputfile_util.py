import json
from findpapers.models.search import Search


def save(search: Search, filepath: str):
    """
    Method used to save a search result in a JSON representation

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
    Method used to load a search result using a JSON representation

    Parameters
    ----------
    filepath : str
        A valid file path containing a JSON representation of the search results
    """

    with open(filepath, 'r') as jsonfile:
        return Search.from_dict(json.load(jsonfile))
