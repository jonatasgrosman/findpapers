import datetime
import pytest
from urllib.parse import quote_plus
import findpapers.searchers.rxiv_searcher as rxiv_searcher
from findpapers.models.search import Search
from findpapers.models.publication import Publication


def test_get_search_urls(search: Search):

    search.query = "([term a] AND [term b]) OR ([term c] OR [term d])"
    urls = rxiv_searcher._get_search_urls(search, "medRxiv")

    assert len(urls) == 2

    with pytest.raises(ValueError): # wildcards not supported
        search.query = "([term a] AND [term ?]) OR ([term c] OR [term d])"
        rxiv_searcher._get_search_urls(search, "medRxiv")

    with pytest.raises(ValueError): # AND NOT not supported
        search.query = "([term a] AND NOT [term b]) OR ([term c] OR [term d])"
        rxiv_searcher._get_search_urls(search, "medRxiv")

    with pytest.raises(ValueError): # Max 1-level parentheses group
        search.query = "(([term a] OR [term b]) OR ([term c] OR [term d])) OR [term e]"
        rxiv_searcher._get_search_urls(search, "medRxiv")

    with pytest.raises(ValueError): # only OR between groups
        search.query = "([term a] AND [term b]) AND ([term c] OR [term d])"
        rxiv_searcher._get_search_urls(search, "medRxiv")

    with pytest.raises(ValueError): # Mixed connectors not supported
        search.query = "([term a] AND [term b] OR [term c])"
        rxiv_searcher._get_search_urls(search, "medRxiv")

