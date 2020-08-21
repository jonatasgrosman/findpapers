import os
import findpapers


def test_get(mock_scopus_get_publication_entry, mock_scopus_get_paper_page, mock_scopus_get_search_results):

    os.environ['SCOPUS_API_TOKEN'] = 'api-fake-token'
    search = findpapers.get('this AND that')

    assert len(search.papers) == 4
