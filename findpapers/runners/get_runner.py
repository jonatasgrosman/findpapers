"""GetRunner: fetches a single paper by identifier (URL or DOI) from multiple sources."""

from __future__ import annotations

import logging
import re
from time import perf_counter

from findpapers.connectors import DOI_LOOKUP_REGISTRY, URL_LOOKUP_REGISTRY
from findpapers.connectors.connector_base import ConnectorBase
from findpapers.connectors.doi_lookup_base import DOILookupConnectorBase
from findpapers.connectors.url_lookup_base import URLLookupConnectorBase
from findpapers.connectors.web_scraping import WebScrapingConnector
from findpapers.core.paper import Database, Paper
from findpapers.exceptions import InvalidParameterError
from findpapers.utils.logging_config import configure_verbose_logging
from findpapers.utils.normalization import DOI_URL_PREFIXES

# ---------------------------------------------------------------------------
# Source-skipping heuristics
#
# These tables let GetRunner skip DOI-lookup connectors when the identifier
# (URL or DOI) strongly implies the paper is from a source that a given
# database does not index.  This reduces wasteful API usage against services
# with tight daily quotas (e.g. IEEE Xplore: ~200 requests/day).
# ---------------------------------------------------------------------------

# DOI prefix → databases to skip.
# The prefix comparison is case-insensitive.
_DOI_PREFIX_SKIP: tuple[tuple[str, frozenset[str]], ...] = (
    # arXiv assigns the 10.48550 prefix to all its preprints.  IEEE Xplore does
    # not index arXiv preprints.
    ("10.48550/", frozenset({Database.IEEE})),
    # bioRxiv and medRxiv share the 10.1101 prefix.  IEEE Xplore does not
    # index biomedical preprints.
    ("10.1101/", frozenset({Database.IEEE})),
)

# URL substring (case-insensitive) → databases to skip.
_URL_SUBSTRING_SKIP: tuple[tuple[str, frozenset[str]], ...] = (
    # arXiv landing pages — not indexed by IEEE.
    ("arxiv.org", frozenset({Database.IEEE})),
    # bioRxiv / medRxiv landing pages — not indexed by IEEE.
    ("biorxiv.org", frozenset({Database.IEEE})),
    ("medrxiv.org", frozenset({Database.IEEE})),
)

logger = logging.getLogger(__name__)

# Matches doi.org and dx.doi.org redirect URLs.  These bypass HTML scraping
# and go straight to the DOI-based API connectors.
_DOI_ORG_URL_RE: re.Pattern[str] = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)

# All valid ``databases`` values accepted by :class:`GetRunner`.
# ``"web_scraping"`` is a special toggle not backed by a connector class.
GET_DATABASES: frozenset[str] = frozenset(
    {db.value for db in DOI_LOOKUP_REGISTRY} | {"web_scraping"}
)


