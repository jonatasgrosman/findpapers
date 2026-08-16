"""Query structures for parsing and validating search queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any


class NodeType(Enum):
    """Type of node in the query tree."""

    ROOT = "root"
    TERM = "term"
    CONNECTOR = "connector"
    GROUP = "group"


class ConnectorType(StrEnum):
    """Type of boolean connector.

    Inheriting from :class:`StrEnum` preserves equality with raw connector
    strings so existing ``connector == "and"`` comparisons keep working.
    """

    AND = "and"
    OR = "or"
    AND_NOT = "and not"


class FilterCode(StrEnum):
    """Valid filter codes for query filter specifiers.

    Each member inherits from :class:`StrEnum` so ``filter_code == "ti"``
    comparisons keep working without modification.

    Members
    -------
    TITLE
        ``ti``: search in the title field.
    ABSTRACT
        ``abs``: search in the abstract field.
    KEYWORDS
        ``key``: search in the keywords / subject field.
    AUTHOR
        ``au``: search by author name.
    SOURCE
        ``src``: search by source name (journal, conference, etc.).
    AFFILIATION
        ``aff``: search by institutional affiliation.
    TITLE_ABSTRACT
        ``tiabs``: search in title and abstract (default when unspecified).
    TITLE_ABSTRACT_KEYWORDS
        ``tiabskey``: search in title, abstract, and keywords.
    """

    TITLE = "ti"
    ABSTRACT = "abs"
    KEYWORDS = "key"
    AUTHOR = "au"
    SOURCE = "src"
    AFFILIATION = "aff"
    TITLE_ABSTRACT = "tiabs"
    TITLE_ABSTRACT_KEYWORDS = "tiabskey"


# Frozenset of raw filter-code strings derived from FilterCode.
# Kept for backward-compatible membership testing in the parser and validator.
VALID_FILTER_CODES: frozenset[str] = frozenset(fc.value for fc in FilterCode)


@dataclass
class QueryNode:
    """A node in the query tree.

    Attributes
    ----------
    node_type : NodeType
        The type of this node.
    value : str | None
        The value for TERM and CONNECTOR nodes.
    children : list[QueryNode]
        Child nodes for ROOT and GROUP nodes.
    filter_code : FilterCode | None
        Filter specifier explicitly defined in the original query for TERM and GROUP nodes.
        Preserved as-is from the query - not modified during propagation.
        Valid filter codes: ti (title), abs (abstract), key (keywords),
        au (author), src (source), aff (affiliation),
        tiabs (title + abstract), tiabskey (title + abstract + keywords).
    inherited_filter_code : FilterCode | None
        The effective filter code for this node after inheritance.
        For TERM nodes: the filter to actually use (from explicit filter_code or inherited).
        For GROUP nodes: the filter passed down to children.
        When None, defaults to 'tiabs' at conversion time.
    children_match_filter : bool | None
        Only applicable for GROUP nodes.
        True if all children use the same filter as the group (either by inheritance
        or by having the same explicit filter), allowing database APIs to apply
        the filter at the group level instead of individual terms.
        None for non-GROUP nodes.
    """

    node_type: NodeType
    value: str | None = None
    children: list[QueryNode] = field(default_factory=list)
    filter_code: FilterCode | None = None
    inherited_filter_code: FilterCode | None = None
    children_match_filter: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the node to a dictionary representation.

        Returns
        -------
        dict[str, Any]
            Dictionary representation of the node.
        """
        result: dict[str, Any] = {"node_type": self.node_type.value}
        if self.value is not None:
            result["value"] = (
                self.value.value if isinstance(self.value, ConnectorType) else self.value
            )
        if self.filter_code is not None:
            result["filter_code"] = self.filter_code.value
        if self.inherited_filter_code is not None:
            result["inherited_filter_code"] = self.inherited_filter_code.value
        if self.children_match_filter is not None:
            result["children_match_filter"] = self.children_match_filter
        if self.children:
            result["children"] = [child.to_dict() for child in self.children]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> QueryNode:
        """Create a QueryNode from a dictionary.

        Parameters
        ----------
        data : dict
            Dictionary with node_type, optional value, optional filter_code,
            optional inherited_filter_code, optional children_match_filter, and optional children.

        Returns
        -------
        QueryNode
            The reconstructed node.
        """
        node_type = NodeType(data["node_type"])
        raw_value = data.get("value")
        filter_code_str = data.get("filter_code")
        inherited_filter_code_str = data.get("inherited_filter_code")
        children_match_filter_value = data.get("children_match_filter")
        children = [cls.from_dict(child) for child in data.get("children", [])]
        # Reconstruct typed enum values from serialised strings.
        filter_code = FilterCode(filter_code_str) if filter_code_str is not None else None
        inherited_filter_code = (
            FilterCode(inherited_filter_code_str) if inherited_filter_code_str is not None else None
        )
        value: str | None = (
            ConnectorType(raw_value)
            if node_type == NodeType.CONNECTOR and raw_value is not None
            else raw_value
        )
        return cls(
            node_type=node_type,
            value=value,
            children=children,
            filter_code=filter_code,
            inherited_filter_code=inherited_filter_code,
            children_match_filter=children_match_filter_value,
        )

    def get_all_terms(self) -> list[str]:
        """Get all term values from this node and its children.

        Returns
        -------
        list[str]
            List of all term values.
        """
        terms: list[str] = []
        if self.node_type == NodeType.TERM and self.value:
            terms.append(self.value)
        for child in self.children:
            terms.extend(child.get_all_terms())
        return terms

    def get_all_filters(self) -> list[FilterCode]:
        """Get all unique filter codes used in this node and its children.

        Returns
        -------
        list[FilterCode]
            List of unique filter codes (e.g., [FilterCode.TITLE, FilterCode.ABSTRACT]).
        """
        all_filters: set[FilterCode] = set()
        if self.filter_code:
            all_filters.add(self.filter_code)
        for child in self.children:
            all_filters.update(child.get_all_filters())
        return sorted(all_filters)


