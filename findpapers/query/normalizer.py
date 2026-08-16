"""Query normalization logic.

This module provides :class:`QueryNormalizer`, which converts lenient query
forms into the canonical bracket syntax before validation and parsing.

Supported conversions
---------------------
Double-quote terms
    ``"DL" OR "ML"`` -> ``[DL] OR [ML]``

    Any term wrapped in double quotes is converted to the bracket form.
    A filter-code prefix immediately before the opening quote is preserved::

        ti"neural network" -> ti[neural network]

Bare query (no brackets, no double quotes)
    ``Deep learning`` -> ``[Deep learning]``

    When the entire query lacks both square brackets and double quotes, the
    whole string is treated as a single term and wrapped in brackets.

Already canonical
    ``[DL] OR [ML]`` -> unchanged.

    If the query already contains at least one ``[``, it is returned as-is so
    that the normal validation/parser path handles it.
"""

from __future__ import annotations

import re


class QueryNormalizer:
    """Normalize lenient query forms into the canonical bracket syntax.

    The normalizer is intentionally permissive: it only performs mechanical
    string transformations and never raises errors: validation is the
    responsibility of :class:`~findpapers.query.validator.QueryValidator`.
    """

    # Matches a double-quoted term, optionally preceded by a filter-code word
    # (sequence of letters that touches the opening quote with no space).
    # Group 1: filter prefix (may be empty string)
    # Group 2: term content inside the quotes
    _QUOTED_TERM_RE: re.Pattern[str] = re.compile(r'([a-zA-Z]*)"([^"]*)"')

    def normalize(self, query_string: str) -> str:
        """Return the canonical form of *query_string*.

        Parameters
        ----------
        query_string : str
            Raw query string as provided by the caller.

        Returns
        -------
        str
            The normalized query string ready for validation and parsing.
            If no normalization is needed the original string is returned
            unchanged.
        """
        query = query_string.strip()

        if not query:
            return query

        # Already uses brackets: pass through untouched.
        if "[" in query:
            return query

        # Double-quote form: replace each "..." (with optional filter prefix) with [...]
        if '"' in query:
            return self._QUOTED_TERM_RE.sub(self._replace_quoted_term, query)

        # Bare form: treat the whole string as a single term, but only when it
        # contains no parentheses.  A query like "((bad query" looks like an
        # attempt at a structured expression and should pass through unchanged
        # so the validator can report the unbalanced-parentheses error.
        if "(" not in query and ")" not in query:
            return f"[{query}]"

        return query

    # ------------------------------------------------------------------
    # Internal helpers

    @staticmethod
    def _replace_quoted_term(match: re.Match[str]) -> str:
        """Replace a regex match of a quoted term with the bracket form.

        Parameters
        ----------
        match : re.Match[str]
            A match object from :attr:`_QUOTED_TERM_RE`.

        Returns
        -------
        str
            The bracket-form replacement string.
        """
        prefix = match.group(1)
        content = match.group(2)
        return f"{prefix}[{content}]"
