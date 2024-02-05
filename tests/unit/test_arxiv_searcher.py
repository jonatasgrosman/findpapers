import datetime
import copy
import pytest
import findpapers.searchers.arxiv_searcher as arxiv_searcher
from findpapers.models.search import Search
from findpapers.models.publication import Publication

paper_entry = {
    "title": "title fake",
    "published": "2020-02-27T13:35:26Z",
    "arxiv:journal_ref": {
        "#text": "fake publication name"
    },
    "category": [  # can be a single value
        {"@term": "astro-ph"}
    ],
    "arxiv:doi": {
        "#text": "fake-doi"
    },
    "summary": "a long abstract",
    "link": [  # can be a single value
        {"@href": "http://fake-url-A"},
        {"@href": "http://fake-url-B"},
    ],
    "author": [  # can be a single value
        {"name": "author A"},
        {"name": "author B"},
    ],
    "arxiv:comment": {
        "#text": "fake comment"
    }
}

@pytest.mark.skip(reason="It needs some revision after some tool's refactoring")
def test_get_search_url(search: Search):

    start_record = 25
    query = "all:this AND (all:that thing OR all:something) ANDNOT all:anything"

    url = f"http://export.arxiv.org/api/query?search_query={query}&start={start_record}&sortBy=submittedDate&sortOrder=descending&max_results={arxiv_searcher.MAX_ENTRIES_PER_PAGE}"

    assert arxiv_searcher._get_search_url(search, start_record) == url


def test_mocks():

    assert arxiv_searcher._get_api_result() is not None


def test_get_publication():

    publication = arxiv_searcher._get_publication(paper_entry)

    assert publication.title == paper_entry.get(
        "arxiv:journal_ref").get("#text")
    assert publication.isbn is None
    assert publication.issn is None
    assert publication.publisher is None
    assert publication.category is None
    assert len(publication.subject_areas) == 1
    assert "Astrophysics" in publication.subject_areas

    alternative_paper_entry = copy.deepcopy(paper_entry)
    alternative_paper_entry["category"] = paper_entry.get("category")[0]

    publication = arxiv_searcher._get_publication(alternative_paper_entry)
    assert len(publication.subject_areas) == 1
    assert "Astrophysics" in publication.subject_areas


def test_get_paper(publication: Publication):

    publication_date = datetime.date(2020, 2, 27)

    paper = arxiv_searcher._get_paper(
        paper_entry, publication_date, publication)

    assert paper.publication == publication
    assert paper.title == paper_entry.get("title")
    assert paper.publication_date == publication_date
    assert paper.doi == paper_entry.get("arxiv:doi").get("#text")
    assert paper.citations is None
    assert paper.abstract == paper_entry.get("summary")
    assert len(paper.authors) == 2
    assert "author B" in paper.authors
    assert len(paper.keywords) == 0
    assert len(paper.urls) == 2
    assert "http://fake-url-B" in paper.urls

    alternative_paper_entry = copy.deepcopy(paper_entry)
    alternative_paper_entry["link"] = paper_entry.get("link")[0]
    alternative_paper_entry["author"] = paper_entry.get("author")[0]

    paper = arxiv_searcher._get_paper(
        alternative_paper_entry, publication_date, publication)
    assert len(paper.urls) == 1
    assert "http://fake-url-A" in paper.urls
    assert len(paper.authors) == 1
    assert "author A" in paper.authors


def test_run(search: Search):

    search.limit = 20
    search.limit_per_database = None
    search.since = datetime.date(2020,8,26)
    search.until = datetime.date(2020,8,26)

    arxiv_searcher.run(search)

    assert len(search.papers) == 18
