import datetime
import pytest
import findpapers.searchers.scopus_searcher as scopus_searcher
from findpapers.models.search import Search
from findpapers.models.publication import Publication


def test_get_query(search: Search):

    query = f"TITLE-ABS-KEY({search.query})"
    query += f" AND PUBYEAR > {search.since.year - 1}"
    query += f" AND PUBYEAR < {search.until.year + 1}"

    assert scopus_searcher._get_query(search) == query


def test_mocks():

    assert scopus_searcher._get_publication_entry() is not None
    assert scopus_searcher._get_paper_page() is not None
    assert scopus_searcher._get_search_results() is not None


@pytest.mark.parametrize("paper_entry", [
    ({
        "prism:publicationName": "fake publication title",
        "prism:isbn": "fake ISBN",
        "prism:issn": "fake ISSN",
        "prism:aggregationType": "journal",
    }),
    ({
        "prism:publicationName": "fake publication title",
        "prism:isbn": [{"$": "fake ISBN"}],
        "prism:issn": [{"$": "fake ISSN"}],
        "prism:aggregationType": "journal",
    })
])
def test_get_publication(paper_entry: dict):

    publication = scopus_searcher._get_publication(paper_entry, None)

    assert publication.title == paper_entry.get("prism:publicationName")

    if isinstance(paper_entry.get("prism:isbn"), list):
        assert publication.isbn == paper_entry.get("prism:isbn")[0].get("$")
    else:
        assert publication.isbn == paper_entry.get("prism:isbn")

    if isinstance(paper_entry.get("prism:issn"), list):
        assert publication.issn == paper_entry.get("prism:issn")[0].get("$")
    else:
        assert publication.issn == paper_entry.get("prism:issn")

    assert publication.category == "Journal"


@pytest.mark.skip(reason="It needs some revision after some tool's refactoring")
def test_get_paper(publication: Publication):

    paper_entry = {
        "dc:title": "fake paper title",
        "prism:coverDate": "2020-01-01",
        "prism:doi": "fake-doi",
        "citedby-count": "42",
        "link": [
            {"@ref": "scopus", "@href": "http://fake-url"}
        ]
    }

    paper = scopus_searcher._get_paper(paper_entry, publication, "fake-api-token")

    assert paper.publication == publication
    assert paper.title == paper_entry.get("dc:title")
    assert paper.publication_date == datetime.date(2020, 1, 1)
    assert paper.doi == paper_entry.get("prism:doi")
    assert paper.citations == 42
    assert len(paper.abstract) == 1284
    assert paper.abstract.startswith("With the popularity of deep learning")
    assert len(paper.authors) == 6
    assert "He, S." in paper.authors
    assert len(paper.keywords) == 4
    assert "Tensor decomposition" in paper.keywords
    assert len(paper.urls) == 1
    assert paper_entry.get("link")[0].get("@href") in paper.urls


def test_get_paper_exceptions(publication: Publication, mock_scopus_get_paper_page_error):

    paper_entry = {
        "dc:title": "fake paper title",
        "prism:coverDate": "2020-01-01",
        "prism:doi": "fake-doi",
        "citedby-count": "42",
        "link": [
            {"@ref": "scopus", "@href": "http://fake-url"}
        ]
    }

    paper = scopus_searcher._get_paper(paper_entry, publication, "fake-api-token")

    assert paper.abstract is None
    assert len(paper.keywords) == 0


def test_run(search: Search):

    search.limit = 3
    scopus_searcher.run(search, "fake-api-token")

    assert len(search.papers) == 3

    with pytest.raises(AttributeError):
        scopus_searcher.run(search, "")

    with pytest.raises(AttributeError):
        scopus_searcher.run(search, None)


def test_enrich_publication_data(search: Search):

    with pytest.raises(AttributeError):
        scopus_searcher.enrich_publication_data(search, "")

    with pytest.raises(AttributeError):
        scopus_searcher.enrich_publication_data(search, None)

    scopus_searcher.enrich_publication_data(search, "fake-api-token")

    for publication_key, publication in search.publication_by_key.items():
        assert publication.cite_score is not None
        assert publication.sjr is not None
        assert publication.snip is not None
        assert len(publication.subject_areas) > 0
    