"""Unit tests for QueryBuilder static/instance helper methods."""

from __future__ import annotations

from findpapers.core.query import ConnectorType, FilterCode, NodeType, Query, QueryNode
from findpapers.query.builder import QueryBuilder, QueryValidationResult

# ---------------------------------------------------------------------------
# Minimal concrete builders used only in these unit tests
# ---------------------------------------------------------------------------


class _NoKeywordsBuilder(QueryBuilder):
    """Builder that does not support tiabskey: used in unit tests only."""

    _SUPPORTED_FILTERS = frozenset({FilterCode.TITLE_ABSTRACT})

    def validate_query(self, query: Query) -> QueryValidationResult:
        return QueryValidationResult(is_valid=True)

    def convert_query(self, query: Query) -> str:
        return ""


class _KeywordsBuilder(QueryBuilder):
    """Builder that supports tiabskey: used in unit tests only."""

    _SUPPORTED_FILTERS = frozenset({FilterCode.TITLE_ABSTRACT, FilterCode.TITLE_ABSTRACT_KEYWORDS})

    def validate_query(self, query: Query) -> QueryValidationResult:
        return QueryValidationResult(is_valid=True)

    def convert_query(self, query: Query) -> str:
        return ""


# ---------------------------------------------------------------------------
# get_effective_filter
# ---------------------------------------------------------------------------


class TestGetEffectiveFilter:
    """Tests for QueryBuilder.get_effective_filter()."""

    def test_explicit_filter_takes_priority(self) -> None:
        """When filter_code is set, it wins over inherited and default."""
        node = QueryNode(
            node_type=NodeType.TERM,
            value="test",
            filter_code=FilterCode.TITLE,
            inherited_filter_code=FilterCode.ABSTRACT,
        )
        assert _NoKeywordsBuilder().get_effective_filter(node) == FilterCode.TITLE

    def test_inherited_filter_used_when_no_explicit(self) -> None:
        """When no explicit filter_code, inherited_filter_code is used."""
        node = QueryNode(
            node_type=NodeType.TERM,
            value="test",
            inherited_filter_code=FilterCode.KEYWORDS,
        )
        assert _NoKeywordsBuilder().get_effective_filter(node) == FilterCode.KEYWORDS

    def test_default_filter_when_none_set_no_keywords(self) -> None:
        """Builder without tiabskey support defaults to TITLE_ABSTRACT."""
        node = QueryNode(node_type=NodeType.TERM, value="test")
        assert _NoKeywordsBuilder().get_effective_filter(node) == FilterCode.TITLE_ABSTRACT

    def test_default_filter_with_tiabskey_supporting_builder(self) -> None:
        """Builder that supports tiabskey defaults to TITLE_ABSTRACT_KEYWORDS."""
        node = QueryNode(node_type=NodeType.TERM, value="test")
        assert _KeywordsBuilder().get_effective_filter(node) == FilterCode.TITLE_ABSTRACT_KEYWORDS

    def test_explicit_filter_overrides_builder_default(self) -> None:
        """Explicit filter_code wins over builder-aware default."""
        node = QueryNode(node_type=NodeType.TERM, value="test", filter_code=FilterCode.TITLE)
        assert _KeywordsBuilder().get_effective_filter(node) == FilterCode.TITLE

    def test_inherited_filter_overrides_builder_default(self) -> None:
        """Inherited filter wins over builder-aware default."""
        node = QueryNode(
            node_type=NodeType.TERM,
            value="test",
            inherited_filter_code=FilterCode.ABSTRACT,
        )
        assert _KeywordsBuilder().get_effective_filter(node) == FilterCode.ABSTRACT


# ---------------------------------------------------------------------------
# iter_term_nodes
# ---------------------------------------------------------------------------


class TestIterTermNodes:
    """Tests for QueryBuilder.iter_term_nodes()."""

    def test_single_term(self) -> None:
        """A single term node returns itself."""
        node = QueryNode(node_type=NodeType.TERM, value="machine")
        result = QueryBuilder.iter_term_nodes(node)
        assert len(result) == 1
        assert result[0].value == "machine"

    def test_nested_terms(self) -> None:
        """Recursively collects term nodes from a tree."""
        term1 = QueryNode(node_type=NodeType.TERM, value="a")
        term2 = QueryNode(node_type=NodeType.TERM, value="b")
        connector = QueryNode(node_type=NodeType.CONNECTOR, value=ConnectorType.AND)
        group = QueryNode(node_type=NodeType.GROUP, children=[term1, connector, term2])
        root = QueryNode(node_type=NodeType.ROOT, children=[group])

        result = QueryBuilder.iter_term_nodes(root)
        assert len(result) == 2
        assert {n.value for n in result} == {"a", "b"}

    def test_no_terms_returns_empty(self) -> None:
        """A tree with no term nodes returns an empty list."""
        root = QueryNode(node_type=NodeType.ROOT, children=[])
        assert QueryBuilder.iter_term_nodes(root) == []


# ---------------------------------------------------------------------------
# iter_connectors
# ---------------------------------------------------------------------------


