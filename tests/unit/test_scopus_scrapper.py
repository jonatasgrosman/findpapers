import datetime
import pytest
import findpapers.searcher.scopus_searcher as scopus_searcher
from findpapers.models.search import Search


def test_get_query(search: Search):

    query = f'TITLE-ABS-KEY({search.query})'
    query += f' AND PUBYEAR > {search.since.year - 1}'

    selected_areas = ['ECON', 'BUSI', 'ARTS',
                      'DECI', 'ENVI', 'PSYC', 'SOCI', 'MULT']
    selected_areas.sort()
    query += f' AND SUBJAREA({" OR ".join(selected_areas)})'

    assert scopus_searcher.get_query(search) == query


def test_mocks(mock_scopus_get_publication_entry, mock_scopus_get_paper_page, mock_scopus_get_search_results):

    assert scopus_searcher.get_publication_entry() is not None
    assert scopus_searcher.get_paper_page() is not None
    assert scopus_searcher.get_search_results() is not None

@pytest.mark.parametrize('paper_entry', [
    ({
        'prism:publicationName': 'fake publication title',
        'prism:isbn': 'fake ISBN',
        'prism:issn': 'fake ISSN',
        'prism:aggregationType': 'journal',
    }),
    ({
        'prism:publicationName': 'fake publication title',
        'prism:isbn': [{'$': 'fake ISBN'}],
        'prism:issn': [{'$': 'fake ISSN'}],
        'prism:aggregationType': 'journal',
    })
])
def test_get_publication(mock_scopus_get_publication_entry, paper_entry):

    publication = scopus_searcher.get_publication(paper_entry, None)

    assert publication.title == paper_entry.get('prism:publicationName')
    
    if isinstance(paper_entry.get('prism:isbn'), list):
        assert publication.isbn == paper_entry.get('prism:isbn')[0].get('$')
    else:
        assert publication.isbn == paper_entry.get('prism:isbn')

    if isinstance(paper_entry.get('prism:issn'), list):
        assert publication.issn == paper_entry.get('prism:issn')[0].get('$')
    else:
        assert publication.issn == paper_entry.get('prism:issn')
        
    assert publication.publisher == 'Tech Science Press'
    assert publication.category == 'Journal'

    assert len(publication.bibliometrics_list) == 1
    assert publication.bibliometrics_list[0].cite_score == 3.8
    assert publication.bibliometrics_list[0].sjr == 1.534
    assert publication.bibliometrics_list[0].snip == 4.801
    assert publication.bibliometrics_list[0].source_name == 'Scopus'


def test_get_paper(mock_scopus_get_paper_page, publication):

    paper_entry = {
        'dc:title': 'fake paper title',
        'prism:coverDate': '2020-01-01',
        'prism:doi': 'fake-doi',
        'citedby-count': '42',
        'link': [
            {'@ref': 'scopus', '@href': 'http://fake-url'}
        ]
    }

    paper = scopus_searcher.get_paper(paper_entry, publication)

    assert paper.publication == publication
    assert paper.title == paper_entry.get('dc:title')
    assert paper.publication_date == datetime.date(2020, 1, 1)
    assert paper.doi == paper_entry.get('prism:doi')
    assert paper.citations == 42
    assert len(paper.abstract) == 1284
    assert paper.abstract.startswith('With the popularity of deep learning')
    assert len(paper.authors) == 6
    assert 'He, S.' in paper.authors
    assert len(paper.keywords) == 4
    assert 'Tensor decomposition' in paper.keywords
    assert len(paper.urls) == 1
    assert paper_entry.get('link')[0].get('@href') in paper.urls


def test_run(mock_scopus_get_publication_entry, mock_scopus_get_paper_page, mock_scopus_get_search_results, search):

    scopus_searcher.run(search, 'fake-api-token')

    assert len(search.papers) == 2

    paper_titles = [x.title for x in search.papers]

    assert 'MultiWoz - A large-scale multi-domain wizard-of-oz dataset for task-oriented dialogue modelling' in paper_titles
    assert 'BioBERT: A pre-trained biomedical language representation model for biomedical text mining' in paper_titles
