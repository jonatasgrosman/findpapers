import os
import pytest
import json
import datetime
from lxml import html
import findpapers.searchers.scopus_searcher as scopus_searcher


@pytest.fixture(autouse=True)
def mock_scopus_get_search_results(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/scopus-api-search.json")
        search_results = json.load(open(filename)).get("search-results")

        for entry in search_results.get("entry"):
            entry["dc:title"] = f"FAKE-TITLE-{datetime.datetime.now()}"
            entry["prism:doi"] = f"FAKE-DOI-{datetime.datetime.now()}"

        # if it"s a recursive call for new search results
        if len(args) > 0 and args[2] is not None:
            search_results["link"] = []  # preventing infinite recursion

        return search_results

    monkeypatch.setattr(
        scopus_searcher, "_get_search_results", mocked_data)


@pytest.fixture(autouse=True)
def mock_scopus_get_publication_entry(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/scopus-api-publication.json")
        return json.load(open(filename))["serial-metadata-response"]["entry"][0]

    monkeypatch.setattr(
        scopus_searcher, "_get_publication_entry", mocked_data)


@pytest.fixture(autouse=True)
def mock_scopus_get_paper_page(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/scopus-paper-page.html")
        with open(filename) as f:
            page = f.read()
        return html.fromstring(page)

    monkeypatch.setattr(scopus_searcher, "_get_paper_page", mocked_data)


@pytest.fixture
def mock_scopus_get_paper_page_error(monkeypatch):

    def mocked_data(*args, **kwargs):
        raise RuntimeError()

    monkeypatch.setattr(scopus_searcher, "_get_paper_page", mocked_data)
