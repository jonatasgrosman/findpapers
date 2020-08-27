import os
import pytest
import json
from lxml import html
import findpapers.searcher.ieee_searcher as ieee_searcher


@pytest.fixture(autouse=True)
def mock_ieee_get_api_result(monkeypatch):

    def mocked_search_results(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/ieee-api-search.json')
        search_results = json.load(open(filename))

        return search_results

    monkeypatch.setattr(ieee_searcher, '_get_api_result', mocked_search_results)
