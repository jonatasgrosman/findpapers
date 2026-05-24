"""Findpapers - Academic paper search and management tool."""

from findpapers.core.author import Author
from findpapers.core.paper import Database, Paper, PaperType
from findpapers.core.query import ConnectorType, FilterCode
from findpapers.core.search_result import SearchResult
from findpapers.core.snowball_result import SnowballResult
from findpapers.core.source import Source, SourceType
from findpapers.engine import Engine
from findpapers.exceptions import (
    ConnectorError,
    FindpapersError,
    InvalidParameterError,
    MissingApiKeyError,
    ModelValidationError,
    PersistenceError,
    QueryValidationError,
    UnsupportedQueryError,
)
from findpapers.runners.download_runner import DownloadRunner
from findpapers.runners.get_runner import GetRunner
from findpapers.runners.search_runner import SearchRunner
from findpapers.runners.snowball_runner import SnowballRunner
from findpapers.utils.persistence import (
    load_from_bibtex,
    load_from_csv,
    load_from_json,
    save_to_bibtex,
    save_to_csv,
    save_to_json,
)

__all__ = [
    "Author",
    "ConnectorError",
    "ConnectorType",
    "Database",
    "DownloadRunner",
    "Engine",
    "FilterCode",
    "FindpapersError",
    "GetRunner",
    "InvalidParameterError",
    "MissingApiKeyError",
    "ModelValidationError",
    "Paper",
    "PaperType",
    "PersistenceError",
    "QueryValidationError",
    "SearchResult",
    "SearchRunner",
    "SnowballResult",
    "SnowballRunner",
    "Source",
    "SourceType",
    "UnsupportedQueryError",
    "load_from_bibtex",
    "load_from_csv",
    "load_from_json",
    "save_to_bibtex",
    "save_to_csv",
    "save_to_json",
]
