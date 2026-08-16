"""Tests for OpenAlex query builder."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from findpapers.core.query import ConnectorType, FilterCode, NodeType, Query, QueryNode
from findpapers.query.builders.openalex import OpenAlexQueryBuilder


def _make_query(raw: str, *children: QueryNode) -> Query:
    """Build a Query with the given root children."""
    root = QueryNode(node_type=NodeType.ROOT, children=list(children))
    return Query(raw_query=raw, root=root)


def _term(value: str, filter_code: FilterCode | None = None) -> QueryNode:
    """Build a TERM node."""
    return QueryNode(node_type=NodeType.TERM, value=value, filter_code=filter_code)


def _connector(connector_type: ConnectorType) -> QueryNode:
    """Build a CONNECTOR node."""
    return QueryNode(node_type=NodeType.CONNECTOR, value=connector_type)


def _group(*children: QueryNode) -> QueryNode:
    """Build a GROUP node."""
    return QueryNode(node_type=NodeType.GROUP, children=list(children))


def test_openalex_rejects_wildcards(parse_and_propagate: Callable[[str], Query]) -> None:
    """OpenAlex rejects wildcard terms."""
    query = parse_and_propagate("[gene*]")
    result = OpenAlexQueryBuilder().validate_query(query)
    assert result.is_valid is False


def test_openalex_default_filter_mapping(parse_and_propagate: Callable[[str], Query]) -> None:
    """Unqualified terms default to title_and_abstract search."""
    query = parse_and_propagate("[federated learning]")
    result = OpenAlexQueryBuilder().validate_query(query)
    assert result.is_valid is True
    converted = OpenAlexQueryBuilder().convert_query(query)
    assert "title_and_abstract.search" in converted["filter"]


def test_openalex_or_uses_search_mode(parse_and_propagate: Callable[[str], Query]) -> None:
    """OpenAlex uses boolean search mode for OR expressions."""
    query = parse_and_propagate("[alpha] OR [beta]")
    converted = OpenAlexQueryBuilder().convert_query(query)
    assert "search" in converted
    assert "OR" in converted["search"]


def test_openalex_rejects_tiabskey(parse_and_propagate: Callable[[str], Query]) -> None:
    """OpenAlex rejects tiabskey filter (no keyword search support)."""
    query = parse_and_propagate("tiabskey[cancer]")
    result = OpenAlexQueryBuilder().validate_query(query)
    assert result.is_valid is False


@pytest.mark.parametrize(
    ("query_string", "expected_fragment"),
    [
        ("ti[cancer]", "title.search:cancer"),
        ("abs[cancer]", "abstract.search:cancer"),
        ("au[cancer]", "raw_author_name.search:cancer"),
        ("aff[cancer]", "raw_affiliation_strings.search:cancer"),
        ("tiabs[cancer]", "title_and_abstract.search:cancer"),
    ],
)
def test_openalex_supports_all_filters_in_conversion(
    parse_and_propagate: Callable[[str], Query],
    query_string: str,
    expected_fragment: str,
) -> None:
    """OpenAlex conversion supports each documented filter code."""
    query = parse_and_propagate(query_string)
    result = OpenAlexQueryBuilder().validate_query(query)
    assert result.is_valid is True
    converted = OpenAlexQueryBuilder().convert_query(query)
    assert "filter" in converted
    assert expected_fragment in converted["filter"]


def test_openalex_and_not_uses_search_mode(parse_and_propagate: Callable[[str], Query]) -> None:
    """OpenAlex uses boolean search mode for AND NOT expressions."""
    query = parse_and_propagate("[alpha] AND NOT [beta]")
    converted = OpenAlexQueryBuilder().convert_query(query)
    assert "search" in converted
    assert "NOT" in converted["search"]


def test_openalex_expand_query_or_without_and_not_decomposes(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """OR-only queries are expanded into separate AND-only sub-queries by expand_query."""
    query = parse_and_propagate("[alpha] OR [beta]")
    expanded = OpenAlexQueryBuilder().expand_query(query)
    # Two OR branches -> two sub-queries
    assert len(expanded) >= 2


def test_openalex_expand_query_and_not_stays_single(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """AND NOT queries are not decomposed; they fall back to a single query."""
    query = parse_and_propagate("[alpha] AND NOT [beta]")
    expanded = OpenAlexQueryBuilder().expand_query(query)
    assert len(expanded) == 1


def test_openalex_boolean_search_with_group_node() -> None:
    """_to_openalex_boolean_search wraps GROUP nodes in parentheses."""
    builder = OpenAlexQueryBuilder()
    # Build: root -> group(a AND b) OR c
    a = _term("a")
    b = _term("b")
    group = _group(a, _connector(ConnectorType.AND), b)
    c = _term("c")
    root = QueryNode(
        node_type=NodeType.ROOT,
        children=[group, _connector(ConnectorType.OR), c],
    )
    result = builder._to_openalex_boolean_search(root)
    assert "(" in result
    assert ")" in result
    assert "OR" in result
    assert "c" in result


def test_openalex_rejects_unsupported_filter() -> None:
    """OpenAlex rejects a term with an unsupported filter code via direct injection."""
    unsupported = FilterCode.TITLE  # supported: confirm via double check
    assert OpenAlexQueryBuilder().supports_filter(unsupported) is True

    # SOURCE is not supported by OpenAlex (no text search for source names)
    assert OpenAlexQueryBuilder().supports_filter(FilterCode.SOURCE) is False

    # KEYWORDS is not supported (keyword.search returns 0 results)
    assert OpenAlexQueryBuilder().supports_filter(FilterCode.KEYWORDS) is False

    # TITLE_ABSTRACT_KEYWORDS is not supported (no keyword search)
    assert OpenAlexQueryBuilder().supports_filter(FilterCode.TITLE_ABSTRACT_KEYWORDS) is False


def test_openalex_dnf_and_not_fallback() -> None:
    """_to_dnf_with_filters falls back to flat list for AND NOT connectors."""
    builder = OpenAlexQueryBuilder()
    # Build: root with a AND NOT b  (no parse_and_propagate to bypass validator)
    a = _term("a", FilterCode.TITLE)
    b = _term("b", FilterCode.ABSTRACT)
    root = QueryNode(
        node_type=NodeType.ROOT,
        children=[a, _connector(ConnectorType.AND_NOT), b],
    )
    clauses = builder._to_dnf_with_filters(root)
    # Should return exactly one clause with both terms
    assert len(clauses) == 1
    assert len(clauses[0]) == 2


def test_openalex_dnf_and_cartesian_product() -> None:
    """_to_dnf_with_filters applies cartesian product for AND over OR sub-trees."""
    builder = OpenAlexQueryBuilder()
    # (a OR b) AND (c OR d) should produce 4 clauses
    a = _term("a")
    b = _term("b")
    c = _term("c")
    d = _term("d")
    # Build group1 = (a OR b), group2 = (c OR d) connected by AND
    group1 = _group(a, _connector(ConnectorType.OR), b)
    group2 = _group(c, _connector(ConnectorType.OR), d)
    root = QueryNode(
        node_type=NodeType.ROOT,
        children=[group1, _connector(ConnectorType.AND), group2],
    )
    clauses = builder._to_dnf_with_filters(root)
    assert len(clauses) == 4


def test_openalex_dnf_empty_operands() -> None:
    """_to_dnf_with_filters returns [[]] for a root node with no operand children."""
    builder = OpenAlexQueryBuilder()
    # A root node with only a connector (no actual terms/groups)
    root = QueryNode(
        node_type=NodeType.ROOT,
        children=[_connector(ConnectorType.AND)],
    )
    clauses = builder._to_dnf_with_filters(root)
    assert clauses == [[]]


def test_openalex_multi_term_with_phrase(parse_and_propagate: Callable[[str], Query]) -> None:
    """Filter fragments for multi-word terms are quoted."""
    query = parse_and_propagate("ti[neural networks]")
    converted = OpenAlexQueryBuilder().convert_query(query)
    assert 'title.search:"neural networks"' in converted["filter"]


def test_openalex_rejects_tilde_wildcard(parse_and_propagate: Callable[[str], Query]) -> None:
    """OpenAlex rejects queries with '~' in a term."""

    # Bypass the global validator by building the query directly
    query = _make_query("[fuzz~2]", _term("fuzz~2"))
    result = OpenAlexQueryBuilder().validate_query(query)
    assert result.is_valid is False
