import json
import re
from typing import Optional
from findpapers.models.search import Search


def save(search: Search, outputpath: str):
    """
    Method used to save a search result in a JSON representation

    Parameters
    ----------
    search : Search
        A Search instance
    outputpath : str
        A valid file path used to save the search results
    """

    with open(outputpath, 'w') as jsonfile:
        json.dump(Search.to_dict(search), jsonfile, indent=2, sort_keys=True)


def load(search_path: str):
    """
    Method used to load a search result using a JSON representation

    Parameters
    ----------
    search_path : str
        A valid file path containing a JSON representation of the search results
    """

    with open(search_path, 'r') as jsonfile:
        return Search.from_dict(json.load(jsonfile))
