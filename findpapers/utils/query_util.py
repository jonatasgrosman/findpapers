from typing import Optional


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
                    if '?' in search_term or '*' in search_term:
                        search_term = search_term.replace(
                            '[', open_replacement).replace(']', close_replacement)
                    final_query += search_term
                    search_term = ''
                    is_inside_a_term = False
            else:
                final_query += character

        return final_query

    else:

        return query.replace('[', open_replacement).replace(']', close_replacement)
