"""Abstract base class for connectors that can fetch a paper from a known URL.

Extends :class:`~findpapers.connectors.connector_base.ConnectorBase` with
the URL-lookup contract: extracting a native database ID from a landing-page
URL and fetching the corresponding paper via the database's own API.
"""

from __future__ import annotations

import re
from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from findpapers.core.paper import Paper

from findpapers.connectors.connector_base import ConnectorBase


class URLLookupConnectorBase(ConnectorBase):
    """Abstract base class for connectors that can resolve a URL to a Paper.

    Connectors that implement this interface expose two abstract members:

    * :attr:`url_pattern`: a compiled regex whose first capture group extracts
      the native database identifier from a matching landing-page URL.
    * :meth:`fetch_paper_by_id`: fetches a paper directly from the database
      API using the native identifier.

    The concrete :meth:`fetch_paper_by_url` method provided here ties the two
    together: it applies :attr:`url_pattern` to the given URL, and if a match
    is found it delegates to :meth:`fetch_paper_by_id`.

    This is used by :class:`~findpapers.connectors.web_scraping.WebScrapingConnector`
    to avoid HTML scraping when the URL belongs to a database that already has
    a structured API connector.
    """

    @property
    @abstractmethod
    def url_pattern(self) -> re.Pattern[str]:
        """Regex that matches URLs handled by this connector.

        The pattern must contain exactly one capture group that extracts the
        native database identifier (e.g. arXiv ID, PMID, article number).

        Returns
        -------
        re.Pattern[str]
            Compiled regular expression.
        """

    @abstractmethod
    def fetch_paper_by_id(self, paper_id: str) -> Paper | None:
        """Fetch a single paper by its native database identifier.

        Parameters
        ----------
        paper_id : str
            Native database identifier extracted from the URL
            (e.g. arXiv ID, PubMed PMID, IEEE article number).

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the paper is not found or cannot be parsed.
        """

    def supports_url(self, url: str) -> bool:
        """Return whether this connector can fetch the paper at *url*.

        Applies :attr:`url_pattern` to *url* and returns ``True`` when the
        pattern matches, indicating that this connector is the right one for
        the given landing-page URL.

        Parameters
        ----------
        url : str
            Landing-page URL to test.

        Returns
        -------
        bool
            ``True`` when the URL matches this connector's pattern.
        """
        return bool(self.url_pattern.search(url))

    def fetch_paper_by_url(self, url: str) -> Paper | None:
        """Fetch a paper by matching its landing-page URL against this connector.

        Applies :attr:`url_pattern` to *url*.  When it matches, the first
        capture group is extracted as the native database ID and passed to
        :meth:`fetch_paper_by_id`.  Returns ``None`` when the URL does not
        match this connector's pattern.

        Parameters
        ----------
        url : str
            Landing-page URL of the paper.

        Returns
        -------
        Paper | None
            A populated :class:`~findpapers.core.paper.Paper`, or ``None``
            when the URL is not recognised or the paper cannot be fetched.
        """
        match = self.url_pattern.search(url)
        if not match:
            return None
        return self.fetch_paper_by_id(match.group(1))
