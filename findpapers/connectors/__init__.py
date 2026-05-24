"""Connector registry for academic database integrations.

Provides central registries that map source identifiers to their connector
classes, so that runners can discover connectors without importing each one
individually.

To register a **new search connector**:
    1. Create the connector class inheriting from
       :class:`~findpapers.connectors.search_base.SearchConnectorBase`.
    2. Add a corresponding member to
       :class:`~findpapers.core.paper.Database`.
    3. Add an entry to :data:`SEARCH_REGISTRY` below.

To register a **new DOI-lookup connector**:
    1. Create the connector class inheriting from
       :class:`~findpapers.connectors.doi_lookup_base.DOILookupConnectorBase`.
    2. Add a corresponding member to
       :class:`~findpapers.core.paper.Database`.
    3. Add an entry to :data:`DOI_LOOKUP_REGISTRY` below.

To register a **new URL-lookup connector**:
    1. Create the connector class inheriting from
       :class:`~findpapers.connectors.url_lookup_base.URLLookupConnectorBase`.
    2. Add a corresponding member to
       :class:`~findpapers.core.paper.Database`.
    3. Add an entry to :data:`URL_LOOKUP_REGISTRY` below.
"""

from __future__ import annotations

from findpapers.connectors.arxiv import ArxivConnector
from findpapers.connectors.crossref import CrossRefConnector
from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.ieee import IEEEConnector
from findpapers.connectors.openalex import OpenAlexConnector
from findpapers.connectors.pubmed import PubmedConnector
from findpapers.connectors.scopus import ScopusConnector
from findpapers.connectors.search_base import SearchConnectorBase
from findpapers.connectors.semantic_scholar import SemanticScholarConnector
from findpapers.connectors.url_lookup_base import URLLookupConnectorBase
from findpapers.connectors.wos import WosConnector
from findpapers.core.paper import Database

# Central mapping of Database identifiers to their search connector classes.
SEARCH_REGISTRY: dict[Database, type[SearchConnectorBase]] = {
    Database.ARXIV: ArxivConnector,
    Database.IEEE: IEEEConnector,
    Database.OPENALEX: OpenAlexConnector,
    Database.PUBMED: PubmedConnector,
    Database.SCOPUS: ScopusConnector,
    Database.SEMANTIC_SCHOLAR: SemanticScholarConnector,
    Database.WOS: WosConnector,
}

# Mapping of Database identifiers to DOI-lookup connector classes.
# CrossRef is listed first as the canonical DOI registration authority.
DOI_LOOKUP_REGISTRY: dict[Database, type[DOILookupConnectorBase]] = {
    Database.CROSSREF: CrossRefConnector,
    Database.ARXIV: ArxivConnector,
    Database.IEEE: IEEEConnector,
    Database.OPENALEX: OpenAlexConnector,
    Database.PUBMED: PubmedConnector,
    Database.SCOPUS: ScopusConnector,
    Database.SEMANTIC_SCHOLAR: SemanticScholarConnector,
    Database.WOS: WosConnector,
}

# Mapping of Database identifiers to URL-lookup connector classes.
# CrossRef and Scopus do not implement URLLookupConnectorBase and are absent.
URL_LOOKUP_REGISTRY: dict[Database, type[URLLookupConnectorBase]] = {
    Database.ARXIV: ArxivConnector,
    Database.IEEE: IEEEConnector,
    Database.OPENALEX: OpenAlexConnector,
    Database.PUBMED: PubmedConnector,
    Database.SEMANTIC_SCHOLAR: SemanticScholarConnector,
    Database.WOS: WosConnector,
}
