import os
import pytest
import xmltodict
import findpapers.searcher.pubmed_searcher as pubmed_searcher


@pytest.fixture(autouse=True)
def mock_pubmed_get_api_result(monkeypatch):

    def mocked_search_results(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/pubmed-api-search.xml')
        with open(filename) as f:
            data = xmltodict.parse(f.read())
        return data

    monkeypatch.setattr(pubmed_searcher, '_get_api_result',
                        mocked_search_results)


@pytest.fixture(autouse=True)
def mock_pubmed_get_paper_entry(monkeypatch):

    def mocked_search_results(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/pubmed-api-paper.xml')
        with open(filename) as f:
            data = xmltodict.parse(f.read())
        return data

    monkeypatch.setattr(pubmed_searcher, '_get_paper_entry',
                        mocked_search_results)
