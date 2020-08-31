import os
import json
import findpapers


def test_run():

    os.environ['SCOPUS_API_TOKEN'] = 'api-fake-token'
    os.environ['IEEE_API_TOKEN'] = 'api-fake-token'
    search = findpapers.run('this AND that', limit_per_database=2)

    fetched_papers_count = 0
    for paper in search.papers:
        fetched_papers_count += len(paper.databases)

    assert fetched_papers_count == 10
    