import pytest
import findpapers.utils.query_util as query_util


@pytest.mark.parametrize("query, tree", [
    ("[term A] OR [term B]", 
    {"node_type": "root", "children" : [
        {"node_type": "term", "value": "term A"}, 
        {"node_type": "connector", "value": "OR"}, 
        {"node_type": "term", "value": "term B"}, 
    ]}
    ),
    ("[term A] AND [term B]", 
    {"node_type": "root", "children" : [
        {"node_type": "term", "value": "term A"}, 
        {"node_type": "connector", "value": "AND"}, 
        {"node_type": "term", "value": "term B"}, 
    ]}
    ),
    ("[term A] AND NOT [term B]", 
    {"node_type": "root", "children" : [
        {"node_type": "term", "value": "term A"}, 
        {"node_type": "connector", "value": "AND NOT"}, 
        {"node_type": "term", "value": "term B"}, 
    ]}
    ),
    ("[term A] AND NOT [term B] OR ([term C] AND [term D])", 
    {"node_type": "root", "children" : [
        {"node_type": "term", "value": "term A"}, 
        {"node_type": "connector", "value": "AND NOT"}, 
        {"node_type": "term", "value": "term B"}, 
        {"node_type": "connector", "value": "OR"}, 
        {"node_type": "group", "children": [
            {"node_type": "term", "value": "term C"},
            {"node_type": "connector", "value": "AND"}, 
            {"node_type": "term", "value": "term D"},
        ]}
    ]}
    ),
    ("[term A] OR [term B] AND ([term C] OR [term D] OR [term E] OR ([term F] AND [term G] AND NOT [term H])) AND NOT [term I]", 
    {"node_type": "root", "children" : [
        {"node_type": "term", "value": "term A"}, 
        {"node_type": "connector", "value": "OR"}, 
        {"node_type": "term", "value": "term B"}, 
        {"node_type": "connector", "value": "AND"}, 
        {"node_type": "group", "children": [
            {"node_type": "term", "value": "term C"},
            {"node_type": "connector", "value": "OR"}, 
            {"node_type": "term", "value": "term D"},
            {"node_type": "connector", "value": "OR"}, 
            {"node_type": "term", "value": "term E"},
            {"node_type": "connector", "value": "OR"}, 
            {"node_type": "group", "children": [
                {"node_type": "term", "value": "term F"},
                {"node_type": "connector", "value": "AND"},
                {"node_type": "term", "value": "term G"},
                {"node_type": "connector", "value": "AND NOT"},
                {"node_type": "term", "value": "term H"},
            ]}
        ]},
        {"node_type": "connector", "value": "AND NOT"},
        {"node_type": "term", "value": "term I"}
    ]}
    ),
])
def test_get_query_tree(query: str, tree: dict):

    query_tree = query_util.get_query_tree(query)

    assert query_tree == tree

@pytest.mark.parametrize("query, max_group_level", [
    ("[term A] OR [term B] OR [term C] OR [term D]", 0),
    ("[term A] OR [term B] AND ([term C] OR [term D])", 1),
    ("[term A] OR [term B] AND ([term C] OR [term D] OR [term E] OR ([term F] AND [term G] AND NOT [term H])) AND NOT [term I]", 2),
    ("[term A] OR [term B] AND ([term C] OR [term D] AND ([term E] OR [term F] OR ([term G] AND [term H]))) AND term I", 3)
])
def test_get_max_group_level(query: str, max_group_level: int):
    
    query_max_group_level = query_util.get_max_group_level(query)

    assert query_max_group_level == max_group_level