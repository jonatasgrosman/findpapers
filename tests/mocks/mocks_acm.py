import os
import random
import pytest
import json
import datetime
from lxml import html
import findpapers.searchers.acm_searcher as acm_searcher


@pytest.fixture(autouse=True)
def mock_acm_get_result(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/acm-search-page.html")
        with open(filename) as f:
            page = f.read()
        return html.fromstring(page)

    monkeypatch.setattr(acm_searcher, "_get_result", mocked_data)


@pytest.fixture(autouse=True)
def mock_get_paper_page(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/acm-paper-page.html")
        with open(filename) as f:
            page = f.read()
        return html.fromstring(page)

    monkeypatch.setattr(acm_searcher, "_get_paper_page", mocked_data)


@pytest.fixture(autouse=True)
def mock_get_paper_metadata(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/acm-paper-metadata.json")
        metadata = json.load(open(filename))
        metadata["DOI"] = f"FAKE-DOI-{datetime.datetime.now()}"
        metadata["title"] = f"FAKE-TITLE-{datetime.datetime.now()}"

        if random.random() > 0.5: 
            # changing data structure in some cases
            metadata["issued"]["date-parts"] = [[2020]]
            metadata["keyword"] = "term A, term B"

        return metadata

    monkeypatch.setattr(acm_searcher, "_get_paper_metadata", mocked_data)
