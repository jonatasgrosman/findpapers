import datetime
import pytest
from findpapers.models.publication import Publication
from findpapers.models.paper import Paper
from findpapers.models.search import Search


def test_publication(publication: Publication):

    assert publication.title == 'awesome publication title'
    assert publication.isbn == 'isbn-X'
    assert publication.issn == 'issn-X'
    assert publication.publisher == 'that publisher'
    assert publication.category == 'Journal'

    publication.category = 'book series'
    assert publication.category == 'Book'

    publication.category = 'journal article'
    assert publication.category == 'Journal'

    publication.category = 'Conference'
    assert publication.category == 'Conference Proceeding'

    publication.category = 'newspaper article'
    assert publication.category == 'Other'

    another_publication = Publication('another awesome title')
    another_publication.cite_score = 1.0
    another_publication.sjr = 2.0
    another_publication.snip = 3.0

    publication.issn = None
    publication.isbn = None
    publication.publisher = None
    publication.category = None

    publication.enrich(another_publication)

    assert publication.cite_score == another_publication.cite_score
    assert publication.sjr == another_publication.sjr
    assert publication.snip == another_publication.snip
    assert publication.issn == another_publication.issn
    assert publication.isbn == another_publication.isbn
    assert publication.publisher == another_publication.publisher
    assert publication.category == another_publication.category


def test_paper(paper: Paper):

    assert paper.title == 'awesome paper title'
    assert paper.abstract == 'a long abstract'
    assert paper.authors == {'Dr Paul', 'Dr John', 'Dr George', 'Dr Ringo'}
    assert len(paper.urls) == 1
    assert len(paper.libraries) == 0

    with pytest.raises(ValueError):
        paper.add_library('INVALID LIBRARY')

    paper.add_library('Scopus')
    paper.add_library('Scopus')
    assert len(paper.libraries) == 1

    paper.add_library('ACM')
    assert len(paper.libraries) == 2

    assert len(paper.urls) == 1
    paper.add_url(next(iter(paper.urls)))
    assert len(paper.urls) == 1

    paper.add_url('another://url')
    assert len(paper.urls) == 2

    paper_citations = 30
    another_paper_citations = 10
    another_doi = 'DOI-X'
    another_keywords = {'key-A', 'key-B', 'key-C'}
    another_comments = 'some comments'

    paper.citations = paper_citations

    another_paper = Paper('another awesome title paper', 'a long abstract', paper.authors, paper.publication,
                          paper.publication_date, paper.urls, another_doi, another_paper_citations, another_keywords, another_comments)
    another_paper.add_library('arXiv')

    paper.publication_date = None
    paper.abstract = None
    paper.authors = None
    paper.keywords = None
    paper.enrich(another_paper)
    assert paper.publication_date == another_paper.publication_date
    assert paper.abstract == another_paper.abstract
    assert paper.authors == another_paper.authors
    assert paper.keywords == another_paper.keywords

    assert 'arXiv' in paper.libraries
    assert len(paper.libraries) == 3
    assert paper.doi == another_doi
    # 'cause another_paper_citations was lower than paper_citations
    assert paper.citations == paper_citations
    assert paper.keywords == another_keywords
    assert paper.comments == another_comments


def test_search(paper: Paper):

    search = Search('this AND that', datetime.date(1969, 1, 30), datetime.date(1970, 4, 8), 2)

    assert len(search.papers) == 0

    search.add_paper(paper)
    assert len(search.papers) == 1
    search.add_paper(paper)
    assert len(search.papers) == 1

    another_paper = Paper('awesome paper title 2', 'a long abstract',
                          paper.authors, paper.publication,  paper.publication_date, paper.urls)
    search.add_paper(another_paper)
    assert len(search.papers) == 2

    assert paper == search.get_paper(paper.title, paper.publication_date)
    assert paper.publication == search.get_publication(
        paper.publication.title, paper.publication.issn, paper.publication.isbn)

    search.remove_paper(another_paper)
    assert len(search.papers) == 1
    assert paper in search.papers

    search.add_paper(another_paper)
    assert len(search.papers) == 2

    another_paper_2 = Paper('awesome paper title 3', 'a long abstract',
                            paper.authors, paper.publication,  paper.publication_date, paper.urls)
    with pytest.raises(OverflowError):
        search.add_paper(another_paper_2)

    search.merge_duplications()
    assert len(search.papers) == 1
