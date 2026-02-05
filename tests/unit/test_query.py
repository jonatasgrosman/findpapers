"""Tests for Query model and query parsing."""

import pytest

from findpapers.models import Query, QueryNode, QueryValidationError
from findpapers.models.query import VALID_FIELD_CODES, ConnectorType, NodeType


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


class TestQueryFieldSpecifiers:
    """Test field specifier parsing and propagation."""

    def test_single_field_on_term(self):
        """Single field specifier on term should be parsed."""
        query = Query("ti[machine learning]")
        term_node = query.root.children[0]
        assert term_node.field == "ti"

    def test_combined_field_tiabs(self):
        """Combined field tiabs should be parsed."""
        query = Query("tiabs[neural networks]")
        term_node = query.root.children[0]
        assert term_node.field == "tiabs"

    def test_combined_field_tiabskey(self):
        """Combined field tiabskey should be parsed."""
        query = Query("tiabskey[deep learning]")
        term_node = query.root.children[0]
        assert term_node.field == "tiabskey"

    def test_field_on_group(self):
        """Field on group should propagate to child terms."""
        query = Query("abs([a] OR [b])")
        group_node = query.root.children[0]
        # After propagation, group field should be None
        assert group_node.field is None
        # But children should have inherited the field
        term_a = group_node.children[0]
        term_b = group_node.children[2]
        assert term_a.field == "abs"
        assert term_b.field == "abs"

    def test_nested_field_override(self):
        """Inner field should override outer field."""
        query = Query("abs(ti[a] OR [b])")
        group_node = query.root.children[0]
        term_a = group_node.children[0]
        term_b = group_node.children[2]
        # First term has explicit ti, should override abs
        assert term_a.field == "ti"
        # Second term inherits abs from group
        assert term_b.field == "abs"

    def test_deeply_nested_field_propagation(self):
        """Deeply nested groups should propagate fields correctly."""
        query = Query("ti(abs([a] OR [b]))")
        outer_group = query.root.children[0]
        inner_group = outer_group.children[0]
        term_a = inner_group.children[0]
        term_b = inner_group.children[2]
        # Inner group has abs, which overrides outer ti
        assert term_a.field == "abs"
        assert term_b.field == "abs"

    def test_term_without_field_defaults_to_none(self):
        """Terms without field specifiers should have None (default applied later)."""
        query = Query("[term]")
        term_node = query.root.children[0]
        assert term_node.field is None

    def test_mixed_fields_in_query(self):
        """Query with mixed field specifiers should parse correctly."""
        query = Query("ti[a] AND abs[b] OR key[c]")
        assert query.root.children[0].field == "ti"
        assert query.root.children[2].field == "abs"
        assert query.root.children[4].field == "key"

    def test_all_valid_field_codes(self):
        """All valid field codes should be accepted."""
        for field_code in VALID_FIELD_CODES:
            query = Query(f"{field_code}[test]")
            assert query.root.children[0].field == field_code

    def test_get_all_fields(self):
        """get_all_fields should return all unique fields from query."""
        query = Query("ti[a] AND abs[b] OR ti[c]")
        fields = query.get_all_fields()
        assert set(fields) == {"ti", "abs"}

    def test_get_all_fields_from_groups(self):
        """get_all_fields should extract fields from groups."""
        query = Query("ti([a] OR [b]) AND key[c]")
        fields = query.get_all_fields()
        assert set(fields) == {"ti", "key"}

    def test_field_in_serialization(self):
        """Fields should be preserved in to_dict/from_dict."""
        original = Query("tiabs[machine learning]")
        data = original.to_dict()
        reconstructed = Query.from_dict(data)
        assert reconstructed.root.children[0].field == "tiabs"


class TestQueryFieldValidation:
    """Test field specifier validation."""

    def test_invalid_field_code(self):
        """Invalid field code should raise error."""
        with pytest.raises(QueryValidationError, match="Invalid field code"):
            Query("invalid[test]")

    def test_field_codes_are_case_insensitive(self):
        """Field codes are case-insensitive and normalized to lowercase."""
        query = Query("TI[test]")
        # Should be normalized to lowercase
        assert query.root.children[0].field == "ti"

    def test_field_codes_mixed_case(self):
        """Mixed case field codes should be normalized to lowercase."""
        query = Query("TiAbS[test]")
        assert query.root.children[0].field == "tiabs"

    def test_invalid_field_code_case_insensitive(self):
        """Invalid field codes should be rejected regardless of case."""
        with pytest.raises(QueryValidationError, match="Invalid field code"):
            Query("INVALID[test]")

    def test_field_on_empty_term(self):
        """Field on empty term should still raise empty term error."""
        with pytest.raises(QueryValidationError, match="empty"):
            Query("ti[]")

    def test_field_with_wildcard(self):
        """Fields should work with wildcards."""
        query = Query("ti[mach*]")
        assert query.root.children[0].field == "ti"
        assert query.root.children[0].value == "mach*"

    def test_field_with_operators(self):
        """Fields should work with all operators."""
        query = Query("ti[a] AND abs[b] OR key[c] AND NOT au[d]")
        assert query.root.children[0].field == "ti"
        assert query.root.children[2].field == "abs"
        assert query.root.children[4].field == "key"
        assert query.root.children[6].field == "au"


class TestQueryNodeMethods:
    """Test QueryNode new methods."""

    def test_get_all_fields_empty(self):
        """get_all_fields on node without field should return empty list."""
        node = QueryNode(node_type=NodeType.TERM, value="test")
        assert node.get_all_fields() == []

    def test_get_all_fields_with_children(self):
        """get_all_fields should collect from children."""
        child1 = QueryNode(node_type=NodeType.TERM, value="a", field="ti")
        child2 = QueryNode(node_type=NodeType.TERM, value="b", field="abs")
        parent = QueryNode(node_type=NodeType.GROUP, children=[child1, child2])
        fields = parent.get_all_fields()
        assert set(fields) == {"ti", "abs"}

    def test_propagate_fields_with_override(self):
        """propagate_fields should respect explicit field."""
        child1 = QueryNode(node_type=NodeType.TERM, value="a", field="ti")
        child2 = QueryNode(node_type=NodeType.TERM, value="b")
        group = QueryNode(node_type=NodeType.GROUP, children=[child1, child2], field="abs")

        group.propagate_fields()

        # child1 has explicit ti, should keep it
        assert child1.field == "ti"
        # child2 inherits from group
        assert child2.field == "abs"
        # Group should have field cleared after propagation
        assert group.field is None
