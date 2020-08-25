import os
import pytest
import json
from lxml import html
import findpapers.searcher.scopus_searcher as scopus_searcher


def prevent_search_results_infinite_loop(search_results):
    # creating fake paper titles for next recursion
    for i, entry in enumerate(search_results.get('entry')):
        entry['dc:title'] = f'FAKE PAPER TITLE {i}'

    search_results['link'] = []  # preventing infinite recursion


@pytest.fixture(autouse=True)
def mock_scopus_get_search_results(monkeypatch):

    def mocked_search_results(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/scopus-api-search.json')
        search_results = json.load(open(filename)).get('search-results')

        # if it's a recursive call for new search results
        if len(args) > 0 and args[2] is not None:
            prevent_search_results_infinite_loop(search_results)

        return search_results

    monkeypatch.setattr(
        scopus_searcher, '_get_search_results', mocked_search_results)


@pytest.fixture(autouse=True)
def mock_scopus_get_publication_entry(monkeypatch):

    def mocked_publication_entry(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/scopus-api-publication.json')
        return json.load(open(filename))['serial-metadata-response']['entry'][0]

    monkeypatch.setattr(
        scopus_searcher, '_get_publication_entry', mocked_publication_entry)


@pytest.fixture(autouse=True)
def mock_scopus_get_paper_page(monkeypatch):

    def mocked_paper_page(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/scopus-paper-page.html')
        with open(filename) as f:
            page = f.read()
        return html.fromstring(page)

    monkeypatch.setattr(scopus_searcher, '_get_paper_page', mocked_paper_page)


@pytest.fixture
def mock_scopus_get_search_results_entry_error(monkeypatch):

    def mocked_search_results(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/scopus-api-search.json')
        search_results = json.load(open(filename))['search-results']

        # removing the title value from the first paper
        del search_results.get('entry')[0]['dc:title']

        # if it's a recursive call for new search results
        if len(args) > 0 and args[2] is not None:
            prevent_search_results_infinite_loop(search_results)

        return search_results

    monkeypatch.setattr(
        scopus_searcher, '_get_search_results', mocked_search_results)


@pytest.fixture
def mock_scopus_get_paper_page_error(monkeypatch):

    def mocked_paper_page(*args, **kwargs):
        raise RuntimeError()

    monkeypatch.setattr(scopus_searcher, '_get_paper_page', mocked_paper_page)
