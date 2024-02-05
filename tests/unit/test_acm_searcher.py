import datetime
import pytest
from urllib.parse import quote_plus
import findpapers.searchers.acm_searcher as acm_searcher
from findpapers.models.search import Search
from findpapers.models.publication import Publication


def test_get_search_url(search: Search):

    url = acm_searcher._get_search_url(search)

    query = search.query.replace(" AND NOT ", " NOT ")

    assert quote_plus(query) in url
    assert url.startswith("https://dl.acm.org/action/doSearch?")


def test_mocks():

    assert acm_searcher._get_result() is not None
    assert acm_searcher._get_paper_page() is not None
    assert acm_searcher._get_paper_metadata() is not None


def test_get_paper():

    paper_page = acm_searcher._get_paper_page()

    paper = acm_searcher._get_paper(paper_page, "fake-paper-doi", "fake-url")

    assert paper is not None
    assert paper.title is not None
    assert paper.doi is not None
    assert paper.number_of_pages == 2
    assert len(paper.authors) == 3
    assert paper.publication_date.year == 2020
    assert paper.publication is not None
    assert paper.publication.title == "Proceedings of the 7th ACM IKDD CoDS and 25th COMAD"
    assert paper.publication.publisher == "Association for Computing Machinery"
    assert paper.publication.isbn == "9781450377386"


@pytest.mark.skip(reason="It needs some revision after some tool's refactoring")
def test_run(search: Search):

    search.limit = 14
    search.limit_per_database = None

    acm_searcher.run(search)

    assert len(search.papers) == 14
