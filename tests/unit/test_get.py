import os
import findpapers


def test_get():

    os.environ['SCOPUS_API_TOKEN'] = 'api-fake-token'
    search = findpapers.get('this AND that')

    assert len(search.papers) == 4
