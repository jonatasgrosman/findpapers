import pytest
import datetime
import requests
from findpapers.models.publication import Publication
from findpapers.models.paper import Paper
from findpapers.models.search import Search
from findpapers.models.bibliometrics import AcmBibliometrics, ScopusBibliometrics


@pytest.fixture
def acm_bibliometrics():
    return AcmBibliometrics(2.2, 4.7)


@pytest.fixture
def scopus_bibliometrics():
    return ScopusBibliometrics(3.5, 7.5, 1.0)


@pytest.fixture
def publication():
    return Publication('awesome publication title', 'isbn-X', 'issn-X', 'that publisher', 'Journal')


@pytest.fixture
def paper(publication):
    authors = {'Dr Paul', 'Dr John', 'Dr George', 'Dr Ringo'}
    publication_date = datetime.date(1969, 1, 30)
    paper_url = "https://en.wikipedia.org/wiki/The_Beatles'_rooftop_concert"
    urls = {paper_url}

    return Paper('awesome paper title', 'a long abstract', authors, publication, publication_date, urls)


@pytest.fixture
def search():
    return Search('this AND that', datetime.date(1969, 1, 30), 2)


@pytest.fixture(autouse=True)
def disable_network_calls(monkeypatch):
    """Remove requests.sessions.Session.request for all tests."""
    monkeypatch.delattr("requests.sessions.Session.request")
