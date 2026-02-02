"""Tests for Query model and query parsing."""

import pytest

from findpapers.models import Query, QueryNode, QueryValidationError
from findpapers.models.query import ConnectorType, NodeType


class TestQueryValidCases:
    """Test valid query strings are parsed correctly."""

    def test_simple_term(self):
        """A single term should be parsed correctly."""
        query = Query("[term a]")
        assert query.raw_query == "[term a]"
        assert len(query.root.children) == 1
        assert query.root.children[0].node_type == NodeType.TERM
        assert query.root.children[0].value == "term a"

    def test_two_terms_with_or(self):
        """Two terms with OR should be parsed correctly."""
        query = Query("[term a] OR [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[0].value == "term a"
        assert query.root.children[1].node_type == NodeType.CONNECTOR
        assert query.root.children[1].value == "OR"
        assert query.root.children[2].value == "term b"

    def test_two_terms_with_and(self):
        """Two terms with AND should be parsed correctly."""
        query = Query("[term a] AND [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[0].value == "term a"
        assert query.root.children[1].value == "AND"
        assert query.root.children[2].value == "term b"

    def test_and_not_operator(self):
        """AND NOT should be parsed as a single connector."""
        query = Query("[term a] AND NOT [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[0].value == "term a"
        assert query.root.children[1].node_type == NodeType.CONNECTOR
        assert query.root.children[1].value == "AND NOT"
        assert query.root.children[2].value == "term b"

    def test_grouped_query(self):
        """Parentheses should create GROUP nodes."""
        query = Query("([term a] OR [term b])")
        assert len(query.root.children) == 1
        assert query.root.children[0].node_type == NodeType.GROUP
        group = query.root.children[0]
        assert len(group.children) == 3
        assert group.children[0].value == "term a"
        assert group.children[1].value == "OR"
        assert group.children[2].value == "term b"

    def test_nested_groups(self):
        """Nested parentheses should create nested GROUP nodes."""
        query = Query("[a] AND ([b] OR ([c] AND [d]))")
        assert len(query.root.children) == 3  # term, connector, group
        assert query.root.children[0].value == "a"
        assert query.root.children[1].value == "AND"

        outer_group = query.root.children[2]
        assert outer_group.node_type == NodeType.GROUP
        # [b] OR ([c] AND [d])
        assert len(outer_group.children) == 3
        assert outer_group.children[0].value == "b"
        assert outer_group.children[1].value == "OR"

        inner_group = outer_group.children[2]
        assert inner_group.node_type == NodeType.GROUP
        assert len(inner_group.children) == 3
        assert inner_group.children[0].value == "c"
        assert inner_group.children[1].value == "AND"
        assert inner_group.children[2].value == "d"

    def test_complex_query_from_readme(self):
        """Complex query from README should parse correctly."""
        query = Query("[happiness] AND ([joy] OR [peace of mind]) AND NOT [stressful]")
        assert len(query.root.children) == 5  # term, AND, group, AND NOT, term
        assert query.root.children[0].value == "happiness"
        assert query.root.children[1].value == "AND"
        assert query.root.children[2].node_type == NodeType.GROUP
        assert query.root.children[3].value == "AND NOT"
        assert query.root.children[4].value == "stressful"

    def test_lowercase_and_operator(self):
        """Lowercase 'and' should be accepted and normalized to uppercase."""
        query = Query("[term a] and [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[1].value == "AND"

    def test_lowercase_or_operator(self):
        """Lowercase 'or' should be accepted and normalized to uppercase."""
        query = Query("[term a] or [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[1].value == "OR"

    def test_lowercase_and_not_operator(self):
        """Lowercase 'and not' should be accepted and normalized to uppercase."""
        query = Query("[term a] and not [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[1].value == "AND NOT"

    def test_mixed_case_operators(self):
        """Mixed case operators should be accepted and normalized."""
        query = Query("[a] And [b] Or [c]")
        assert query.root.children[1].value == "AND"
        assert query.root.children[3].value == "OR"

    def test_term_with_question_mark_wildcard(self):
        """Question mark wildcard in valid position should be accepted."""
        query = Query("[son?]")
        assert query.root.children[0].value == "son?"

    def test_term_with_asterisk_wildcard(self):
        """Asterisk wildcard in valid position should be accepted."""
        query = Query("[son*]")
        assert query.root.children[0].value == "son*"

    def test_longer_term_with_asterisk(self):
        """Longer terms with asterisk should be valid."""
        query = Query("[sonic*]")
        assert query.root.children[0].value == "sonic*"

    def test_wildcard_in_grouped_query(self):
        """Wildcards should work in grouped queries."""
        query = Query("[term a] OR ([term b] AND ([term*] OR [t?rm]))")
        terms = query.get_all_terms()
        assert "term*" in terms
        assert "t?rm" in terms

    def test_whitespace_variations(self):
        """Various whitespace should be accepted."""
        query = Query("[term a]  AND  [term b]")
        assert len(query.root.children) == 3
        assert query.root.children[1].value == "AND"

    def test_newline_as_whitespace(self):
        """Newlines should be valid whitespace."""
        query = Query("[term a]\nAND\n[term b]")
        assert len(query.root.children) == 3

    def test_tab_as_whitespace(self):
        """Tabs should be valid whitespace."""
        query = Query("[term a]\tOR\t[term b]")
        assert len(query.root.children) == 3


class TestQueryGetAllTerms:
    """Test the get_all_terms method."""

    def test_simple_term(self):
        """Single term should return single item list."""
        query = Query("[happiness]")
        assert query.get_all_terms() == ["happiness"]

    def test_multiple_terms(self):
        """Multiple terms should all be returned."""
        query = Query("[a] AND [b] OR [c]")
        terms = query.get_all_terms()
        assert "a" in terms
        assert "b" in terms
        assert "c" in terms

    def test_terms_from_groups(self):
        """Terms inside groups should be extracted."""
        query = Query("[a] AND ([b] OR ([c] AND [d]))")
        terms = query.get_all_terms()
        assert set(terms) == {"a", "b", "c", "d"}


class TestQuerySerializationDict:
    """Test Query serialization to/from dict."""

    def test_to_dict_simple(self):
        """to_dict should return valid dict structure."""
        query = Query("[term]")
        data = query.to_dict()
        assert data["raw_query"] == "[term]"
        assert "tree" in data
        assert data["tree"]["node_type"] == "root"

    def test_from_dict_roundtrip(self):
        """from_dict should reconstruct the Query."""
        original = Query("[a] AND [b]")
        data = original.to_dict()
        reconstructed = Query.from_dict(data)
        assert reconstructed.raw_query == original.raw_query
        assert len(reconstructed.root.children) == 3


class TestQueryInvalidCases:
    """Test that invalid queries raise QueryValidationError."""

    def test_empty_query(self):
        """Empty query should raise error."""
        with pytest.raises(QueryValidationError, match="cannot be empty"):
            Query("")

    def test_whitespace_only_query(self):
        """Whitespace-only query should raise error."""
        with pytest.raises(QueryValidationError, match="cannot be empty"):
            Query("   ")

    def test_empty_term(self):
        """Empty term [] should raise error."""
        with pytest.raises(QueryValidationError, match="empty"):
            Query("[] AND [term b]")

    def test_unbalanced_brackets_open(self):
        """Missing closing bracket should raise error."""
        with pytest.raises(QueryValidationError, match="bracket"):
            Query("[term a")

    def test_unbalanced_brackets_close(self):
        """Extra closing bracket should raise error."""
        with pytest.raises(QueryValidationError, match="bracket"):
            Query("term a]")

    def test_unbalanced_parentheses_open(self):
        """Missing closing parenthesis should raise error."""
        with pytest.raises(QueryValidationError, match="parentheses"):
            Query("([term a] OR [term b]")

    def test_unbalanced_parentheses_close(self):
        """Extra closing parenthesis should raise error."""
        with pytest.raises(QueryValidationError, match="parentheses"):
            Query("[term a] OR [term b])")

    def test_consecutive_terms_without_operator(self):
        """Terms without operator between them should raise error."""
        with pytest.raises(QueryValidationError, match="separated by boolean operators"):
            Query("[term a] [term b]")

    def test_consecutive_terms_whitespace(self):
        """Terms with only whitespace between should raise error."""
        with pytest.raises(QueryValidationError, match="separated by boolean operators"):
            Query("[term a]   [term b]")

    def test_not_without_and(self):
        """NOT without preceding AND should raise error."""
        with pytest.raises(QueryValidationError, match="preceded by AND"):
            Query("NOT [term a]")

    def test_or_not_invalid(self):
        """OR NOT should raise error (must be AND NOT)."""
        with pytest.raises(QueryValidationError, match="preceded by AND"):
            Query("[term a] OR NOT [term b]")

    def test_missing_term_brackets(self):
        """Term without brackets cannot be part of a valid query."""
        # A term without brackets at the beginning should fail
        with pytest.raises(QueryValidationError):
            Query("term a OR [term b]")

    def test_invalid_operator_xor(self):
        """XOR is not a valid operator."""
        with pytest.raises(QueryValidationError, match="Invalid boolean operator"):
            Query("[term a] XOR [term b]")

    def test_no_whitespace_before_operator(self):
        """Operator without whitespace before should raise error."""
        with pytest.raises(QueryValidationError, match="whitespace"):
            Query("[term a]OR[term b]")

    def test_connector_at_beginning(self):
        """Connector at the beginning should raise error."""
        with pytest.raises(QueryValidationError, match="beginning"):
            Query("AND [term a]")

    def test_connector_at_end(self):
        """Connector at the end should raise error."""
        with pytest.raises(QueryValidationError, match="end"):
            Query("[term a] AND")

    def test_connector_or_at_end(self):
        """OR connector at the end should raise error."""
        with pytest.raises(QueryValidationError, match="end"):
            Query("[term a] OR")

    def test_connector_and_not_at_end(self):
        """AND NOT connector at the end should raise error."""
        with pytest.raises(QueryValidationError, match="end"):
            Query("[term a] AND NOT")

    def test_consecutive_connectors(self):
        """Consecutive connectors should raise error."""
        with pytest.raises(QueryValidationError, match="consecutive"):
            Query("[term a] AND OR [term b]")


class TestQueryWildcardValidation:
    """Test wildcard validation rules."""

    def test_wildcard_at_start_question(self):
        """Question mark at start should raise error."""
        with pytest.raises(QueryValidationError, match="start of a search term"):
            Query("[?erm]")

    def test_wildcard_at_start_asterisk(self):
        """Asterisk at start should raise error."""
        with pytest.raises(QueryValidationError, match="start of a search term"):
            Query("[*erm]")

    def test_term_with_double_quotes(self):
        """Terms with double quotes should raise error."""
        with pytest.raises(QueryValidationError, match="double quotes"):
            Query('[term "quoted"]')

    def test_asterisk_not_at_end(self):
        """Asterisk not at end should raise error."""
        with pytest.raises(QueryValidationError, match="only be used at the end"):
            Query("[ter*s]")

    def test_asterisk_less_than_3_chars_before(self):
        """Less than 3 chars before asterisk should raise error."""
        with pytest.raises(QueryValidationError, match="minimum of 3 characters"):
            Query("[te*]")

    def test_asterisk_exactly_2_chars_before(self):
        """Exactly 2 chars before asterisk should raise error."""
        with pytest.raises(QueryValidationError, match="minimum of 3 characters"):
            Query("[ab*]")

    def test_asterisk_exactly_3_chars_before_valid(self):
        """Exactly 3 chars before asterisk should be valid."""
        query = Query("[abc*]")
        assert query.root.children[0].value == "abc*"

    def test_multiple_wildcards(self):
        """Multiple wildcards in one term should raise error."""
        with pytest.raises(QueryValidationError, match="Only one wildcard"):
            Query("[t?rm?]")

    def test_asterisk_and_question(self):
        """Both asterisk and question mark should raise error."""
        with pytest.raises(QueryValidationError, match="Only one wildcard"):
            Query("[ter?*]")

    def test_wildcard_in_multi_word_term(self):
        """Wildcard in term with spaces should raise error."""
        with pytest.raises(QueryValidationError, match="single terms"):
            Query("[some term*]")


class TestQueryNode:
    """Test QueryNode class."""

    def test_node_to_dict_term(self):
        """TERM node to_dict should include value."""
        node = QueryNode(node_type=NodeType.TERM, value="test")
        data = node.to_dict()
        assert data["node_type"] == "term"
        assert data["value"] == "test"
        assert "children" not in data

    def test_node_to_dict_group(self):
        """GROUP node to_dict should include children."""
        child = QueryNode(node_type=NodeType.TERM, value="test")
        node = QueryNode(node_type=NodeType.GROUP, children=[child])
        data = node.to_dict()
        assert data["node_type"] == "group"
        assert len(data["children"]) == 1
        assert data["children"][0]["value"] == "test"

    def test_node_from_dict(self):
        """from_dict should reconstruct node correctly."""
        data = {
            "node_type": "root",
            "children": [
                {"node_type": "term", "value": "test"},
            ],
        }
        node = QueryNode.from_dict(data)
        assert node.node_type == NodeType.ROOT
        assert len(node.children) == 1
        assert node.children[0].value == "test"

    def test_get_all_terms_recursive(self):
        """get_all_terms should work recursively."""
        inner = QueryNode(node_type=NodeType.TERM, value="inner")
        group = QueryNode(node_type=NodeType.GROUP, children=[inner])
        outer = QueryNode(node_type=NodeType.TERM, value="outer")
        root = QueryNode(node_type=NodeType.ROOT, children=[outer, group])

        terms = root.get_all_terms()
        assert set(terms) == {"inner", "outer"}


class TestQueryRepr:
    """Test Query string representation."""

    def test_repr(self):
        """repr should show the raw query."""
        query = Query("[test]")
        assert repr(query) == "Query('[test]')"


class TestQueryEquality:
    """Test Query equality comparison."""

    def test_equal_queries(self):
        """Queries with same raw string should be equal."""
        q1 = Query("[test]")
        q2 = Query("[test]")
        assert q1 == q2

    def test_different_queries(self):
        """Queries with different raw strings should not be equal."""
        q1 = Query("[test a]")
        q2 = Query("[test b]")
        assert q1 != q2

    def test_equality_with_non_query(self):
        """Comparing with non-Query should return NotImplemented."""
        query = Query("[test]")
        assert query.__eq__("not a query") == NotImplemented


class TestConnectorType:
    """Test ConnectorType enum."""

    def test_connector_values(self):
        """ConnectorType values should match expected strings."""
        assert ConnectorType.AND.value == "AND"
        assert ConnectorType.OR.value == "OR"
        assert ConnectorType.AND_NOT.value == "AND NOT"


class TestNodeType:
    """Test NodeType enum."""

    def test_node_type_values(self):
        """NodeType values should match expected strings."""
        assert NodeType.ROOT.value == "root"
        assert NodeType.TERM.value == "term"
        assert NodeType.CONNECTOR.value == "connector"
        assert NodeType.GROUP.value == "group"


class TestQueryEdgeCases:
    """Test edge cases and special scenarios."""

    def test_deeply_nested_groups(self):
        """Deeply nested groups should be parsed correctly."""
        query = Query("[a] AND (([b] OR [c]) AND ([d] OR [e]))")
        assert query.root.children[0].value == "a"
        assert query.root.children[2].node_type == NodeType.GROUP

    def test_term_with_special_characters(self):
        """Terms with special characters should be preserved."""
        query = Query("[term-with-dashes]")
        assert query.root.children[0].value == "term-with-dashes"

    def test_term_with_numbers(self):
        """Terms with numbers should be preserved."""
        query = Query("[covid-19]")
        assert query.root.children[0].value == "covid-19"

    def test_multiple_spaces_in_term(self):
        """Multiple spaces in term should be preserved."""
        query = Query("[term  with  spaces]")
        assert query.root.children[0].value == "term  with  spaces"

    def test_long_query(self):
        """Long query with many terms should parse correctly."""
        terms = " OR ".join(f"[term{i}]" for i in range(10))
        query = Query(terms)
        all_terms = query.get_all_terms()
        assert len(all_terms) == 10
