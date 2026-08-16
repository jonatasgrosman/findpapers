"""Tests for arXiv query builder."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from findpapers.core.query import Query
from findpapers.query.builders.arxiv import ArxivQueryBuilder


def test_arxiv_hyphen_preprocess(parse_and_propagate: Callable[[str], Query]) -> None:
    """arXiv replaces hyphen by space before conversion."""
    query = parse_and_propagate("[covid-19]")
    builder = ArxivQueryBuilder()
    preprocessed = builder.preprocess_terms(query)
    assert preprocessed.root.children[0].value == "covid 19"


def test_arxiv_conversion_default_filter(parse_and_propagate: Callable[[str], Query]) -> None:
    """arXiv default filter expands to title OR abstract."""
    query = parse_and_propagate("[machine learning]")
    converted = ArxivQueryBuilder().convert_query(query)
    assert 'ti:"machine learning"' in converted
    assert 'abs:"machine learning"' in converted


def test_arxiv_build_execution_plan_single_query(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """Single-query plans expose one payload and identity combination expression."""
    query = parse_and_propagate("[foundation model]")
    plan = ArxivQueryBuilder().build_execution_plan(query)
    assert len(plan.request_payloads) == 1
    assert plan.combination_expression == "q0"


@pytest.mark.parametrize(
    ("query_string", "expected_fragment"),
    [
        ("ti[graph]", "ti:graph"),
        ("abs[graph]", "abs:graph"),
        ("au[smith]", "au:smith"),
        ("tiabs[graph]", "(ti:graph OR abs:graph)"),
    ],
)
def test_arxiv_supports_all_filters_in_conversion(
    parse_and_propagate: Callable[[str], Query],
    query_string: str,
    expected_fragment: str,
) -> None:
    """arXiv conversion supports each documented filter code."""
    query = parse_and_propagate(query_string)
    result = ArxivQueryBuilder().validate_query(query)
    assert result.is_valid is True
    converted = ArxivQueryBuilder().convert_query(query)
    assert expected_fragment in converted


def test_arxiv_compound_query_no_percent_encoding(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """Parentheses in compound queries are NOT pre-encoded as %28/%29.

    Previously the builder called ``.replace("(", "%28")`` on its output.
    When that string was then passed to ``requests.get(params=...)`` the HTTP
    library percent-encoded the ``%`` sign a second time, producing ``%2528``
    in the final URL.  arXiv decoded once back to ``%28`` (literal characters)
    and failed to parse the query as boolean groups, silently returning
    unrelated papers.

    The fix: return the raw expression with literal '(' and ')' characters and
    let the HTTP library perform the single, correct URL-encoding.
    """
    query = parse_and_propagate("[machine learning] AND [healthcare]")
    converted = ArxivQueryBuilder().convert_query(query)
    assert "(" in converted, "parentheses must be present as literal characters"
    assert ")" in converted, "parentheses must be present as literal characters"
    assert "%28" not in converted, "must not pre-encode '(': would cause double-encoding"
    assert "%29" not in converted, "must not pre-encode ')': would cause double-encoding"
    # Confirm the boolean structure is preserved
    assert 'ti:"machine learning"' in converted
    assert 'abs:"machine learning"' in converted
    assert "AND" in converted
    assert "ti:healthcare" in converted
    assert "abs:healthcare" in converted


def test_arxiv_accepts_trailing_star_wildcard(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """arXiv supports '*' wildcard when not in the first character position.

    The global QueryValidator already rejects leading wildcards, so they never
    reach this builder.  Here we confirm the builder itself does not block
    valid trailing wildcards.
    """
    query = parse_and_propagate("[machine*]")
    result = ArxivQueryBuilder().validate_query(query)
    assert result.is_valid is True


def test_arxiv_accepts_mid_question_mark_wildcard(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """arXiv supports '?' wildcard when not in the first character position.

    The global QueryValidator already rejects leading wildcards, so they never
    reach this builder.  Here we confirm the builder itself does not block
    valid mid-word '?' wildcards.
    """
    query = parse_and_propagate("[col?r]")
    result = ArxivQueryBuilder().validate_query(query)
    assert result.is_valid is True
