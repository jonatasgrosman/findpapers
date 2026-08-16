"""Unit tests for the WoS (Web of Science) query builder."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from findpapers.core.query import Query
from findpapers.query.builders.wos import WosQueryBuilder


def test_wos_default_filter_is_ts(parse_and_propagate: Callable[[str], Query]) -> None:
    """WoS default filter (no explicit code) maps to TS (Topic)."""
    query = parse_and_propagate("[heart attack]")
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is True
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TS=(heart attack)"


def test_wos_title_filter(parse_and_propagate: Callable[[str], Query]) -> None:
    """ti filter maps to TI."""
    query = parse_and_propagate("ti[transformer]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TI=(transformer)"


def test_wos_author_filter(parse_and_propagate: Callable[[str], Query]) -> None:
    """au filter maps to AU."""
    query = parse_and_propagate("au[Einstein]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "AU=(Einstein)"


def test_wos_source_filter(parse_and_propagate: Callable[[str], Query]) -> None:
    """src filter maps to SO."""
    query = parse_and_propagate("src[Nature]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "SO=(Nature)"


def test_wos_affiliation_filter(parse_and_propagate: Callable[[str], Query]) -> None:
    """aff filter maps to OG."""
    query = parse_and_propagate("aff[MIT]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "OG=(MIT)"


def test_wos_tiabskey_filter(parse_and_propagate: Callable[[str], Query]) -> None:
    """tiabskey filter maps to TS (the native WoS Topic field)."""
    query = parse_and_propagate("tiabskey[bert]")
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is True
    assert WosQueryBuilder().convert_query(query) == "TS=(bert)"


@pytest.mark.parametrize(
    ("query_string", "expected"),
    [
        ("ti[deep learning]", "TI=(deep learning)"),
        ("au[LeCun]", "AU=(LeCun)"),
        ("src[CVPR]", "SO=(CVPR)"),
        ("aff[Google]", "OG=(Google)"),
        ("tiabskey[bert]", "TS=(bert)"),
    ],
)
def test_wos_supports_all_filter_codes(
    parse_and_propagate: Callable[[str], Query],
    query_string: str,
    expected: str,
) -> None:
    """WoS conversion supports each documented filter code."""
    query = parse_and_propagate(query_string)
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is True
    assert WosQueryBuilder().convert_query(query) == expected


@pytest.mark.parametrize(
    "query_string",
    [
        "abs[attention mechanism]",
        "key[transformer]",
        "tiabs[deep learning]",
    ],
)
def test_wos_rejects_unsupported_filters(
    parse_and_propagate: Callable[[str], Query],
    query_string: str,
) -> None:
    """WoS rejects abs, key, and tiabs filters: they have no equivalent field tag."""
    query = parse_and_propagate(query_string)
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is False


def test_wos_boolean_and(parse_and_propagate: Callable[[str], Query]) -> None:
    """AND operator is preserved."""
    query = parse_and_propagate("[machine learning] AND [deep learning]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TS=(machine learning) AND TS=(deep learning)"


def test_wos_boolean_or(parse_and_propagate: Callable[[str], Query]) -> None:
    """OR operator is preserved."""
    query = parse_and_propagate("[neural network] OR [deep learning]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TS=(neural network) OR TS=(deep learning)"


def test_wos_boolean_not(parse_and_propagate: Callable[[str], Query]) -> None:
    """AND NOT operator maps to NOT."""
    query = parse_and_propagate("[neural network] AND NOT [shallow]")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TS=(neural network) NOT TS=(shallow)"


def test_wos_wildcards_preserved(parse_and_propagate: Callable[[str], Query]) -> None:
    """Wildcards * and ? are passed through unchanged."""
    query = parse_and_propagate("[oxid*]")
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is True
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TS=(oxid*)"


def test_wos_question_wildcard_preserved(parse_and_propagate: Callable[[str], Query]) -> None:
    """? wildcard is also passed through unchanged."""
    query = parse_and_propagate("[wom?n]")
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is True
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TS=(wom?n)"


def test_wos_rejects_short_prefix_before_wildcard(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """WoS rejects wildcards with fewer than 3 characters before them."""
    query = parse_and_propagate("[ox*]")
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is False
    assert result.error_message is not None
    assert "3 characters" in result.error_message


def test_wos_accepts_three_char_prefix(parse_and_propagate: Callable[[str], Query]) -> None:
    """Exactly 3 characters before wildcard is valid."""
    query = parse_and_propagate("[oxo*]")
    result = WosQueryBuilder().validate_query(query)
    assert result.is_valid is True


def test_wos_group_filter_optimization(parse_and_propagate: Callable[[str], Query]) -> None:
    """WoS wraps group with field tag when all children share the same filter."""
    query = parse_and_propagate("ti([machine learning] OR [deep learning])")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "TI=(machine learning OR deep learning)"


def test_wos_mixed_filter_group_no_optimization(
    parse_and_propagate: Callable[[str], Query],
) -> None:
    """WoS falls back to per-term when children use different filters."""
    query = parse_and_propagate("ti([deep learning] OR tiabskey[attention])")
    converted = WosQueryBuilder().convert_query(query)
    assert converted == "(TI=(deep learning) OR TS=(attention))"


def test_wos_complex_query(parse_and_propagate: Callable[[str], Query]) -> None:
    """Complex query with multiple filters and operators converts correctly."""
    query = parse_and_propagate(
        "ti[federated learning] AND (tiabskey[privacy] OR tiabskey[security]) AND NOT src[arXiv]"
    )
    converted = WosQueryBuilder().convert_query(query)
    assert "TI=(federated learning)" in converted
    assert "TS=(privacy)" in converted
    assert "TS=(security)" in converted
    assert "SO=(arXiv)" in converted
    assert "AND" in converted
    assert "NOT" in converted
