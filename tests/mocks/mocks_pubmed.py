import os
import pytest
import xmltodict
import random
import datetime
import findpapers.searchers.pubmed_searcher as pubmed_searcher


@pytest.fixture(autouse=True)
def mock_pubmed_get_api_result(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/pubmed-api-search.xml")
        with open(filename) as f:
            data = xmltodict.parse(f.read())
        return data

    monkeypatch.setattr(pubmed_searcher, "_get_api_result", mocked_data)


@pytest.fixture(autouse=True)
def mock_pubmed_get_paper_entry(monkeypatch):

    def mocked_data(*args, **kwargs):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, "../data/pubmed-api-paper.xml")
        with open(filename) as f:
            data = xmltodict.parse(f.read())

        data["PubmedArticleSet"]["PubmedArticle"]["MedlineCitation"][
            "Article"]["ArticleTitle"] = f"FAKE-TITLE-{datetime.datetime.now()}"
        data["PubmedArticleSet"]["PubmedArticle"]["PubmedData"]["ArticleIdList"][
            "ArticleId"][1]["#text"] = f"FAKE-DOI-{datetime.datetime.now()}"

        if random.random() > 0.5:
            data["PubmedArticleSet"]["PubmedArticle"]["MedlineCitation"][
            "Article"]["Pagination"]["MedlinePgn"] = f"{random.randint(1,100)}-{random.randint(1,100)}"

        return data

    monkeypatch.setattr(pubmed_searcher, "_get_paper_entry", mocked_data)