@dataclass
class Query:
    """Represents a parsed and validated search query.

    This class represents a search query that has been parsed into a tree structure.
    The actual parsing and validation logic is handled by QueryParser and QueryValidator.

    The query follows these rules:
    - All terms must be enclosed in square brackets: [term]
    - Operators must have whitespace before and after them
    - Operators are case-insensitive (normalized to lowercase internally)
    - NOT must be preceded by AND: [term a] AND NOT [term b]
    - Subqueries can be enclosed in parentheses
    - Terms cannot be empty
    - Wildcards: ? replaces one char, * replaces zero or more
    - Wildcards cannot be at the start of a term
    - Minimum 3 chars before asterisk wildcard
    - Asterisk can only be at the end of a term
    - Only one wildcard per term
    - Wildcards only in single terms (no spaces)
    - Filter specifiers can be added before terms or groups:
      - Syntax: filter[term] or filter([group])
      - Valid filter codes: ti (title), abs (abstract), key (keywords),
        au (author), src (source), aff (affiliation),
        tiabs (title + abstract), tiabskey (title + abstract + keywords)
      - Filter codes are case-insensitive (normalized to lowercase internally)
      - When omitted, defaults to tiabs (title + abstract)
      - Group filters propagate to child terms (innermost wins)

    Attributes
    ----------
    raw_query : str
        The original query string.
    root : QueryNode
        The root node of the query tree.
    """

    raw_query: str
    root: QueryNode

    def get_all_terms(self) -> list[str]:
        """Get all term values from the query.

        Returns
        -------
        list[str]
            List of all term values.
        """
        return self.root.get_all_terms()

    def get_all_filters(self) -> list[FilterCode]:
        """Get all unique filter codes used in the query.

        Returns
        -------
        list[FilterCode]
            List of unique filter codes used across all terms.
        """
        return self.root.get_all_filters()

    def to_dict(self) -> dict[str, Any]:
        """Convert the query to a dictionary representation.

        Returns
        -------
        dict[str, Any]
            Dictionary with raw_query and tree structure.
        """
        return {
            "raw_query": self.raw_query,
            "tree": self.root.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Query:
        """Create a Query from a dictionary (bypasses validation).

        Parameters
        ----------
        data : dict
            Dictionary with raw_query and tree.

        Returns
        -------
        Query
            The reconstructed Query.
        """
        raw_query = data["raw_query"]
        root = QueryNode.from_dict(data["tree"])
        return cls(raw_query=raw_query, root=root)
