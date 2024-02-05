import pytest
import datetime
import requests
import findpapers
from findpapers.models.publication import Publication
from findpapers.models.paper import Paper
from findpapers.models.search import Search


@pytest.fixture
def publication():
    return Publication("awesome publication title", "isbn-X", "issn-X", "that publisher", "Journal")


@pytest.fixture
def paper(publication):
    title = "awesome paper title"
    abstract = "a long abstract"
    authors = ["Dr Paul", "Dr John", "Dr George", "Dr Ringo"]
    publication_date = datetime.date(1969, 1, 30)
    paper_url = "https://en.wikipedia.org/wiki/The_Beatles'_rooftop_concert"
    urls = {paper_url}
    doi = "fake-doi"
    citations = 25
    keywords = {"term A", "term B"}
    comments = "some comments"
    number_of_pages = 4
    pages = "1-4"
    databases = {"arXiv", "ACM", "IEEE", "PubMed", "Scopus"}
    selected = True
    categories = {"Facet A": ["Category A", "Category B"]}

    paper = Paper(title, abstract, authors, publication, publication_date, urls, doi, citations, keywords,
                  comments, number_of_pages, pages, databases, selected, categories)

    return paper


@pytest.fixture
def search():
    return Search("\"this\" AND (\"that thing\" OR \"something\") AND NOT \"anything\"", datetime.date(1969, 1, 30), datetime.date(2020, 12, 31), 100, 100)


@pytest.fixture(autouse=True)
def disable_network_calls(monkeypatch):
    """Remove requests.sessions.Session.request for all tests."""
    monkeypatch.delattr("requests.sessions.Session.request")
