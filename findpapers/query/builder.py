"""Abstract interfaces for database-specific query builders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from findpapers.core.query import ConnectorType, FilterCode, NodeType, Query, QueryNode


@dataclass(slots=True)
class QueryValidationResult:
    """Validation result for database-specific query compatibility.

    Attributes
    ----------
    is_valid : bool
        Whether the query is valid for the target database.
    error_message : str | None
        Human-readable error when validation fails.
    """

    is_valid: bool
    error_message: str | None = None


@dataclass(slots=True)
class QueryExecutionPlan:
    """Execution metadata produced by a query builder.

    Attributes
    ----------
    request_payloads : list[str | dict]
        Payloads that must be sent by the searcher.
    combination_expression : str
        Expression describing how searcher results should be combined.
        The expression uses aliases `q0`, `q1`, ... and boolean operators
        `AND`, `OR`, and `NOT` with set semantics:
        - `AND`: intersection of result sets
        - `OR`: union of result sets
        - `NOT`: difference (left minus right)
    """

    request_payloads: list[str | dict]
    combination_expression: str


class QueryBuilder(ABC):
    """Abstract base class for database-specific query builders.

    Subclasses must declare the set of supported filter codes by overriding
    ``_SUPPORTED_FILTERS`` and must implement ``validate_query`` and
    ``convert_query``.  The remaining methods have sensible defaults that
    subclasses may override when they need custom behaviour:

    * ``supports_filter``: returns ``True`` iff ``filter_code`` is in
      ``_SUPPORTED_FILTERS``.
    * ``preprocess_terms``: returns the query unchanged.
    * ``expand_query``: returns a single-element list containing the original
      query.
    """

    # Override in subclasses to declare which FilterCodes are accepted.
    _SUPPORTED_FILTERS: frozenset[FilterCode] = frozenset()

    @abstractmethod
    def validate_query(self, query: Query) -> QueryValidationResult:
        """Validate if this builder supports the given query.

        Parameters
        ----------
        query : Query
            Parsed query object.

        Returns
        -------
        QueryValidationResult
            Validation result with compatibility information.
        """

    @abstractmethod
    def convert_query(self, query: Query) -> str | dict:
        """Convert Query into a database-specific payload.

        Parameters
        ----------
        query : Query
            Parsed query object.

        Returns
        -------
        str | dict
            Query string for URL-based APIs or parameter dictionary for REST APIs.
        """

    def preprocess_terms(self, query: Query) -> Query:
        """Preprocess query terms before conversion.

        The default implementation returns the query unchanged. Override this
        method when the target database requires term normalisation (e.g.
        hyphen removal).

        Parameters
        ----------
        query : Query
            Query to preprocess.

        Returns
        -------
        Query
            Preprocessed query.
        """
        return query

    def supports_filter(self, filter_code: FilterCode) -> bool:
        """Check whether the builder supports a filter code.

        Returns ``True`` iff ``filter_code`` is present in
        ``_SUPPORTED_FILTERS``.  Override when more complex logic is needed.

        Parameters
        ----------
        filter_code : FilterCode
            Filter code to check.

        Returns
        -------
        bool
            True when the filter is supported.
        """
        return filter_code in self._SUPPORTED_FILTERS

    def expand_query(self, query: Query) -> list[Query]:
        """Expand query into multiple queries when necessary.

        The default implementation returns a single-element list containing
        the original query unchanged.  Override this method for databases that
        require query decomposition (e.g. OpenAlex DNF expansion).

        Parameters
        ----------
        query : Query
            Query to expand.

        Returns
        -------
        list[Query]
            Expanded query list.
        """
        return [query]

    def build_execution_plan(self, query: Query) -> QueryExecutionPlan:
        """Build request payloads and result-combination instructions.

        Parameters
        ----------
        query : Query
            Parsed query object.

        Returns
        -------
        QueryExecutionPlan
            Request payloads and expression for combining results.
        """
        expanded_queries = self.expand_query(query)
        request_payloads = [
            self.convert_query(expanded_query) for expanded_query in expanded_queries
        ]
        combination_expression = self._build_combination_expression(expanded_queries)
        return QueryExecutionPlan(
            request_payloads=request_payloads,
            combination_expression=combination_expression,
        )

    def _build_combination_expression(self, expanded_queries: list[Query]) -> str:
        """Build default combination expression for expanded queries.

        Parameters
        ----------
        expanded_queries : list[Query]
            Queries returned by ``expand_query``.

        Returns
        -------
        str
            Combination expression.
        """
        if len(expanded_queries) == 1:
            return "q0"
        return " OR ".join(f"q{index}" for index in range(len(expanded_queries)))

    # ------------------------------------------------------------------
    # Query helpers: available to all subclasses
    # ------------------------------------------------------------------

    def get_effective_filter(self, node: QueryNode) -> FilterCode:
        """Return effective filter code for a query node.

        When no explicit or inherited filter is set, the default is determined
        by the target database: ``tiabskey`` is used if ``self`` supports it,
        otherwise ``tiabs`` is used as the fallback.

        Parameters
        ----------
        node : QueryNode
            Query node to inspect.

        Returns
        -------
        FilterCode
            Explicit filter when present, otherwise inherited filter, otherwise
            the best default for this builder.
        """
        explicit = node.filter_code or node.inherited_filter_code
        if explicit:
            return explicit
        # Prefer tiabskey when the target database supports it so that keywords
        # are included in the default search scope.
        if self.supports_filter(FilterCode.TITLE_ABSTRACT_KEYWORDS):
            return FilterCode.TITLE_ABSTRACT_KEYWORDS
        return FilterCode.TITLE_ABSTRACT

    @staticmethod
    def iter_term_nodes(node: QueryNode) -> list[QueryNode]:
        """Return all term nodes in a subtree.

        Parameters
        ----------
        node : QueryNode
            Root node of a subtree.

        Returns
        -------
        list[QueryNode]
            Term nodes found recursively.
        """
        terms: list[QueryNode] = []
        if node.node_type == NodeType.TERM:
            terms.append(node)
        for child in node.children:
            terms.extend(QueryBuilder.iter_term_nodes(child))
        return terms

    @staticmethod
    def iter_connectors(node: QueryNode) -> list[ConnectorType]:
        """Return connector values in a subtree.

        Parameters
        ----------
        node : QueryNode
            Root node of a subtree.

        Returns
        -------
        list[ConnectorType]
            Connector enum members in tree order.
        """
        values: list[ConnectorType] = []
        if node.node_type == NodeType.CONNECTOR and node.value:
            values.append(ConnectorType(node.value))
        for child in node.children:
            values.extend(QueryBuilder.iter_connectors(child))
        return values

    @staticmethod
    def has_wildcard(term: str) -> bool:
        """Check if term contains wildcard characters.

        Parameters
        ----------
        term : str
            Input term.

        Returns
        -------
        bool
            True when term contains ``*`` or ``?``.
        """
        return "*" in term or "?" in term

    @staticmethod
    def quote_term(term: str) -> str:
        """Quote term preserving wildcard characters.

        Parameters
        ----------
        term : str
            Input term.

        Returns
        -------
        str
            Quoted term when it contains spaces, otherwise unchanged.
        """
        if " " in term:
            return f'"{term}"'
        return term

    @staticmethod
    def convert_expression(
        node: QueryNode,
        term_converter: Callable[[QueryNode], str],
        connector_map: dict[ConnectorType, str],
        *,
        plain_term_converter: Callable[[QueryNode], str] | None = None,
        optimized_group_converter: Callable[[QueryNode, str], str | None] | None = None,
    ) -> str:
        """Convert query tree node to infix expression.

        When ``plain_term_converter`` and ``optimized_group_converter`` are
        provided, GROUP nodes whose ``children_match_filter`` is ``True`` are
        converted in a compact form: the children are rendered without per-term
        filter prefixes and the whole group is wrapped by a single filter call
        via ``optimized_group_converter``.  If that callback returns ``None``
        the group falls back to the standard per-term conversion.

        Parameters
        ----------
        node : QueryNode
            Node to convert.
        term_converter : Callable[[QueryNode], str]
            Function that converts TERM nodes (including filter prefix).
        connector_map : dict[ConnectorType, str]
            Connector mapping for target database.
        plain_term_converter : Callable[[QueryNode], str] | None
            Function that converts TERM nodes **without** a filter prefix.
            Required for the group-level filter optimisation.
        optimized_group_converter : Callable[[QueryNode, str], str | None] | None
            Receives ``(group_node, plain_inner_expression)`` and returns a
            compact expression with the filter applied at the group level, or
            ``None`` to fall back to per-term conversion.

        Returns
        -------
        str
            Converted expression.
        """
        if node.node_type == NodeType.TERM:
            return term_converter(node)

        parts: list[str] = []
        for child in node.children:
            if child.node_type == NodeType.CONNECTOR and child.value:
                parts.append(connector_map[ConnectorType(child.value)])
                continue

            # Optimisation: apply filter at group level when all children share it
            if (
                child.node_type == NodeType.GROUP
                and child.children_match_filter
                and plain_term_converter is not None
                and optimized_group_converter is not None
            ):
                inner_plain = QueryBuilder.convert_expression(
                    child, plain_term_converter, connector_map
                )
                optimized = optimized_group_converter(child, inner_plain)
                if optimized is not None:
                    parts.append(optimized)
                    continue
                # Fall back to per-term conversion below

            converted = QueryBuilder.convert_expression(
                child,
                term_converter,
                connector_map,
                plain_term_converter=plain_term_converter,
                optimized_group_converter=optimized_group_converter,
            )
            if child.node_type == NodeType.GROUP:
                parts.append(f"({converted})")
            else:
                parts.append(converted)

        return " ".join(parts)

    @staticmethod
    def clone_query(query: Query) -> Query:
        """Clone a query object using dict serialization.

        Parameters
        ----------
        query : Query
            Query object.

        Returns
        -------
        Query
            Deep-copied query.
        """
        return Query.from_dict(query.to_dict())
