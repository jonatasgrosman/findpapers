import os
import json
import findpapers
import tempfile
import pytest
from findpapers.models.search import Search
from findpapers.models.paper import Paper
import findpapers.tools.search_runner_tool as search_runner_tool


@pytest.mark.skip(reason="It needs some revision after some tool's refactoring")
def test_run():

    os.environ["FINDPAPERS_SCOPUS_API_TOKEN"] = "api-fake-token"
    os.environ["FINDPAPERS_IEEE_API_TOKEN"] = "api-fake-token"
    search = findpapers.run("this AND that", limit_per_database=2)

    fetched_papers_count = 0
    for paper in search.papers:
        fetched_papers_count += len(paper.databases)

    assert fetched_papers_count == 10
    
    
@pytest.mark.skip(reason="It needs some revision after some tool's refactoring")
def test_save_and_load(search: Search, paper: Paper):

    temp_dirpath = tempfile.mkdtemp()
    temp_filepath = os.path.join(temp_dirpath, "output.json")

    search.add_paper(paper)
    
    findpapers.save(search, temp_filepath)

    loaded_search = findpapers.load(temp_filepath)

    assert loaded_search.query == search.query
    assert loaded_search.since == search.since
    assert loaded_search.until == search.until
    assert loaded_search.limit == search.limit
    assert loaded_search.limit_per_database == search.limit_per_database
    assert loaded_search.processed_at.strftime("%Y-%m-%d %H:%M:%S") == search.processed_at.strftime("%Y-%m-%d %H:%M:%S")
    assert len(loaded_search.papers) == len(search.papers)


def test_query_format():

    assert search_runner_tool._is_query_ok("([term a] OR [term b])")
    assert search_runner_tool._is_query_ok("[term a] OR [term b]")
    assert search_runner_tool._is_query_ok("[term a] AND [term b]")
    assert search_runner_tool._is_query_ok("[term a] AND NOT ([term b] OR [term c])")
    assert search_runner_tool._is_query_ok("[term a] OR ([term b] AND ([term c] OR [term d]))")
    assert search_runner_tool._is_query_ok("[term a]")
    assert not search_runner_tool._is_query_ok("[term a] OR ([term b] AND ([term c] OR [term d])")
    assert not search_runner_tool._is_query_ok("[term a] or [term b]")
    assert not search_runner_tool._is_query_ok("[term a] and [term b]")
    assert not search_runner_tool._is_query_ok("[term a] and not [term b]")
    assert not search_runner_tool._is_query_ok("([term a] OR [term b]")
    assert not search_runner_tool._is_query_ok("term a OR [term b]")
    assert not search_runner_tool._is_query_ok("[term a] [term b]")
    assert not search_runner_tool._is_query_ok("[term a] XOR [term b]")
    assert not search_runner_tool._is_query_ok("[term a] OR NOT [term b]")
    assert not search_runner_tool._is_query_ok("[] AND [term b]")
    assert not search_runner_tool._is_query_ok("[ ] AND [term b]")
    assert not search_runner_tool._is_query_ok("[ ]")
    assert not search_runner_tool._is_query_ok("[")


def test_query_sanitize():

    assert search_runner_tool._sanitize_query("[term a]    OR     [term b]") == "[term a] OR [term b]"
    assert search_runner_tool._sanitize_query("[term a]    AND     [term b]") == "[term a] AND [term b]"
    assert search_runner_tool._sanitize_query("([term a]    OR     [term b]) AND [term *]") == "([term a] OR [term b]) AND [term *]"
    assert search_runner_tool._sanitize_query("([term a]\nOR\t[term b]) AND [term *]") == "([term a] OR [term b]) AND [term *]"
    assert search_runner_tool._sanitize_query("([term a]\n\n\n\nOR\n\n\n\n[term b]) AND [term *]") == "([term a] OR [term b]) AND [term *]"