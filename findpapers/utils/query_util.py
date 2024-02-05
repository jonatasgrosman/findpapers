from typing import Optional, Callable


def replace_search_term_enclosures(query: str, open_replacement: str, close_replacement: str,
                                   only_on_wildcards: Optional[bool] = False) -> str:
    """
    Replace search term enclosures

    Parameters
    ----------
    query : str
        A search query
    open_replacement : str
        An open replacement string
    close_replacement : str
        An open replacement string
    only_on_wildcards : bool, optional
        If the replacement should be only be performed on wildcards terms, by default False

    Returns
    -------
    str
        A transformed query
    """

    if only_on_wildcards:

        def wildcards_apply(search_term):
            if "?" in search_term or "*" in search_term:
                return search_term.replace("[", open_replacement).replace("]", close_replacement)
            else:
                return search_term

        return apply_on_each_term(query, wildcards_apply)

    else:

        return query.replace("[", open_replacement).replace("]", close_replacement)


def apply_on_each_term(query: str, function: Callable) -> str:
    """
    Apply a function to each term of the query

    Parameters
    ----------
    query : str
        A search query
    function : Callable
        A callable function that will be applied to each term of the provided query

    Returns
    -------
    str
        A new query with each term transformed by the provided function
    """

    is_inside_a_term = False
    search_term = ""
    final_query = ""
    for character in query:

        if character == "[":
            search_term += character
            is_inside_a_term = True
            continue

        if is_inside_a_term:
            search_term += character
            if character == "]":
                search_term = function(search_term)
                final_query += search_term
                search_term = ""
                is_inside_a_term = False
        else:
            final_query += character

    return final_query


def get_max_group_level(query: str) -> int:
    """
    Get the max group level of a query

    Parameters
    ----------
    query : str
        A search query

    Returns
    -------
    int
        The max group level of the query
    """

    current_level = 0
    max_level = 0
    for character in query:
        if character == "(":
            current_level += 1
            if current_level > max_level:
                max_level = current_level
        elif character == ")":
            current_level -= 1

    return max_level


def get_query_tree(query: str, parent: dict = None) -> dict:
    """
    Get the tree of a query

    Given the following query: 
    [term A] OR [term B] AND ([term C] OR [term D] OR [term E] OR ([term F] AND [term G] AND NOT [term H])) AND NOT [term I]

    The following tree will be returned:
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

    Parameters
    ----------
    query : str
        A search query
    parent : dict, optional
        The parent node, by default None

    Returns
    -------
    dict
        The query tree
        
    """

    if parent is None:
        parent = {"node_type": "root", "children": []}

    query_iterator = iter(query)
    current_character = next(query_iterator, None)
    current_connector = None

    while current_character is not None:

        if current_character == "(": # is a beginning of a group

            if current_connector is not None:
                parent["children"].append({"node_type": "connector", "value": current_connector.strip()})
                current_connector = None
                
            subquery = ""
            subquery_group_level = 1

            while True:

                current_character = next(query_iterator, None)

                if current_character is None:
                    raise ValueError("Unbalanced parentheses")

                if current_character == "(": # has a nested group
                    subquery_group_level += 1

                elif current_character == ")":
                    subquery_group_level -= 1
                    if subquery_group_level == 0: # end of the group
                        break

                subquery += current_character

            group_node = {"node_type": "group", "children": []}
            parent["children"].append(group_node)

            get_query_tree(subquery, group_node)

        elif current_character == "[": # is a beginning of a term

            if current_connector is not None:
                parent["children"].append({"node_type": "connector", "value": current_connector.strip()})
                current_connector = None

            term_query = ""

            while True:

                current_character = next(query_iterator, None)

                if current_character is None:
                    raise ValueError("Missing term closing bracket")
                
                if current_character == "]":
                    break

                term_query += current_character

            parent["children"].append({"node_type": "term", "value": term_query})

        else: # is a connector

            if current_connector is None:
                current_connector = ""

            current_connector += current_character

        current_character = next(query_iterator, None)

    return parent
