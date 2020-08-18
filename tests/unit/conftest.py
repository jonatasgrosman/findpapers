import pytest, datetime
from findpapers.models.publication import Publication
from findpapers.models.paper import Paper
from findpapers.models.search_result import SearchResult

@pytest.fixture
def paper():

    publication = Publication('awesome publication title', 'isbn-X', 'issn-X', 'that publisher', 'Journal')
    authors = {'Dr Paul', 'Dr John', 'Dr George', 'Dr Ringo'}
    publication_date = datetime.date(1969,1,30)
    paper_url = "https://en.wikipedia.org/wiki/The_Beatles'_rooftop_concert"
    urls = {paper_url}

    return Paper('awesome paper title', 'a long abstract', authors, publication, publication_date, urls)