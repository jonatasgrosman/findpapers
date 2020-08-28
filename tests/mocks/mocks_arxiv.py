import os
import pytest
import xmltodict
import findpapers.searcher.arxiv_searcher as arxiv_searcher


@pytest.fixture(autouse=True)
def mock_arxiv_get_api_result(monkeypatch):

    def mocked_search_results(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, '../data/arxiv-api-search.xml')
        with open(filename) as f:
            data = xmltodict.parse(f.read())
        return data

    monkeypatch.setattr(arxiv_searcher, '_get_api_result',
                        mocked_search_results)
