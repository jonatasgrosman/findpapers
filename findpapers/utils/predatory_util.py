from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

from .predatory_data import POTENTIAL_PREDATORY_JOURNALS, POTENTIAL_PREDATORY_PUBLISHERS

POTENTIAL_PREDATORY_PUBLISHERS_HOSTS: set[str] = {
    urlparse(entry.get("url", "")).netloc.replace("www.", "")
    for entry in POTENTIAL_PREDATORY_PUBLISHERS
    if entry.get("url")
}
POTENTIAL_PREDATORY_PUBLISHERS_NAMES: set[str] = {
    entry.get("name", "").lower() for entry in POTENTIAL_PREDATORY_PUBLISHERS if entry.get("name")
}
POTENTIAL_PREDATORY_JOURNALS_NAMES: set[str] = {
    entry.get("name", "").lower() for entry in POTENTIAL_PREDATORY_JOURNALS if entry.get("name")
}


def _normalize(value: str | None) -> str | None:
    """Normalize a string for matching.

    Parameters
    ----------
    value : str | None
        Raw string value.

    Returns
    -------
    str | None
        Normalized lowercase string, or None.
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _get_publication_fields(publication: object) -> tuple[str | None, str | None, str | None]:
    """Extract publication name, publisher name and publisher host.

    Parameters
    ----------
    publication : object
        Publication object or dict.

    Returns
    -------
    tuple[str | None, str | None, str | None]
        Publication name, publisher name, publisher host.
    """
    if isinstance(publication, dict):
        publication_name = _normalize(publication.get("title"))
        publisher_name = _normalize(publication.get("publisher"))
        publisher_host = _normalize(publication.get("publisher_host"))
    else:
        publication_name = _normalize(getattr(publication, "title", None))
        publisher_name = _normalize(getattr(publication, "publisher", None))
        publisher_host = _normalize(getattr(publication, "publisher_host", None))

    return publication_name, publisher_name, publisher_host


def is_predatory_publication(publication: object | None) -> bool:
    """Determine if a publication is potentially predatory.

    Parameters
    ----------
    publication : object | None
        Publication object or dict.

    Returns
    -------
    bool
        True if the publication matches a predatory list.
    """
    if publication is None:
        return False

    publication_name, publisher_name, publisher_host = _get_publication_fields(publication)

    if publication_name in POTENTIAL_PREDATORY_JOURNALS_NAMES:
        return True
    if publisher_name in POTENTIAL_PREDATORY_PUBLISHERS_NAMES:
        return True
    if publisher_host in POTENTIAL_PREDATORY_PUBLISHERS_HOSTS:
        return True
    return False


def normalize_allowed_types(types: Iterable[str]) -> set[str]:
    """Normalize publication types.

    Parameters
    ----------
    types : Iterable[str]
        Raw publication type names.

    Returns
    -------
    set[str]
        Normalized publication type names.
    """
    return {value.strip().lower() for value in types if value.strip()}
