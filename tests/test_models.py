import datetime, pytest
from findpapers import util as Util
from findpapers.models.bibliometrics import AcmBibliometrics, ScopusBibliometrics
from findpapers.models.publication import Publication
from findpapers.models.paper import Paper

def test_bibliometrics():

    acm_bibliometrics = AcmBibliometrics(5.2)
    assert acm_bibliometrics.average_citation_per_article == 5.2
    assert acm_bibliometrics.average_downloads_per_article is None

    acm_bibliometrics = AcmBibliometrics(2.2, 4.7)
    assert acm_bibliometrics.average_citation_per_article == 2.2
    assert acm_bibliometrics.average_downloads_per_article == 4.7

    scopus_bibliometrics = ScopusBibliometrics(2.5)
    assert scopus_bibliometrics.cite_score == 2.5
    assert scopus_bibliometrics.sjr is None
    assert scopus_bibliometrics.snip is None

    scopus_bibliometrics = ScopusBibliometrics(3.5, 7.5, 1.0)
    assert scopus_bibliometrics.cite_score == 3.5
    assert scopus_bibliometrics.sjr == 7.5
    assert scopus_bibliometrics.snip == 1.0


def test_publication():

    publication = Publication('some awesome title')

    assert publication.title == 'some awesome title'
    assert publication.isbn == None
    assert publication.issn == None
    assert publication.publisher == None
    assert publication.category == None
    assert len(publication.bibliometrics_list) == 0

    publication = Publication('some awesome title', 'isbn-X', 'issn-X', 'that publisher', 'Journal')

    assert publication.title == 'some awesome title'
    assert publication.isbn == 'isbn-X'
    assert publication.issn == 'issn-X'
    assert publication.publisher == 'that publisher'
    assert publication.category == 'Journal'
    assert len(publication.bibliometrics_list) == 0

    publication.category = 'book series'
    assert publication.category == 'Book'

    publication.category = 'journal article'
    assert publication.category == 'Journal'

    publication.category = 'Conference'
    assert publication.category == 'Conference Proceeding'

    publication.category = 'newspaper article'
    assert publication.category == 'Other'

    acm_bibliometrics = AcmBibliometrics(5.2, 1.2)
    publication.add_bibliometrics(acm_bibliometrics)
    assert len(publication.bibliometrics_list) == 1
    assert acm_bibliometrics in publication.bibliometrics_list

    other_acm_bibliometrics = AcmBibliometrics(7.2, 1.2)
    publication.add_bibliometrics(other_acm_bibliometrics)
    assert len(publication.bibliometrics_list) == 1
    assert other_acm_bibliometrics not in publication.bibliometrics_list

    another_publication = Publication('another awesome title')
    scopus_bibliometrics = ScopusBibliometrics(3.5, 7.5, 1.0)
    another_publication.add_bibliometrics(scopus_bibliometrics)

    publication.enrich(another_publication)
    assert len(publication.bibliometrics_list) == 2
    assert scopus_bibliometrics in publication.bibliometrics_list


def test_paper():

    publication = Publication('some awesome title', 'isbn-X', 'issn-X', 'that publisher', 'Journal')
    authors = {'Dr Paul', 'Dr John', 'Dr George', 'Dr Ringo'}
    publication_date = datetime.date(1969,1,30)
    paper_url = "https://en.wikipedia.org/wiki/The_Beatles'_rooftop_concert"
    urls = {paper_url}

    paper = Paper('a paper awesome title', 'a long abstract', authors, publication, publication_date, urls)
    assert paper.title == 'a paper awesome title'
    assert paper.abstract == 'a long abstract'
    assert paper.authors == authors
    assert paper.publication == publication
    assert paper.publication_date == publication_date
    assert paper.urls == urls
    assert len(paper.libraries) == 0

    with pytest.raises(ValueError):
        paper.add_library('INVALID LIBRARY')

    paper.add_library('Scopus')
    paper.add_library('Scopus')
    assert len(paper.libraries) == 1

    paper.add_library('ACM')
    assert len(paper.libraries) == 2

    assert len(paper.urls) == 1
    paper.add_url(paper_url)
    assert len(paper.urls) == 1

    paper.add_url('another://url')
    assert len(paper.urls) == 2

    paper_citations = 30
    another_paper_citations = 10
    another_doi = 'DOI-X'
    another_keywords = {'key-A', 'key-B', 'key-C'}
    another_comments = 'some comments'

    paper.citations = paper_citations
    
    another_paper = Paper('another paper awesome title', 'a long abstract', authors, publication, 
                            publication_date, urls, another_doi, another_paper_citations, another_keywords, another_comments)
    another_paper.add_library('arXiv')

    paper.enrich(another_paper)

    assert 'arXiv' in paper.libraries
    assert len(paper.libraries) == 3
    assert paper.doi == another_doi
    assert paper.citations == paper_citations # 'cause another_paper_citations was lower than paper_citations
    assert paper.keywords == another_keywords
    assert paper.comments == another_comments