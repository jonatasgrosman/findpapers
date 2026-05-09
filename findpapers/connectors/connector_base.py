"""Abstract base class for external API connectors.

Provides shared HTTP infrastructure — rate limiting, credential injection,
request/response logging — so that every module that talks to an external
service inherits a consistent, production-ready networking layer.
"""

from __future__ import annotations

import contextlib
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from types import TracebackType
from urllib.parse import urlencode

import requests

from findpapers.utils.logging_config import SENSITIVE_PARAM_NAMES

logger = logging.getLogger(__name__)

# Alias kept for internal use; the canonical definition lives in
# findpapers.utils.logging_config so the SensitiveDataFilter can share it.
_SENSITIVE_PARAM_NAMES: frozenset[str] = SENSITIVE_PARAM_NAMES

# Header names (compared case-insensitively) that carry API credentials
# and must be redacted before logging.
_SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "x-els-apikey",
        "x-api-key",
        "x-apikey",
        "authorization",
    }
)


class ConnectorBase(ABC):
    """Abstract base class for external API connectors.

    Provides rate-limited HTTP helpers (``_get`` / ``_post``), automatic
    credential injection via ``_prepare_params`` / ``_prepare_headers``,
    and debug-level request/response logging with sensitive-parameter
    redaction.

    A :class:`requests.Session` is created lazily on the first HTTP call
    so that TCP+TLS connections are pooled and reused across requests to
    the same host.

    Subclasses must implement :attr:`name` and :attr:`min_request_interval`.
    """

    # Default HTTP timeout in seconds for all requests.  Subclasses or callers
    # can override by setting ``self._timeout`` in ``__init__``.
    _timeout: float = 30.0

    def __init__(self) -> None:
        """Initialise per-instance rate-limiter state and threading lock.

        Subclasses **must** call ``super().__init__()`` to ensure the
        rate-limiter and threading lock are properly initialised.
        """
        self._last_request_time: float = 0.0
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Retry configuration
    # ------------------------------------------------------------------

    # HTTP status codes that trigger an automatic retry.
    _retryable_status_codes: frozenset[int] = frozenset({429, 502, 503, 504})

    # Maximum number of retry attempts for connection errors / non-429 retryable
    # status codes (excluding the initial request).
    _max_retries: int = 3

    # Maximum number of retry attempts exclusively for HTTP 429 responses.
    # This budget is independent of _max_retries so that transient timeouts
    # do not consume the rate-limit retry allowance.
    _max_rate_limit_retries: int = 3

    # Base delay in seconds for exponential backoff (delay = base * 2^attempt).
    _retry_base_delay: float = 1.0

    # Base delay used when retrying HTTP 429 (rate-limited) responses.
    # Rate-limit back-off needs longer waits than generic transient errors.
    _rate_limit_base_delay: float = 5.0

    # Maximum delay cap in seconds to prevent excessively long waits.
    _retry_max_delay: float = 60.0

    # ------------------------------------------------------------------
    # HTTP Session (connection pooling)
    # ------------------------------------------------------------------

    def _get_session(self) -> requests.Session:
        """Return the shared :class:`requests.Session`, creating it lazily.

        Using a session allows ``urllib3`` to keep TCP+TLS connections alive
        across consecutive requests to the same host, which significantly
        reduces latency for connectors that issue many paginated calls.

        Returns
        -------
        requests.Session
            The reusable HTTP session bound to this connector instance.
        """
        # Instance attribute created on first access; avoids requiring
        # subclasses to call super().__init__().
        if not hasattr(self, "_http_session"):
            self._http_session = requests.Session()
        return self._http_session

    def close(self) -> None:
        """Close the underlying HTTP session, releasing pooled connections.

        Safe to call multiple times or even if no request was ever made.
        """
        if hasattr(self, "_http_session"):
            self._http_session.close()
            del self._http_session

    # Context-manager protocol so connectors can be used with ``with``.

    def __enter__(self) -> ConnectorBase:
        """Enter the runtime context and return the connector itself.

        Returns
        -------
        ConnectorBase
            ``self``, allowing ``with Connector() as c: ...`` usage.
        """
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit the runtime context, closing the HTTP session."""
        self.close()

    def __del__(self) -> None:
        """Best-effort cleanup: close the session when garbage-collected.

        This is a safety-net only; callers should prefer :meth:`close` or
        a ``with`` block for deterministic resource release.
        """
        self.close()

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable connector identifier used in log messages.

        Returns
        -------
        str
            Connector name (e.g. ``"arxiv"``, ``"crossref"``).
        """

    @property
    @abstractmethod
    def min_request_interval(self) -> float:
        """Minimum number of seconds that must elapse between consecutive HTTP requests.

        Returns
        -------
        float
            Interval in seconds.
        """

    def _get_lock(self) -> threading.Lock:
        """Return the per-instance threading lock.

        Returns
        -------
        threading.Lock
            The lock guarding rate-limiter state for this connector.
        """
        return self._lock

    def _rate_limit(self) -> None:
        """Enforce the minimum interval between HTTP requests.

        Thread-safe: uses a per-instance lock so concurrent threads sharing
        the same connector never violate the rate limit.
        """
        with self._get_lock():
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)

    def _retry_delay(
        self,
        attempt: int,
        response: requests.Response | None = None,
        *,
        base_delay: float | None = None,
    ) -> float:
        """Compute the delay before the next retry attempt.

        Uses exponential backoff with jitter.  If the response contains a
        ``Retry-After`` header (common with 429 responses), that value is
        used as the minimum delay.

        Parameters
        ----------
        attempt : int
            Zero-based retry attempt number (0 = first retry).
        response : requests.Response | None
            The HTTP response that triggered the retry, if available.
        base_delay : float | None
            Override the exponential-backoff base delay.  When ``None`` the
            instance attribute :attr:`_retry_base_delay` is used.

        Returns
        -------
        float
            Delay in seconds before the next retry.
        """
        effective_base = base_delay if base_delay is not None else self._retry_base_delay
        # Exponential backoff: base * 2^attempt, capped at max_delay.
        backoff: float = min(effective_base * (2**attempt), self._retry_max_delay)

        # Honour Retry-After header when present (429 responses).
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                # Non-numeric Retry-After (e.g. HTTP-date); ignore.
                with contextlib.suppress(ValueError, TypeError):
                    backoff = max(backoff, float(retry_after))

        # Add jitter (0–25 %) to avoid thundering-herd effects.
        # nosec B311 — random is intentionally used here for timing jitter only, not for
        # cryptographic or security-sensitive purposes.
        jitter: float = backoff * 0.25 * random.random()  # nosec B311
        return backoff + jitter

    def _request_with_retry(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        json_body: dict | list | None = None,
    ) -> requests.Response:
        """Execute an HTTP request with automatic retry on transient failures.

        Retries are triggered for status codes in :attr:`_retryable_status_codes`
        and for :class:`requests.ConnectionError` /
        :class:`requests.Timeout` exceptions.  Uses exponential backoff with
        jitter between attempts.

        HTTP 429 (rate-limited) responses use a **separate** retry counter
        (:attr:`_max_rate_limit_retries`) so that transient timeouts or
        connection errors do not consume the rate-limit retry allowance.
        The back-off base for 429 retries is :attr:`_rate_limit_base_delay`
        (typically larger than :attr:`_retry_base_delay`).

        Parameters
        ----------
        method : str
            HTTP method (``"GET"`` or ``"POST"``).
        url : str
            Target URL.
        params : dict | None
            Query parameters (already prepared).
        headers : dict | None
            HTTP headers (already prepared).
        json_body : dict | list | None
            JSON payload for POST requests.

        Returns
        -------
        requests.Response
            Successful HTTP response.

        Raises
        ------
        requests.HTTPError
            On non-2xx status codes after all retries are exhausted.
        requests.ConnectionError
            On persistent connection failures.
        requests.Timeout
            On persistent timeout failures.
        """
        # general_attempt counts retries for connection errors, timeouts, and
        # non-429 retryable status codes.
        # rate_limit_attempt counts retries exclusively for HTTP 429 so that
        # transient failures do not consume the rate-limit retry allowance.
        general_attempt: int = 0
        rate_limit_attempt: int = 0

        while True:
            try:
                self._rate_limit()
                self._log_request(url, params or None, method=method, headers=headers)

                if method == "POST":
                    response = self._get_session().post(
                        url,
                        json=json_body,
                        params=params or None,
                        headers=headers or None,
                        timeout=self._timeout,
                    )
                else:
                    response = self._get_session().get(
                        url,
                        params=params or None,
                        headers=headers or None,
                        timeout=self._timeout,
                    )

                with self._get_lock():
                    self._last_request_time = time.monotonic()
                self._log_response(response)

                if response.status_code == 429:
                    # 429 uses its own retry budget so general retries (e.g.
                    # timeouts on earlier attempts) do not exhaust it.
                    if rate_limit_attempt < self._max_rate_limit_retries:
                        delay = self._retry_delay(
                            rate_limit_attempt,
                            response,
                            base_delay=self._rate_limit_base_delay,
                        )
                        logger.debug(
                            "[%s] HTTP 429 from %s — retrying in %.1fs (attempt %d/%d).",
                            self.name,
                            url,
                            delay,
                            rate_limit_attempt + 1,
                            self._max_rate_limit_retries,
                        )
                        time.sleep(delay)
                        rate_limit_attempt += 1
                        continue
                    # Rate-limit retries exhausted — fall through to raise.

                elif (
                    response.status_code in self._retryable_status_codes
                    and general_attempt < self._max_retries
                ):
                    delay = self._retry_delay(general_attempt, response)
                    logger.warning(
                        "[%s] HTTP %d from %s — retrying in %.1fs (attempt %d/%d).",
                        self.name,
                        response.status_code,
                        url,
                        delay,
                        general_attempt + 1,
                        self._max_retries,
                    )
                    time.sleep(delay)
                    general_attempt += 1
                    continue
                    # General retries exhausted — fall through to raise.

                if not response.ok:
                    try:
                        body = response.json()
                    except ValueError:
                        body = response.text
                    logger.debug(
                        "[%s] HTTP %d response body from %s: %s",
                        self.name,
                        response.status_code,
                        url,
                        body,
                    )
                response.raise_for_status()
                return response

            except (requests.ConnectionError, requests.Timeout) as exc:
                if general_attempt < self._max_retries:
                    delay = self._retry_delay(general_attempt)
                    logger.warning(
                        "[%s] %s for %s — retrying in %.1fs (attempt %d/%d).",
                        self.name,
                        type(exc).__name__,
                        url,
                        delay,
                        general_attempt + 1,
                        self._max_retries,
                    )
                    time.sleep(delay)
                    general_attempt += 1
                    continue
                raise

    def _prepare_params(self, params: dict) -> dict:
        """Augment query parameters before the request is sent.

        The default implementation returns *params* unchanged.  Subclasses
        override this to inject API keys or other credentials into the query
        string.

        Parameters
        ----------
        params : dict
            Raw query parameters supplied by the caller.

        Returns
        -------
        dict
            Augmented parameters.
        """
        return params

    def _prepare_headers(self, headers: dict) -> dict:
        """Return a copy of the provided headers without modifications.

        Subclasses should call ``super()._prepare_headers(headers)`` and then
        add their own keys (API tokens, Accept types, etc.).

        Parameters
        ----------
        headers : dict
            Raw HTTP headers supplied by the caller.

        Returns
        -------
        dict
            Copy of the input headers.
        """
        return dict(headers)

    def _get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        """Perform a rate-limited, logged GET request with automatic retry.

        Calls :meth:`_prepare_params` and :meth:`_prepare_headers` so
        subclasses can inject credentials without duplicating the
        rate-limiting and logging boilerplate.  Transient failures
        (429, 502, 503, 504 and connection/timeout errors) are retried
        with exponential backoff.

        Parameters
        ----------
        url : str
            Target URL.
        params : dict | None
            Query parameters (before credential injection).
        headers : dict | None
            HTTP headers (before credential injection).

        Returns
        -------
        requests.Response
            HTTP response.

        Raises
        ------
        requests.HTTPError
            On non-2xx status codes after all retries are exhausted.
        """
        prepared_params = self._prepare_params(dict(params) if params else {})
        prepared_headers = self._prepare_headers(dict(headers) if headers else {})
        return self._request_with_retry(
            method="GET",
            url=url,
            params=prepared_params,
            headers=prepared_headers,
        )

    def _post(
        self,
        url: str,
        json_body: dict | list | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        """Perform a rate-limited, logged POST request with automatic retry.

        Mirrors :meth:`_get` but sends a JSON body via ``requests.post``.
        Calls :meth:`_prepare_params` and :meth:`_prepare_headers` for
        credential injection and browser-header defaults.

        Parameters
        ----------
        url : str
            Target URL.
        json_body : dict | list | None
            JSON-serialisable payload for the request body.
        params : dict | None
            Query parameters (before credential injection).
        headers : dict | None
            HTTP headers (before credential injection).

        Returns
        -------
        requests.Response
            HTTP response.

        Raises
        ------
        requests.HTTPError
            On non-2xx status codes after all retries are exhausted.
        """
        prepared_params = self._prepare_params(dict(params) if params else {})
        prepared_headers = self._prepare_headers(dict(headers) if headers else {})
        return self._request_with_retry(
            method="POST",
            url=url,
            params=prepared_params,
            headers=prepared_headers,
            json_body=json_body,
        )

    def _log_request(
        self,
        url: str,
        params: dict | None = None,
        method: str = "GET",
        headers: dict | None = None,
    ) -> None:
        """Log an outgoing HTTP request at ``DEBUG`` level.

        API keys and other sensitive parameters and headers are replaced with
        ``"***"`` so that credentials are never written to logs.

        Parameters
        ----------
        url : str
            Base request URL (without query string).
        params : dict | None
            Query parameters to be sent with the request.
        method : str
            HTTP method (e.g. ``"GET"`` or ``"POST"``).
        headers : dict | None
            HTTP headers to be sent with the request.
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return
        if params:
            safe_params = {
                k: "***" if k.lower() in _SENSITIVE_PARAM_NAMES else v for k, v in params.items()
            }
            full_url = f"{url}?{urlencode(safe_params)}"
        else:
            full_url = url
        logger.debug("[%s] %s %s", self.name, method, full_url)
        if headers:
            safe_headers = {
                k: "***" if k.lower() in _SENSITIVE_HEADER_NAMES else v for k, v in headers.items()
            }
            logger.debug("[%s] headers: %s", self.name, safe_headers)

    def _log_response(self, response: requests.Response) -> None:
        """Log a summary of an HTTP response at ``DEBUG`` level.

        Logs the HTTP status code, content-type header, and body size so that
        verbose sessions can trace what each request returned without printing
        the full body.

        Parameters
        ----------
        response : requests.Response
            The completed HTTP response to summarise.
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return
        status = f"{response.status_code} {response.reason}"
        content_type = response.headers.get("Content-Type", "unknown").split(";")[0].strip()
        size = len(response.content)
        logger.debug(
            "[%s] <- %s | content-type: %s | %d bytes",
            self.name,
            status,
            content_type,
            size,
        )
