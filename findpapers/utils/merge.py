"""Shared merge helpers for model enrichment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from findpapers.core.author import Author


def merge_authors(base: list[Author], incoming: list[Author]) -> list[Author]:
    """Merge two author lists by keeping whichever list is larger.

    When both lists have the same length, the list with more affiliations
    is preferred.  If still tied, the *base* list is kept.

    This conservative strategy avoids the risk of combining lists that
    represent the same authors in different string formats (e.g.
    ``"First Last"`` vs ``"Last, First"``).

    When the winning list is chosen, affiliations from the losing list are
    back-filled onto authors that share the same name but lack an affiliation
    in the winning list.

    Parameters
    ----------
    base : list[Author]
        Existing author list.
    incoming : list[Author]
        New authors to merge in.

    Returns
    -------
    list[Author]
        The merged author list.
    """
    if not incoming:
        return list(base)
    if not base:
        return list(incoming)

    base_affiliations = sum(1 for a in base if a.affiliation)
    incoming_affiliations = sum(1 for a in incoming if a.affiliation)

    if len(incoming) > len(base):
        winner, loser = list(incoming), base
    elif len(base) > len(incoming):
        winner, loser = list(base), incoming
    elif incoming_affiliations > base_affiliations:
        winner, loser = list(incoming), base
    else:
        winner, loser = list(base), incoming

    # Back-fill affiliations from the loser list.
    loser_map = {a.name.lower(): a.affiliation for a in loser if a.affiliation}
    for author in winner:
        if not author.affiliation and author.name.lower() in loser_map:
            author.affiliation = loser_map[author.name.lower()]

    return winner


def _dedup_concat(seq1: Any, seq2: Any) -> list[Any]:
    """Concatenate two sequences with order-preserving deduplication.

    Tolerates unhashable items by falling back to linear scan.

    Parameters
    ----------
    seq1 : Any
        First sequence.
    seq2 : Any
        Second sequence.

    Returns
    -------
    list[Any]
        Merged list without duplicates, preserving insertion order.
    """
    seen: set[Any] = set()
    result: list[Any] = []
    for item in list(seq1) + list(seq2):
        try:
            if item not in seen:
                seen.add(item)
                result.append(item)
        except TypeError:
            # Unhashable item — fall back to linear scan.
            if item not in result:
                result.append(item)
    return result


def _merge_dict(base: dict[Any, Any], incoming: dict[Any, Any]) -> dict[Any, Any]:
    """Recursively merge two dicts by merging each shared key's value.

    Parameters
    ----------
    base : dict
        Base dictionary.
    incoming : dict
        Incoming dictionary.

    Returns
    -------
    dict
        New dict with all keys from both inputs, values merged recursively.
    """
    merged = dict(base)
    for key in set(base.keys()) | set(incoming.keys()):
        merged[key] = merge_value(base.get(key), incoming.get(key))
    return merged


def merge_value(base: Any, incoming: Any) -> Any:
    """Merge two values, keeping the most complete result.

    Parameters
    ----------
    base : Any
        Base value.
    incoming : Any
        Incoming value.

    Returns
    -------
    Any
        Selected merged value.
    """
    # Prefer non-null values.
    if base is None:
        return incoming
    if incoming is None:
        return base

    # Prefer longer text and larger numeric values.
    if isinstance(base, str) and isinstance(incoming, str):
        return base if len(base) >= len(incoming) else incoming
    if isinstance(base, (int, float)) and isinstance(incoming, (int, float)):
        return base if base >= incoming else incoming

    # Prefer merged collections when possible.
    if isinstance(base, set) and isinstance(incoming, set):
        return base | incoming
    if isinstance(base, list) and isinstance(incoming, list):
        return _dedup_concat(base, incoming)
    if isinstance(base, tuple) and isinstance(incoming, tuple):
        return tuple(_dedup_concat(base, incoming))
    if isinstance(base, dict) and isinstance(incoming, dict):
        return _merge_dict(base, incoming)

    # Fall back to the base value for unsupported types.
    return base
