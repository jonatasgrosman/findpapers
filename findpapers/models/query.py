"""Query model for parsing and validating search queries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class NodeType(Enum):
    """Type of node in the query tree."""

    ROOT = "root"
    TERM = "term"
    CONNECTOR = "connector"
    GROUP = "group"


class ConnectorType(Enum):
    """Type of boolean connector."""

    AND = "AND"
    OR = "OR"
    AND_NOT = "AND NOT"


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
    """

    node_type: NodeType
    value: Optional[str] = None
    children: List["QueryNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert the node to a dictionary representation.

        Returns
        -------
        dict
            Dictionary representation of the node.
        """
        result: dict = {"node_type": self.node_type.value}
        if self.value is not None:
            result["value"] = self.value
        if self.children:
            result["children"] = [child.to_dict() for child in self.children]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "QueryNode":
        """Create a QueryNode from a dictionary.

        Parameters
        ----------
        data : dict
            Dictionary with node_type, optional value, and optional children.

        Returns
        -------
        QueryNode
            The reconstructed node.
        """
        node_type = NodeType(data["node_type"])
        value = data.get("value")
        children = [cls.from_dict(child) for child in data.get("children", [])]
        return cls(node_type=node_type, value=value, children=children)

    def get_all_terms(self) -> List[str]:
        """Get all term values from this node and its children.

        Returns
        -------
        list[str]
            List of all term values.
        """
        terms: List[str] = []
        if self.node_type == NodeType.TERM and self.value:
            terms.append(self.value)
        for child in self.children:
            terms.extend(child.get_all_terms())
        return terms


class QueryValidationError(ValueError):
    """Raised when a query string is invalid."""


class Query:
    """Represents a parsed and validated search query.

    This class parses a search query string into a tree structure that can be
    used by different searchers to convert into database-specific query formats.

    The query must follow these rules:
    - All terms must be enclosed in square brackets: [term]
    - Boolean operators (AND, OR, NOT) must be uppercase
    - Operators must have whitespace before and after them
    - NOT must be preceded by AND: [term a] AND NOT [term b]
    - Subqueries can be enclosed in parentheses
    - Terms cannot be empty
    - Wildcards: ? replaces one char, * replaces zero or more
    - Wildcards cannot be at the start of a term
    - Minimum 3 chars before asterisk wildcard
    - Asterisk can only be at the end of a term
    - Only one wildcard per term
    - Wildcards only in single terms (no spaces)

    Parameters
    ----------
    query_string : str
        The raw query string to parse.

    Raises
    ------
    QueryValidationError
        If the query string is invalid.

    Examples
    --------
    >>> query = Query("[happiness] AND ([joy] OR [peace of mind]) AND NOT [stressful]")
    >>> query.root.children[0].value
    'happiness'
    """

    def __init__(self, query_string: str) -> None:
        """Create a Query from a string.

        Parameters
        ----------
        query_string : str
            The raw query string.

        Raises
        ------
        QueryValidationError
            If the query is invalid.
        """
        self._raw_query = query_string.strip()
        self._validate_query_string()
        self._root = self._parse_query()

    @property
    def raw_query(self) -> str:
        """Return the original query string.

        Returns
        -------
        str
            The original query string.
        """
        return self._raw_query

    @property
    def root(self) -> QueryNode:
        """Return the root node of the query tree.

        Returns
        -------
        QueryNode
            The root node.
        """
        return self._root

    def get_all_terms(self) -> List[str]:
        """Get all term values from the query.

        Returns
        -------
        list[str]
            List of all term values.
        """
        return self._root.get_all_terms()

    def to_dict(self) -> dict:
        """Convert the query to a dictionary representation.

        Returns
        -------
        dict
            Dictionary with raw_query and tree structure.
        """
        return {
            "raw_query": self._raw_query,
            "tree": self._root.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Query":
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
        query = object.__new__(cls)
        query._raw_query = data["raw_query"]
        query._root = QueryNode.from_dict(data["tree"])
        return query

    def _validate_query_string(self) -> None:
        """Validate the query string before parsing.

        Raises
        ------
        QueryValidationError
            If the query is invalid.
        """
        query = self._raw_query

        if not query:
            raise QueryValidationError("Query cannot be empty")

        # Check for balanced brackets
        self._check_balanced_brackets(query)

        # Check for balanced parentheses
        self._check_balanced_parentheses(query)

        # Check for empty terms
        if "[]" in query:
            raise QueryValidationError("Terms cannot be empty: found []")

        # Extract and validate all terms
        terms = re.findall(r"\[([^\]]*)\]", query)
        for term in terms:
            self._validate_term(term)

        # Check for consecutive terms without operators
        self._check_consecutive_terms(query)

        # Validate operators
        self._validate_operators(query)

        # Validate query structure (must have at least one term)
        self._validate_query_structure(query)

    def _check_balanced_brackets(self, query: str) -> None:
        """Check that square brackets are balanced.

        Parameters
        ----------
        query : str
            The query string.

        Raises
        ------
        QueryValidationError
            If brackets are not balanced.
        """
        count = 0
        for char in query:
            if char == "[":
                count += 1
            elif char == "]":
                count -= 1
            if count < 0:
                raise QueryValidationError("Unbalanced square brackets")
        if count != 0:
            raise QueryValidationError("Unbalanced square brackets")

    def _check_balanced_parentheses(self, query: str) -> None:
        """Check that parentheses are balanced.

        Parameters
        ----------
        query : str
            The query string.

        Raises
        ------
        QueryValidationError
            If parentheses are not balanced.
        """
        count = 0
        inside_term = False
        for char in query:
            if char == "[":
                inside_term = True
            elif char == "]":
                inside_term = False
            elif not inside_term:
                if char == "(":
                    count += 1
                elif char == ")":
                    count -= 1
                if count < 0:
                    raise QueryValidationError("Unbalanced parentheses")
        if count != 0:
            raise QueryValidationError("Unbalanced parentheses")

    def _validate_term(self, term: str) -> None:
        """Validate a single term.

        Parameters
        ----------
        term : str
            The term content (without brackets).

        Raises
        ------
        QueryValidationError
            If the term is invalid.
        """
        if not term or not term.strip():
            raise QueryValidationError("Terms cannot be empty")

        # Terms cannot contain double quotes
        if '"' in term:
            raise QueryValidationError(f"Terms cannot contain double quotes: [{term}]")

        # Count wildcards
        question_count = term.count("?")
        asterisk_count = term.count("*")
        total_wildcards = question_count + asterisk_count

        if total_wildcards == 0:
            return  # No wildcards, term is valid

        # Only one wildcard per term
        if total_wildcards > 1:
            raise QueryValidationError(
                f"Only one wildcard can be included in a search term: [{term}]"
            )

        # Wildcards cannot be at the start
        if term.startswith("?") or term.startswith("*"):
            raise QueryValidationError(
                f"Wildcards cannot be used at the start of a search term: [{term}]"
            )

        # Wildcards only in single terms (no spaces)
        if " " in term and total_wildcards > 0:
            raise QueryValidationError(
                f"Wildcards can be used only in single terms (no spaces): [{term}]"
            )

        # Asterisk-specific rules
        if asterisk_count > 0:
            asterisk_pos = term.index("*")

            # Asterisk can only be at the end
            if asterisk_pos != len(term) - 1:
                raise QueryValidationError(
                    f"The asterisk wildcard can only be used at the end of a search term: [{term}]"
                )

            # Minimum 3 characters before asterisk
            if asterisk_pos < 3:
                raise QueryValidationError(
                    f"A minimum of 3 characters preceding the asterisk wildcard is required: [{term}]"
                )

    def _check_consecutive_terms(self, query: str) -> None:
        """Check for consecutive terms without operators.

        Parameters
        ----------
        query : str
            The query string.

        Raises
        ------
        QueryValidationError
            If consecutive terms are found without operators.
        """
        # Pattern: ] followed by optional whitespace then [
        pattern = r"\]\s*\["
        if re.search(pattern, query):
            raise QueryValidationError(
                "Terms must be separated by boolean operators (AND, OR, AND NOT)"
            )

    def _validate_operators(self, query: str) -> None:
        """Validate boolean operators in the query.

        Parameters
        ----------
        query : str
            The query string.

        Raises
        ------
        QueryValidationError
            If operators are invalid.
        """
        # Remove terms to check operators and normalize to uppercase for validation
        query_without_terms = re.sub(r"\[[^\]]*\]", "TERM", query)
        query_upper = query_without_terms.upper()

        # Check for operators without proper whitespace (case-insensitive)
        if re.search(r"TERM(AND|OR|NOT)", query_upper):
            raise QueryValidationError("Operators must have whitespace before and after them")
        if re.search(r"(AND|OR|NOT)TERM", query_upper):
            raise QueryValidationError("Operators must have whitespace before and after them")

        # Check for NOT without preceding AND (case-insensitive)
        # Find all NOT occurrences and check if preceded by AND
        not_matches = list(re.finditer(r"\bNOT\b", query_upper))
        for match in not_matches:
            pos = match.start()
            before = query_upper[:pos].strip()
            # Must end with AND
            if not before.endswith("AND"):
                raise QueryValidationError(
                    "NOT operator must be preceded by AND: use 'AND NOT' instead of 'OR NOT' or just 'NOT'"
                )

        # Check for invalid operators
        words = query_upper.split()
        valid_keywords = {"AND", "OR", "NOT", "TERM", "(", ")"}
        for word in words:
            # Clean parentheses
            clean_word = word.strip("()")
            if clean_word and clean_word not in valid_keywords:
                # Check if it's an operator-like word
                if clean_word in {"XOR", "NAND", "NOR"}:
                    raise QueryValidationError(f"Invalid boolean operator: {clean_word}")

    def _validate_connector_placement(self, structure: str) -> None:
        """Validate that connectors are properly placed between terms/groups.

        Connectors (AND, OR, AND NOT) must be between terms or groups.
        A single term cannot have connectors.

        Parameters
        ----------
        structure : str
            Query structure with terms replaced by TERM markers.

        Raises
        ------
        QueryValidationError
            If connectors are not properly placed.
        """
        # Normalize: replace groups with GROUP marker, treating (...) as a unit
        # First, handle nested parentheses by iteratively replacing innermost groups
        normalized = structure
        while "(" in normalized:
            # Replace innermost parentheses groups
            normalized = re.sub(r"\([^()]*\)", " GROUP ", normalized)

        # Now we have a flat sequence of TERM, GROUP, and operators
        # Normalize whitespace and uppercase
        normalized = " ".join(normalized.upper().split())

        # Replace "AND NOT" with a single token to treat as one connector
        normalized = normalized.replace("AND NOT", "ANDNOT")

        tokens = normalized.split()

        if not tokens:
            return

        # Check: first token cannot be a connector
        if tokens[0] in {"AND", "OR", "ANDNOT", "NOT"}:
            raise QueryValidationError(
                "Connectors cannot appear at the beginning of a query or subquery"
            )

        # Check: last token cannot be a connector
        if tokens[-1] in {"AND", "OR", "ANDNOT", "NOT"}:
            raise QueryValidationError("Connectors cannot appear at the end of a query or subquery")

        # Check: connectors must be between terms/groups (not consecutive)
        for i, token in enumerate(tokens):
            if token in {"AND", "OR", "ANDNOT"}:
                # Previous token must be TERM or GROUP
                if i > 0 and tokens[i - 1] in {"AND", "OR", "ANDNOT", "NOT"}:
                    raise QueryValidationError(
                        "Connectors must be between terms or groups, not consecutive"
                    )
                # Next token must be TERM or GROUP
                if i < len(tokens) - 1 and tokens[i + 1] in {"AND", "OR", "ANDNOT"}:
                    raise QueryValidationError(
                        "Connectors must be between terms or groups, not consecutive"
                    )

    def _validate_query_structure(self, query: str) -> None:
        """Validate query structure - must have terms and proper connectors.

        Parameters
        ----------
        query : str
            The query string.

        Raises
        ------
        QueryValidationError
            If query structure is invalid.
        """
        # Replace terms with a marker and parentheses with nothing
        # to check what's left (should only be whitespace and valid operators)
        structure = re.sub(r"\[[^\]]*\]", " TERM ", query)

        # Check if the query contains any terms at all
        if "TERM" not in structure:
            raise QueryValidationError("Query must contain at least one term enclosed in []")

        # Validate connector placement - connectors must be between terms/groups
        self._validate_connector_placement(structure)

        # Check between terms/groups for invalid content
        # Split by TERM and check each segment
        segments = structure.split("TERM")

        for i, segment in enumerate(segments):
            # Skip empty segments
            if not segment.strip():
                continue

            # Remove parentheses and check what's left
            cleaned = segment.replace("(", " ").replace(")", " ").strip()

            if not cleaned:
                continue

            # The segment should only contain valid operators (case-insensitive)
            words = cleaned.split()
            for word in words:
                word_upper = word.upper()
                if word_upper not in {"AND", "OR", "NOT"}:
                    # Check if it looks like text that should be a term
                    if word and not word.startswith("(") and not word.endswith(")"):
                        raise QueryValidationError(
                            f"All terms must be enclosed in square brackets: found '{word}'"
                        )

    def _parse_query(self) -> QueryNode:
        """Parse the query string into a tree structure.

        Returns
        -------
        QueryNode
            The root node of the query tree.
        """
        return self._parse_query_recursive(self._raw_query, None)

    def _parse_query_recursive(self, query: str, parent: Optional[QueryNode]) -> QueryNode:
        """Recursively parse a query or subquery.

        Parameters
        ----------
        query : str
            The query string to parse.
        parent : QueryNode | None
            The parent node, or None for root.

        Returns
        -------
        QueryNode
            The parsed node.
        """
        if parent is None:
            parent = QueryNode(node_type=NodeType.ROOT, children=[])

        query_iterator = iter(query)
        current_character = next(query_iterator, None)
        current_connector = ""

        while current_character is not None:
            if current_character == "(":  # Beginning of a group
                if current_connector.strip():
                    parent.children.append(
                        QueryNode(
                            node_type=NodeType.CONNECTOR,
                            value=current_connector.strip().upper(),
                        )
                    )
                    current_connector = ""

                subquery = ""
                subquery_group_level = 1

                while True:
                    current_character = next(query_iterator, None)

                    if current_character is None:
                        raise QueryValidationError("Unbalanced parentheses")

                    if current_character == "[":
                        # Skip content inside brackets
                        subquery += current_character
                        while True:
                            current_character = next(query_iterator, None)
                            if current_character is None:
                                raise QueryValidationError("Missing term closing bracket")
                            subquery += current_character
                            if current_character == "]":
                                break
                        continue

                    if current_character == "(":
                        subquery_group_level += 1

                    elif current_character == ")":
                        subquery_group_level -= 1
                        if subquery_group_level == 0:
                            break

                    subquery += current_character

                group_node = QueryNode(node_type=NodeType.GROUP, children=[])
                parent.children.append(group_node)
                self._parse_query_recursive(subquery, group_node)

            elif current_character == "[":  # Beginning of a term
                if current_connector.strip():
                    parent.children.append(
                        QueryNode(
                            node_type=NodeType.CONNECTOR,
                            value=current_connector.strip().upper(),
                        )
                    )
                    current_connector = ""

                term_value = ""
                while True:
                    current_character = next(query_iterator, None)

                    if current_character is None:
                        raise QueryValidationError("Missing term closing bracket")

                    if current_character == "]":
                        break

                    term_value += current_character

                parent.children.append(QueryNode(node_type=NodeType.TERM, value=term_value))

            else:  # Part of a connector
                current_connector += current_character

            current_character = next(query_iterator, None)

        return parent

    def __repr__(self) -> str:
        """Return a string representation of the query.

        Returns
        -------
        str
            String representation.
        """
        return f"Query({self._raw_query!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another Query.

        Parameters
        ----------
        other : object
            The object to compare with.

        Returns
        -------
        bool
            True if equal, False otherwise.
        """
        if not isinstance(other, Query):
            return NotImplemented
        return self._raw_query == other._raw_query
