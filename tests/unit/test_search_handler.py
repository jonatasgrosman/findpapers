import os
import json
import findpapers
import tempfile
from findpapers.models.search import Search
from findpapers.models.paper import Paper


def test_run():

    os.environ['FINDPAPERS_SCOPUS_API_TOKEN'] = 'api-fake-token'
    os.environ['FINDPAPERS_IEEE_API_TOKEN'] = 'api-fake-token'
    search = findpapers.run('this AND that', limit_per_database=2)

    fetched_papers_count = 0
    for paper in search.papers:
        fetched_papers_count += len(paper.databases)

    assert fetched_papers_count == 10
    

def test_save_and_load(search: Search, paper: Paper):

    temp_dirpath = tempfile.mkdtemp()
    temp_filepath = os.path.join(temp_dirpath, 'output.json')

    search.add_paper(paper)
    
    findpapers.save(search, temp_filepath)

    loaded_search = findpapers.load(temp_filepath)

    assert loaded_search.query == search.query
    assert loaded_search.since == search.since
    assert loaded_search.until == search.until
    assert loaded_search.limit == search.limit
    assert loaded_search.limit_per_database == search.limit_per_database
    assert loaded_search.processed_at.strftime('%Y-%m-%d %H:%M:%S') == search.processed_at.strftime('%Y-%m-%d %H:%M:%S')
    assert len(loaded_search.papers) == len(search.papers)
