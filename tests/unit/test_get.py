import os
import json
import findpapers


def test_get():

    os.environ['SCOPUS_API_TOKEN'] = 'api-fake-token'
    os.environ['IEEE_API_TOKEN'] = 'api-fake-token'
    search = findpapers.get('this AND that')

    scopus_papers_test_count = 4
    ieee_papers_test_count = 25
    pubmed_papers_test_count = 1
    arxiv_papers_test_count = 20

    assert len(search.papers) == scopus_papers_test_count + \
        ieee_papers_test_count + pubmed_papers_test_count + arxiv_papers_test_count