class GetRunner:
    """Runner that fetches a single paper by URL or DOI from multiple sources.

    The pipeline runs in two complementary stages that are no longer mutually
    exclusive:

    **Stage 1 — web scraping** (landing-page URLs only, requires ``"web_scraping"`` in *databases*):
        :class:`~findpapers.connectors.web_scraping.WebScrapingConnector` is
        tried first.  If the URL belongs to a known database (arXiv, PubMed,
        OpenAlex, Semantic Scholar, IEEE) the call is delegated to that
        database's API connector instead of performing HTML scraping.  Any DOI
        found in the result is carried forward to Stage 2.

    **Stage 2 — DOI lookup** (requires a DOI to be available):
        CrossRef is queried first as the canonical DOI registration authority
        (when ``"crossref"`` is in *databases*).
        The remaining connectors (arXiv, IEEE, PubMed, Scopus, Semantic
        Scholar, OpenAlex) follow in order, and each result is *merged* into
        the base paper so that gaps from one source are filled by another.
        The CrossRef URL is preserved as the final canonical URL when
        available.

    For bare DOI inputs (or ``doi.org`` redirect URLs) Stage 1 is skipped and
    the lookup proceeds directly to Stage 2.

    Parameters
    ----------
    identifier : str
        A bare DOI (e.g. ``"10.1038/nature12373"``), a doi.org redirect URL
        (e.g. ``"https://doi.org/10.1038/nature12373"``), or a paper
        landing-page URL (e.g. ``"https://arxiv.org/abs/1706.03762"``).
    email : str | None
        Contact email for CrossRef and OpenAlex polite-pool access.  When
        provided those APIs grant higher rate-limits.
    databases : list[str] | None
        Sources to consult when looking up the paper.  When ``None`` all
        sources are used.  Pass a list to enable only the specified ones.
        Accepted values: ``"arxiv"``, ``"crossref"``, ``"ieee"``,
        ``"openalex"``, ``"pubmed"``, ``"scopus"``,
        ``"semantic_scholar"``, ``"web_scraping"``.
    ieee_api_key : str | None
        IEEE Xplore API key.  When omitted IEEE is skipped.
    scopus_api_key : str | None
        Elsevier / Scopus API key.  When omitted Scopus is skipped.
    pubmed_api_key : str | None
        NCBI PubMed API key.  Optional — increases the PubMed rate limit.
    openalex_api_key : str | None
        OpenAlex API key.  Optional — increases the OpenAlex daily quota.
    semantic_scholar_api_key : str | None
        Semantic Scholar API key.  Optional — provides a dedicated quota.
    wos_api_key : str | None
        Clarivate Web of Science API key.  When omitted WoS is skipped.
    timeout : float | None
        HTTP request timeout in seconds.  ``None`` uses the ``requests``
        default.
    proxy : str | None
        Optional HTTP/HTTPS proxy URL for web scraping requests.
    ssl_verify : bool
        Whether to verify SSL certificates.  Set to ``False`` only when
        working behind institutional proxies that perform SSL inspection.
        Defaults to ``True``.

    Raises
    ------
    InvalidParameterError
        If *identifier* is a bare DOI that is empty or blank after stripping
        whitespace and URL prefixes.
    InvalidParameterError
        If *databases* is an empty list or contains unknown database names.

    Examples
    --------
    Fetch by bare DOI:

    >>> runner = GetRunner(identifier="10.1038/nature12373")
    >>> paper = runner.run()

    Fetch by landing-page URL (scrapes first, then enriches via DOI if found):

    >>> runner = GetRunner(identifier="https://arxiv.org/abs/1706.03762")
    >>> paper = runner.run()
    """

    def __init__(
        self,
        identifier: str,
        email: str | None = None,
        databases: list[str] | None = None,
        ieee_api_key: str | None = None,
        scopus_api_key: str | None = None,
        pubmed_api_key: str | None = None,
        openalex_api_key: str | None = None,
        semantic_scholar_api_key: str | None = None,
        wos_api_key: str | None = None,
        timeout: float | None = 10.0,
        proxy: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialise the runner with an identifier and connection settings.

        Parameters
        ----------
        identifier : str
            A bare DOI, doi.org redirect URL, or paper landing-page URL.
        email : str | None
            Contact email for CrossRef and OpenAlex polite-pool access.
        databases : list[str] | None
            Sources to consult when looking up the paper.  When ``None``
            all sources are used.  Pass a list to enable only the
            specified ones.  Accepted values: ``"arxiv"``,
            ``"crossref"``, ``"ieee"``, ``"openalex"``, ``"pubmed"``,
            ``"scopus"``, ``"semantic_scholar"``, ``"web_scraping"``.
        ieee_api_key : str | None
            IEEE Xplore API key.
        scopus_api_key : str | None
            Elsevier / Scopus API key.
        pubmed_api_key : str | None
            NCBI PubMed API key.
        openalex_api_key : str | None
            OpenAlex API key.
        semantic_scholar_api_key : str | None
            Semantic Scholar API key.
        wos_api_key : str | None
            Clarivate Web of Science API key.
        timeout : float | None
            HTTP request timeout in seconds.
        proxy : str | None
            Optional HTTP/HTTPS proxy URL.
        ssl_verify : bool
            Whether to verify SSL certificates.

        Raises
        ------
        InvalidParameterError
            If *identifier* looks like a bare DOI (not a URL) but is empty
            after stripping.
        InvalidParameterError
            If *databases* is an empty list or contains unknown database names.
        """
        self._identifier = identifier
        self._timeout = timeout

        # Validate and resolve the active databases filter.
        if databases is not None and len(databases) == 0:
            raise InvalidParameterError(
                "databases must not be an empty list. Pass None to select all available databases."
            )
        if databases is not None:
            normalised = [db.strip().lower() for db in databases]
            unknown = [db for db in normalised if db not in GET_DATABASES]
            if unknown:
                raise InvalidParameterError(
                    f"Unknown database(s): {', '.join(unknown)}. "
                    f"Accepted values: {', '.join(sorted(GET_DATABASES))}"
                )
            active_dbs: frozenset[str] = frozenset(normalised)
        else:
            active_dbs = GET_DATABASES

        # Per-source credentials forwarded to each connector at construction time.
        _credentials: dict[Database, dict[str, object]] = {
            Database.CROSSREF: {"email": email},
            Database.ARXIV: {},
            Database.IEEE: {"api_key": ieee_api_key},
            Database.OPENALEX: {"api_key": openalex_api_key, "email": email},
            Database.PUBMED: {"api_key": pubmed_api_key},
            Database.SCOPUS: {"api_key": scopus_api_key},
            Database.SEMANTIC_SCHOLAR: {"api_key": semantic_scholar_api_key},
            Database.WOS: {"api_key": wos_api_key},
        }
        # Sources whose connector requires an API key to function.
        _key_required: frozenset[Database] = frozenset(
            {Database.IEEE, Database.SCOPUS, Database.WOS}
        )

        _doi_map = GetRunner._build_doi_map(active_dbs, _credentials, _key_required)

        self._crossref: DOILookupConnectorBase | None = _doi_map.get(Database.CROSSREF)
        self._arxiv: DOILookupConnectorBase | None = _doi_map.get(Database.ARXIV)
        self._ieee: DOILookupConnectorBase | None = _doi_map.get(Database.IEEE)
        self._openalex: DOILookupConnectorBase | None = _doi_map.get(Database.OPENALEX)
        self._pubmed: DOILookupConnectorBase | None = _doi_map.get(Database.PUBMED)
        self._scopus: DOILookupConnectorBase | None = _doi_map.get(Database.SCOPUS)
        self._semantic_scholar: DOILookupConnectorBase | None = _doi_map.get(
            Database.SEMANTIC_SCHOLAR
        )
        self._wos: DOILookupConnectorBase | None = _doi_map.get(Database.WOS)

        if timeout is not None:
            for connector in self._doi_connectors:
                connector._timeout = timeout

        url_lookup = GetRunner._build_url_connectors(active_dbs, _credentials, _key_required)

        self._scraper: WebScrapingConnector | None = (
            WebScrapingConnector(
                proxy=proxy,
                ssl_verify=ssl_verify,
                url_lookup_connectors=url_lookup,
            )
            if "web_scraping" in active_dbs
            else None
        )
        if timeout is not None and self._scraper is not None:
            self._scraper._timeout = timeout

        self._result: Paper | None = None

    @staticmethod
    def _build_doi_map(
        active_dbs: frozenset[str],
        credentials: dict[Database, dict[str, object]],
        key_required: frozenset[Database],
    ) -> dict[Database, DOILookupConnectorBase]:
        """Instantiate DOI-lookup connectors for the enabled databases.

        Parameters
        ----------
        active_dbs : frozenset[str]
            Set of lowercase database names to enable.
        credentials : dict[Database, dict[str, object]]
            Per-source constructor kwargs.
        key_required : frozenset[Database]
            Sources that need a non-empty ``api_key`` credential.

        Returns
        -------
        dict[Database, DOILookupConnectorBase]
            Mapping from database enum to instantiated connector.
        """
        doi_map: dict[Database, DOILookupConnectorBase] = {}
        for source, cls in DOI_LOOKUP_REGISTRY.items():
            if source.value not in active_dbs:
                continue
            creds = credentials.get(source, {})
            if source in key_required and not creds.get("api_key"):
                continue
            doi_map[source] = cls(**creds)
        return doi_map

    @staticmethod
    def _build_url_connectors(
        active_dbs: frozenset[str],
        credentials: dict[Database, dict[str, object]],
        key_required: frozenset[Database],
    ) -> list[URLLookupConnectorBase]:
        """Instantiate URL-lookup connectors for the enabled databases.

        Parameters
        ----------
        active_dbs : frozenset[str]
            Set of lowercase database names to enable.
        credentials : dict[Database, dict[str, object]]
            Per-source constructor kwargs.
        key_required : frozenset[Database]
            Sources that need a non-empty ``api_key`` credential.

        Returns
        -------
        list[URLLookupConnectorBase]
            Instantiated URL-lookup connectors.
        """
        url_lookup: list[URLLookupConnectorBase] = []
        for url_source, url_cls in URL_LOOKUP_REGISTRY.items():
            if url_source.value not in active_dbs:
                continue
            url_creds = credentials.get(url_source, {})
            if url_source in key_required and not url_creds.get("api_key"):
                continue
            url_lookup.append(url_cls(**url_creds))
        return url_lookup

    @property
    def _doi_connectors(self) -> list[ConnectorBase]:
        """Return all DOI-based connector instances in lookup priority order.

        Returns
        -------
        list[ConnectorBase]
            Connectors ordered: CrossRef (when enabled), OpenAlex, Semantic
            Scholar, PubMed, arXiv, and optionally IEEE and Scopus when their
            API keys were provided at construction time.
        """
        connectors: list[ConnectorBase | None] = [
            self._crossref,
            self._openalex,
            self._semantic_scholar,
            self._pubmed,
            self._arxiv,
            self._ieee,
            self._scopus,
            self._wos,
        ]
        return [c for c in connectors if c is not None]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, verbose: bool = False) -> Paper | None:
        """Execute the full lookup pipeline for the configured identifier.

        The pipeline runs two complementary stages:

        1. **URL stage** (landing-page URLs only): web scraping is performed,
           potentially yielding an initial paper and its DOI.
        2. **DOI stage**: CrossRef and all other API connectors are queried
           using the available DOI (from Stage 1 or the original identifier),
           and their results are merged into the base paper.

        For bare DOI inputs or ``doi.org`` URLs, Stage 1 is skipped.

        Parameters
        ----------
        verbose : bool
            When ``True``, emit detailed log messages at DEBUG level.
            Defaults to ``False``.

        Returns
        -------
        Paper | None
            A :class:`~findpapers.core.paper.Paper` populated with the best
            available metadata from all queried sources, or ``None`` when no
            source found a match.
        """
        _root_logger = logging.getLogger()
        _saved_log_level = _root_logger.level
        if verbose:
            configure_verbose_logging()
        logger.debug("[GetRunner] %s", self._identifier)

        start = perf_counter()

        base_paper: Paper | None = None
        doi: str | None = None

        try:
            base_paper, doi = self._run_stage1(self._identifier)

            if doi is None:
                self._result = base_paper
                _root_logger.setLevel(_saved_log_level)
                return self._result

            base_paper = self._run_stage2(doi, base_paper)

        finally:
            for doi_connector in self._doi_connectors:
                doi_connector.close()
            if self._scraper is not None:
                self._scraper.close()

        self._result = base_paper
        runtime = perf_counter() - start

        if self._result is not None:
            dbs = ", ".join(sorted(self._result.databases or []))
            logger.debug("Lookup found — databases: %s (%.2f s)", dbs, runtime)
        else:
            logger.debug("Lookup not found (%.2f s)", runtime)

        _root_logger.setLevel(_saved_log_level)
        return self._result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_stage1(self, identifier: str) -> tuple[Paper | None, str | None]:
        """Run Stage 1 — web scraping / URL resolution.

        Parameters
        ----------
        identifier : str
            The raw identifier passed to the runner.

        Returns
        -------
        tuple[Paper | None, str | None]
            The scraped paper (or ``None``) and the resolved DOI (or ``None``).
        """
        base_paper: Paper | None = None
        doi: str | None = None

        if self._is_landing_page_url(identifier):
            if self._scraper is not None:
                logger.debug("Stage 1 — web scraping: %s", identifier)
                try:
                    base_paper = self._scraper.fetch_paper_from_url(
                        identifier, timeout=self._timeout
                    )
                except Exception as exc:
                    logger.debug("Web scraping failed for URL %s: %s", identifier, exc)
                doi = base_paper.doi if base_paper is not None else None
                if doi:
                    logger.debug("  Scraped DOI: %s", doi)
                else:
                    logger.debug("  No DOI found — Stage 2 will be skipped.")
            else:
                logger.debug("Stage 1 — web scraping: skipped (disabled via databases filter)")
        else:
            doi = self._sanitize_doi(identifier)
            if self._scraper is not None and doi:
                doi_redirect_url = f"https://doi.org/{doi}"
                logger.debug("Stage 1 — web scraping via DOI URL: %s", doi_redirect_url)
                try:
                    base_paper = self._scraper.fetch_paper_from_url(
                        doi_redirect_url, timeout=self._timeout
                    )
                except Exception as exc:
                    logger.debug(
                        "Web scraping failed for DOI URL %s: %s",
                        doi_redirect_url,
                        exc,
                    )
                if base_paper is not None:
                    logger.debug("  Scraped: %s", base_paper.title)
                else:
                    logger.debug("  No paper found via web scraping.")

        return base_paper, doi

    def _run_stage2(self, doi: str, base_paper: Paper | None) -> Paper | None:
        """Run Stage 2 — DOI-based API lookup and merging.

        Parameters
        ----------
        doi : str
            The resolved DOI.
        base_paper : Paper | None
            Optional paper seeded from Stage 1 scraping.

        Returns
        -------
        Paper | None
            Merged paper with metadata from all available connectors.
        """
        logger.debug("Stage 2 — DOI lookup: %s", doi)

        scraped_url: str | None = base_paper.url if base_paper is not None else None

        crossref_paper = self._run_doi_connector(self._crossref, "CrossRef", doi)
        crossref_url: str | None = crossref_paper.url if crossref_paper is not None else None

        if crossref_paper is not None:
            if base_paper is None:
                base_paper = crossref_paper
            else:
                base_paper.merge(crossref_paper)

        for connector, name, database in (
            (self._arxiv, "arXiv", Database.ARXIV),
            (self._ieee, "IEEE", Database.IEEE),
            (self._pubmed, "PubMed", Database.PUBMED),
            (self._scopus, "Scopus", Database.SCOPUS),
            (self._semantic_scholar, "Semantic Scholar", Database.SEMANTIC_SCHOLAR),
            (self._openalex, "OpenAlex", Database.OPENALEX),
            (self._wos, "WoS", Database.WOS),
        ):
            if self._should_skip_connector(database, doi, self._identifier):
                logger.debug("  %s: skipped (source heuristic)", name)
                continue
            base_paper = self._run_and_merge(connector, name, doi, base_paper)

        if base_paper is not None:
            if scraped_url is not None:
                base_paper.url = scraped_url
            elif crossref_url is not None:
                base_paper.url = crossref_url

        return base_paper

    def _run_doi_connector(
        self,
        connector: DOILookupConnectorBase | None,
        name: str,
        doi: str,
    ) -> Paper | None:
        """Query one DOI connector and return its result without merging.

        Parameters
        ----------
        connector : DOILookupConnectorBase | None
            Connector to query.  When ``None`` the method returns ``None``
            immediately (connector was not initialised due to a missing API
            key).
        name : str
            Human-readable connector name used in log messages.
        doi : str
            Bare DOI to look up.

        Returns
        -------
        Paper | None
            Paper returned by the connector, or ``None`` when the connector
            is absent, the DOI is not found, or an error occurs.
        """
        if connector is None:
            return None
        logger.debug("Querying %s\u2026", name)
        try:
            paper = connector.fetch_paper_by_doi(doi)
        except Exception:
            logger.debug("%s lookup failed for DOI %s.", name, doi, exc_info=True)
            paper = None
        if paper is None:
            logger.debug("  %s: not found", name)
        else:
            logger.debug("  %s: found", name)
        return paper

    def _run_and_merge(
        self,
        connector: DOILookupConnectorBase | None,
        name: str,
        doi: str,
        base_paper: Paper | None,
    ) -> Paper | None:
        """Query a connector and merge its result into *base_paper*.

        If the connector returns a paper and *base_paper* already exists,
        the new paper is merged into the base so that each subsequent source
        enriches the accumulated result.  If *base_paper* is ``None`` the
        new paper becomes the base.

        Parameters
        ----------
        connector : DOILookupConnectorBase | None
            Connector to query.
        name : str
            Human-readable connector name used in log messages.
        doi : str
            Bare DOI to look up.
        base_paper : Paper | None
            The accumulated result so far (may be ``None``).

        Returns
        -------
        Paper | None
            Updated *base_paper* with the connector's data merged in, or the
            original *base_paper* when the connector returns nothing new.
        """
        paper = self._run_doi_connector(connector, name, doi)
        if paper is None:
            return base_paper
        if base_paper is None:
            return paper
        base_paper.merge(paper)
        return base_paper

    @staticmethod
    def _should_skip_connector(
        database: str,
        doi: str | None,
        identifier: str,
    ) -> bool:
        """Return ``True`` when heuristics indicate a connector is unlikely to hold the paper.

        Skipping a connector avoids wasting a quota-limited API request against
        a database that does not index papers from the detected source.  The
        check is intentionally conservative: it only skips when the DOI prefix
        or identifier URL *definitively* points to a preprint server or domain
        incompatible with the given database.

        Parameters
        ----------
        database : str
            The :class:`~findpapers.core.paper.Database` value of the connector
            being evaluated (e.g. ``"ieee"``).
        doi : str | None
            Bare DOI resolved for the paper so far, or ``None`` when unknown.
        identifier : str
            The original identifier supplied by the caller (bare DOI, doi.org
            URL, or landing-page URL).

        Returns
        -------
        bool
            ``True`` when the connector should be skipped for this paper.
        """
        if doi is not None:
            doi_lower = doi.lower()
            for prefix, skip_set in _DOI_PREFIX_SKIP:
                if doi_lower.startswith(prefix) and database in skip_set:
                    return True
        identifier_lower = identifier.lower()
        for substring, skip_set in _URL_SUBSTRING_SKIP:
            if substring in identifier_lower and database in skip_set:
                return True
        return False

    @staticmethod
    def _is_landing_page_url(identifier: str) -> bool:
        """Return ``True`` when *identifier* is a URL but not a doi.org redirect.

        Parameters
        ----------
        identifier : str
            The identifier string to classify.

        Returns
        -------
        bool
            ``True`` for ``http://`` and ``https://`` URLs that are not
            ``doi.org`` or ``dx.doi.org`` redirects.
        """
        return identifier.startswith(("http://", "https://")) and not _DOI_ORG_URL_RE.match(
            identifier
        )

    @staticmethod
    def _sanitize_doi(doi: str) -> str:
        """Strip whitespace and common URL prefixes from a DOI string.

        Parameters
        ----------
        doi : str
            Raw DOI input from the user.

        Returns
        -------
        str
            Bare DOI identifier.

        Raises
        ------
        InvalidParameterError
            If the result is empty after sanitization.
        """
        cleaned = doi.strip()
        for prefix in DOI_URL_PREFIXES:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :]
                break
        cleaned = cleaned.strip()
        if not cleaned:
            raise InvalidParameterError("DOI must not be empty.")
        return cleaned
