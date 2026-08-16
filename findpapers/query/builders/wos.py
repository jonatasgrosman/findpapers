"""Web of Science Starter API query builder."""

from __future__ import annotations

from findpapers.core.query import FilterCode, Query, QueryNode
from findpapers.query.builder import QueryBuilder, QueryValidationResult

# Mapping from findpapers FilterCode to WoS field tag.
#
# The WoS Starter API supports only these content field tags:
#   TI - Title
#   AU - Author
#   SO - Source title
#   OG - Organization
#   TS - Topic (title + abstract + author keywords + Keywords Plus)
#
# There is no abstract-only (abs), keywords-only (key), or title+abstract
# composite (tiabs) field tag in the WoS Starter API.  Queries using those
# filters are rejected by validate_query rather than silently broadened.
_FILTER_TAG_MAP: dict[FilterCode, str] = {
    FilterCode.TITLE: "TI",
    FilterCode.AUTHOR: "AU",
    FilterCode.SOURCE: "SO",
    FilterCode.AFFILIATION: "OG",
    FilterCode.TITLE_ABSTRACT_KEYWORDS: "TS",
}


class WosQueryBuilder(QueryBuilder):
    """Build Web of Science Starter API query expressions.

    Supported filter codes and their WoS field tags:

    * ``ti`` -> ``TI`` (Title)
    * ``au`` -> ``AU`` (Author)
    * ``src`` -> ``SO`` (Source)
    * ``aff`` -> ``OG`` (Organization)
    * ``tiabskey`` -> ``TS`` (Topic: title+abstract+author keywords+Keywords Plus)

    Unsupported filter codes (will cause the database to be skipped):

    * ``abs``: no abstract-only field tag in WoS Starter
    * ``key``: no keywords-only field tag in WoS Starter
    * ``tiabs``: no title+abstract composite (without keywords) in WoS Starter

    Wildcards ``*`` and ``?`` are passed through unchanged because WoS
    supports them natively (minimum 3 characters before ``*`` when using
    right-hand truncation, minimum 3 characters after ``*`` for left-hand
    truncation).

    The ``$`` wildcard (zero or one character) used in WoS has no equivalent
    in findpapers query syntax and is not generated.
    """

    _SUPPORTED_FILTERS = frozenset(
        {
            FilterCode.TITLE,
            FilterCode.AUTHOR,
            FilterCode.SOURCE,
            FilterCode.AFFILIATION,
            FilterCode.TITLE_ABSTRACT_KEYWORDS,
        }
    )

    def validate_query(self, query: Query) -> QueryValidationResult:
        """Validate whether WoS Starter supports this query.

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
                    error_message=f"Filter '{filter_code}' is not supported by WoS.",
                )
            value = term.value or ""
            if not value:
                continue
            # WoS requires at least 3 characters before a right-hand wildcard
            # and at least 3 characters after a left-hand wildcard.
            for wildcard in ("*", "?"):
                if wildcard in value:
                    parts = value.split(wildcard)
                    prefix = parts[0]
                    if 0 < len(prefix) < 3:
                        return QueryValidationResult(
                            is_valid=False,
                            error_message=(
                                f"WoS wildcard '{wildcard}' requires at least 3 characters "
                                f"before '{wildcard}' when using right-hand truncation."
                            ),
                        )
                    suffix = parts[-1] if len(parts) > 1 else ""
                    if value.startswith(wildcard) and 0 < len(suffix) < 3:
                        return QueryValidationResult(
                            is_valid=False,
                            error_message=(
                                f"WoS wildcard '{wildcard}' requires at least 3 characters "
                                f"after '{wildcard}' when using left-hand truncation."
                            ),
                        )
        return QueryValidationResult(is_valid=True)

    def convert_query(self, query: Query) -> str:
        """Convert a parsed query into a WoS Starter API ``q`` parameter string.

        Each term is wrapped in its corresponding WoS field tag using the
        format ``TAG=(value)``.  Terms without an explicit filter default to
        ``TS`` (Topic), which is the broadest supported composite field.

        Parameters
        ----------
        query : Query
            Parsed and propagated query object.

        Returns
        -------
        str
            WoS query string suitable for the ``q`` request parameter.
        """
        from findpapers.core.query import ConnectorType

        connector_map = {
            ConnectorType.AND: "AND",
            ConnectorType.OR: "OR",
            ConnectorType.AND_NOT: "NOT",
        }

        def convert_term(term_node: QueryNode) -> str:
            term = term_node.value or ""
            filter_code = self.get_effective_filter(term_node)
            tag = _FILTER_TAG_MAP.get(filter_code, "TS")
            return f"{tag}=({term})"

        def plain_term(term_node: QueryNode) -> str:
            """Convert term without filter prefix for group-level wrapping."""
            return term_node.value or ""

        def group_wrapper(group_node: QueryNode, inner: str) -> str | None:
            """Wrap a homogeneous group with the WoS field tag.

            Returns ``None`` when children use different filters, falling back
            to per-term conversion.
            """
            filter_code = self.get_effective_filter(group_node)
            tag = _FILTER_TAG_MAP.get(filter_code)
            if tag is None:
                return None
            return f"{tag}=({inner})"

        return self.convert_expression(
            query.root,
            convert_term,
            connector_map,
            plain_term_converter=plain_term,
            optimized_group_converter=group_wrapper,
        )