class TestIterConnectors:
    """Tests for QueryBuilder.iter_connectors()."""

    def test_collects_connectors(self) -> None:
        """Finds connector values in a subtree."""
        c1 = QueryNode(node_type=NodeType.CONNECTOR, value=ConnectorType.AND)
        c2 = QueryNode(node_type=NodeType.CONNECTOR, value=ConnectorType.OR)
        term = QueryNode(node_type=NodeType.TERM, value="x")
        group = QueryNode(node_type=NodeType.GROUP, children=[term, c1, term, c2, term])

        result = QueryBuilder.iter_connectors(group)
        assert result == [ConnectorType.AND, ConnectorType.OR]

    def test_no_connectors(self) -> None:
        """A tree with no connectors returns an empty list."""
        node = QueryNode(node_type=NodeType.TERM, value="x")
        assert QueryBuilder.iter_connectors(node) == []


# ---------------------------------------------------------------------------
# has_wildcard
# ---------------------------------------------------------------------------


class TestHasWildcard:
    """Tests for QueryBuilder.has_wildcard()."""

    def test_star_wildcard(self) -> None:
        """Detects '*' wildcard."""
        assert QueryBuilder.has_wildcard("machine*") is True

    def test_question_wildcard(self) -> None:
        """Detects '?' wildcard."""
        assert QueryBuilder.has_wildcard("col?r") is True

    def test_no_wildcard(self) -> None:
        """Plain term has no wildcard."""
        assert QueryBuilder.has_wildcard("machine") is False

    def test_empty_string(self) -> None:
        """Empty string has no wildcard."""
        assert QueryBuilder.has_wildcard("") is False


# ---------------------------------------------------------------------------
# quote_term
# ---------------------------------------------------------------------------


class TestQuoteTerm:
    """Tests for QueryBuilder.quote_term()."""

    def test_term_with_spaces_is_quoted(self) -> None:
        """Multi-word term is wrapped in double quotes."""
        assert QueryBuilder.quote_term("machine learning") == '"machine learning"'

    def test_single_word_not_quoted(self) -> None:
        """Single-word term is left unchanged."""
        assert QueryBuilder.quote_term("machine") == "machine"


# ---------------------------------------------------------------------------
# convert_expression
# ---------------------------------------------------------------------------


class TestConvertExpression:
    """Tests for QueryBuilder.convert_expression()."""

    def test_simple_term(self) -> None:
        """A single term node is converted using term_converter."""
        node = QueryNode(node_type=NodeType.TERM, value="test")
        result = QueryBuilder.convert_expression(
            node,
            term_converter=lambda n: n.value or "",
            connector_map={ConnectorType.AND: "AND", ConnectorType.OR: "OR"},
        )
        assert result == "test"

    def test_two_terms_with_connector(self) -> None:
        """Two terms joined by a connector produce 'a AND b'."""
        term1 = QueryNode(node_type=NodeType.TERM, value="a")
        conn = QueryNode(node_type=NodeType.CONNECTOR, value=ConnectorType.AND)
        term2 = QueryNode(node_type=NodeType.TERM, value="b")
        group = QueryNode(node_type=NodeType.GROUP, children=[term1, conn, term2])

        result = QueryBuilder.convert_expression(
            group,
            term_converter=lambda n: n.value or "",
            connector_map={ConnectorType.AND: "AND", ConnectorType.OR: "OR"},
        )
        assert result == "a AND b"

    def test_nested_group_gets_parentheses(self) -> None:
        """Nested groups are wrapped in parentheses."""
        inner_t1 = QueryNode(node_type=NodeType.TERM, value="x")
        inner_conn = QueryNode(node_type=NodeType.CONNECTOR, value=ConnectorType.OR)
        inner_t2 = QueryNode(node_type=NodeType.TERM, value="y")
        inner_group = QueryNode(
            node_type=NodeType.GROUP,
            children=[inner_t1, inner_conn, inner_t2],
        )
        outer_conn = QueryNode(node_type=NodeType.CONNECTOR, value=ConnectorType.AND)
        outer_term = QueryNode(node_type=NodeType.TERM, value="z")
        root = QueryNode(
            node_type=NodeType.ROOT,
            children=[inner_group, outer_conn, outer_term],
        )

        result = QueryBuilder.convert_expression(
            root,
            term_converter=lambda n: n.value or "",
            connector_map={ConnectorType.AND: "AND", ConnectorType.OR: "OR"},
        )
        assert result == "(x OR y) AND z"


# ---------------------------------------------------------------------------
# clone_query
# ---------------------------------------------------------------------------


class TestCloneQuery:
    """Tests for QueryBuilder.clone_query()."""

    def test_clone_preserves_raw_query(self) -> None:
        """Cloned query has the same raw_query."""
        original = Query(
            raw_query="[machine learning] AND [deep learning]",
            root=QueryNode(node_type=NodeType.ROOT),
        )
        cloned = QueryBuilder.clone_query(original)
        assert cloned.raw_query == original.raw_query

    def test_clone_is_independent(self) -> None:
        """Changes to the clone don't affect the original."""
        original = Query(
            raw_query="[test]",
            root=QueryNode(
                node_type=NodeType.ROOT,
                children=[QueryNode(node_type=NodeType.TERM, value="test")],
            ),
        )
        cloned = QueryBuilder.clone_query(original)
        cloned.root.children.clear()
        # Original should still have its child
        assert len(original.root.children) == 1
