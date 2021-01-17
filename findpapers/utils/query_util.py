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
            if '?' in search_term or '*' in search_term:
                return search_term.replace('[', open_replacement).replace(']', close_replacement)
            else:
                return search_term

        return apply_on_each_term(query, wildcards_apply)

    else:

        return query.replace('[', open_replacement).replace(']', close_replacement)


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
    search_term = ''
    final_query = ''
    for character in query:

        if character == '[':
            search_term += character
            is_inside_a_term = True
            continue

        if is_inside_a_term:
            search_term += character
            if character == ']':
                search_term = function(search_term)
                final_query += search_term
                search_term = ''
                is_inside_a_term = False
        else:
            final_query += character

    return final_query