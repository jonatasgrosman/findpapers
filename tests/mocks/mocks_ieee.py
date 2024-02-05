import os
import pytest
import json
import datetime
from lxml import html
import findpapers.searchers.ieee_searcher as ieee_searcher


@pytest.fixture(autouse=True)
def mock_ieee_get_api_result(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/ieee-api-search.json")
        search_results = json.load(open(filename))

        for article in search_results.get("articles"):
            article["title"] = f"FAKE-TITLE-{datetime.datetime.now()}"
            article["doi"] = f"FAKE-DOI-{datetime.datetime.now()}"

        return search_results

    monkeypatch.setattr(ieee_searcher, "_get_api_result", mocked_data)
