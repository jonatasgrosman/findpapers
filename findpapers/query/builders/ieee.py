"""IEEE Xplore query builder."""

from __future__ import annotations

from findpapers.core.query import FilterCode, NodeType, Query, QueryNode
from findpapers.query.builder import QueryBuilder, QueryValidationResult


class IEEEQueryBuilder(QueryBuilder):
    """Build IEEE Xplore-compatible query payloads."""

    _SUPPORTED_FILTERS = frozenset(
        {
            # NOTE: FilterCode.TITLE is intentionally excluded.
            # The IEEE Xplore API "Article Title" field is broken in querytext
            # mode: it silently returns zero results regardless of the search
            # term.  The dedicated `article_title` parameter (used for simple
            # single-term queries) works, but querytext is the only option for
            # boolean expressions.  Because we cannot guarantee correct
            # behaviour for all query shapes, title-only searches are disabled.
            # Compound filters (TITLE_ABSTRACT, TITLE_ABSTRACT_KEYWORDS) remain
            # supported and search via Abstract / Index Terms instead.
            # Last verified: 2026-03-13 against IEEE Xplore API v1.
            FilterCode.ABSTRACT,
            FilterCode.KEYWORDS,
            FilterCode.AUTHOR,
            FilterCode.SOURCE,
            FilterCode.AFFILIATION,
            FilterCode.TITLE_ABSTRACT,
            FilterCode.TITLE_ABSTRACT_KEYWORDS,
        }
    )

    def validate_query(self, query: Query) -> QueryValidationResult:
        """Validate whether IEEE supports this query.

        Parameters
        ----------
        query : Query
            Query to validate.

        Returns
        -------
        QueryValidationResult
            Validation result.
        """
        for term in self.iter_term_nodes(query.root):
            filter_code = self.get_effective_filter(term)
            if not self.supports_filter(filter_code):
                return QueryValidationResult(
                    is_valid=False,
                    error_message=f"Filter '{filter_code}' is not supported by IEEE.",
                )
            if not term.value:
                continue
            if "?" in term.value:
                return QueryValidationResult(
                    is_valid=False,
                    error_message="Wildcard '?' is not supported by IEEE.",
                )
            if "*" in term.value:
                prefix = term.value.split("*")[0]
                if len(prefix) < 3:
                    return QueryValidationResult(
                        is_valid=False,
                        error_message="Wildcard '*' requires at least 3 chars before '*'.",
                    )
        return QueryValidationResult(is_valid=True)

    def convert_query(self, query: Query) -> dict:
        """Convert query into IEEE payload.

        Parameters
        ----------
        query : Query
            Query to convert.

        Returns
        -------
        dict
            IEEE query parameters.
        """
        from findpapers.core.query import ConnectorType

        if self._is_simple_single_term(query):
            term_node = query.root.children[0]
            return self._single_term_payload(term_node)

        connector_map = {
            ConnectorType.AND: "AND",
            ConnectorType.OR: "OR",
            ConnectorType.AND_NOT: "NOT",
        }

        def convert_term(term_node: QueryNode) -> str:
            term = term_node.value or ""
            filter_code = self.get_effective_filter(term_node)
            if filter_code == FilterCode.TITLE:
                return f'"Article Title":{self._quote(term)}'
            if filter_code == FilterCode.ABSTRACT:
                return f'"Abstract":{self._quote(term)}'
            if filter_code == FilterCode.KEYWORDS:
                return f'"Index Terms":{self._quote(term)}'
            if filter_code == FilterCode.AUTHOR:
                return f'"Authors":{self._quote(term)}'
            if filter_code == FilterCode.SOURCE:
                return f'"Publication Title":{self._quote(term)}'
            if filter_code == FilterCode.AFFILIATION:
                return f'"Affiliation":{self._quote(term)}'
            if filter_code == FilterCode.TITLE_ABSTRACT:
                # "Article Title" is broken in querytext mode (returns 0
                # results), so TITLE_ABSTRACT falls back to Abstract only.
                return f'"Abstract":{self._quote(term)}'
            # TITLE_ABSTRACT_KEYWORDS -> Abstract + Index Terms (no Article Title)
            abs_expr = f'"Abstract":{self._quote(term)}'
            key_expr = f'"Index Terms":{self._quote(term)}'
            return f"({abs_expr} OR {key_expr})"

        def plain_term(term_node: QueryNode) -> str:
            """Convert term without filter prefix."""
            return self._quote(term_node.value or "")

        def group_wrapper(group_node: QueryNode, inner: str) -> str | None:
            """Wrap a plain group expression with IEEE field prefix.

            Only single-field filters can be wrapped at the group level.
            Compound filters (tiabs, tiabskey) fall back to per-term.
            """
            filter_code = self.get_effective_filter(group_node)
            field_map: dict[FilterCode, str] = {
                # NOTE: FilterCode.TITLE / "Article Title" excluded: broken
                # in querytext mode (returns 0 results).
                FilterCode.ABSTRACT: '"Abstract"',
                FilterCode.KEYWORDS: '"Index Terms"',
                FilterCode.AUTHOR: '"Authors"',
                FilterCode.SOURCE: '"Publication Title"',
                FilterCode.AFFILIATION: '"Affiliation"',
            }
            field = field_map.get(filter_code)
            if field is None:
                return None  # compound filters fall back to per-term
            return f"{field}:({inner})"

        expression = self.convert_expression(
            query.root,
            convert_term,
            connector_map,
            plain_term_converter=plain_term,
            optimized_group_converter=group_wrapper,
        )
        return {"querytext": expression}

    def _is_simple_single_term(self, query: Query) -> bool:
        """Check whether query has one direct term node.

        Parameters
        ----------
        query : Query
            Query to inspect.

        Returns
        -------
        bool
            True for single-term query.
        """
        return (
            len(query.root.children) == 1
            and query.root.children[0].node_type == NodeType.TERM
            and query.root.children[0].value is not None
        )

    def _single_term_payload(self, term_node: QueryNode) -> dict:
        """Build payload for simple single-term query.

        Parameters
        ----------
        term_node : QueryNode
            Term node to convert.

        Returns
        -------
        dict
            IEEE parameters for single-field mode.
        """
        term = term_node.value or ""
        filter_code = self.get_effective_filter(term_node)
        mapping = {
            # NOTE: FilterCode.TITLE / "article_title" param actually works
            # for simple single-term queries, but we exclude ti[] from
            # _SUPPORTED_FILTERS because the querytext mode (used for boolean
            # expressions) silently returns 0 results for "Article Title".
            # Keeping it out of the mapping avoids inconsistent behaviour
            # between simple and compound queries.
            FilterCode.ABSTRACT: "abstract",
            FilterCode.KEYWORDS: "index_terms",
            FilterCode.AUTHOR: "author",
            FilterCode.SOURCE: "publication_title",
            FilterCode.AFFILIATION: "affiliation",
        }
        if filter_code in mapping:
            return {mapping[filter_code]: term}
        if filter_code == FilterCode.TITLE_ABSTRACT:
            # "Article Title" is broken in querytext mode, so TITLE_ABSTRACT
            # falls back to Abstract only.
            return {"abstract": term}
        # TITLE_ABSTRACT_KEYWORDS -> Abstract + Index Terms (no Article Title)
        return {
            "querytext": (f'("Abstract":{self._quote(term)} OR "Index Terms":{self._quote(term)})')
        }

    def _quote(self, term: str) -> str:
        """Quote terms for IEEE expression.

        Parameters
        ----------
        term : str
            Raw term.

        Returns
        -------
        str
            Quoted term string.
        """
        return f'"{term}"'
