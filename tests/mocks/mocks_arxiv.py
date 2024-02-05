import os
import pytest
import xmltodict
import datetime
import findpapers.searchers.arxiv_searcher as arxiv_searcher


@pytest.fixture(autouse=True)
def mock_arxiv_get_api_result(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/arxiv-api-search.xml")
        with open(filename) as f:
            data = xmltodict.parse(f.read())

        for entry in data["feed"]["entry"]:
            entry["title"] = f"FAKE-TITLE-{datetime.datetime.now()}"
            if "arxiv:doi" in entry:
                entry["arxiv:doi"]["#text"] = f"FAKE-DOI-{datetime.datetime.now()}"

        return data

    monkeypatch.setattr(arxiv_searcher, "_get_api_result", mocked_data)
