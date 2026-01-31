from __future__ import annotations

from enum import Enum


class Database(str, Enum):
    """Supported database identifiers."""

    ARXIV = "arxiv"
    BIORXIV = "biorxiv"
    IEEE = "ieee"
    MEDRXIV = "medrxiv"
    PUBMED = "pubmed"
    SCOPUS = "scopus"
