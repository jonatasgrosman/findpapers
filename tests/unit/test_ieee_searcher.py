import datetime
import pytest
import findpapers.searchers.ieee_searcher as ieee_searcher
from findpapers.models.search import Search
from findpapers.models.publication import Publication

paper_entry = {
    "title": "title fake",
    "publication_date": "01 Mar 2020",
    "doi": "fakeDOI",
    "citing_paper_count": 10,
    "abstract": "a long fake abstract",
    "publication_title": "fake publication title",
    "isbn": "fake ISBN",
    "issn": "fake ISSN",
    "publisher": "publisher X",
    "content_type": "journal",
    "pdf_url": "http://pdf_url",
    "index_terms": {
        "author_terms": {"terms": ["term A", "term B"]}
    },
    "authors": {
        "authors": [
            {"full_name": "author A"},
            {"full_name": "author B"},
        ]
    }
}


def test_get_search_url(search: Search):

    api_token = "fake-token"
    start_record = 200

    query = search.query.replace(" AND NOT ", " NOT ")

    url = f"http://ieeexploreapi.ieee.org/api/v1/search/articles?querytext=({query})&format=json&apikey={api_token}&max_records=200"
    url += f"&start_year={search.since.year}"
    url += f"&end_year={search.until.year}"
    url += f"&start_record={start_record}"

    assert ieee_searcher._get_search_url(search, api_token, start_record) == url


def test_mocks():

    assert ieee_searcher._get_api_result() is not None


def test_get_publication():

    publication = ieee_searcher._get_publication(paper_entry)

    assert publication.title == paper_entry.get("publication_title")
    assert publication.isbn == paper_entry.get("isbn")
    assert publication.issn == paper_entry.get("issn")
    assert publication.publisher == paper_entry.get("publisher")
    assert publication.category == "Journal"


def test_get_paper(publication: Publication):

    paper = ieee_searcher._get_paper(paper_entry, publication)

    assert paper.publication == publication

    assert paper.title == paper_entry.get("title")
    assert paper.publication_date == datetime.date(2020, 3, 1)
    assert paper.doi == paper_entry.get("doi")
    assert paper.citations == paper_entry.get("citing_paper_count")
    assert paper.abstract == paper_entry.get("abstract")
    assert len(paper.authors) == 2
    assert "author A" in paper.authors
    assert len(paper.keywords) == 2
    assert "term A" in paper.keywords
    assert len(paper.urls) == 1
    assert paper_entry.get("pdf_url") in paper.urls


def test_run(search: Search):

    search.limit = 26
    ieee_searcher.run(search, "fake-api-token")

    assert len(search.papers) == 26

    with pytest.raises(AttributeError):
        ieee_searcher.run(search, "")

    with pytest.raises(AttributeError):
        ieee_searcher.run(search, None)
