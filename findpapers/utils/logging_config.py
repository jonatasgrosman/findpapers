"""Shared logging configuration utilities for runners."""

from __future__ import annotations

import logging
import re
import sys
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Third-party loggers that produce excessive output at DEBUG level.
_NOISY_LOGGERS = ("urllib3", "requests", "curl_cffi", "charset_normalizer")

# Query-parameter names (compared case-insensitively) that contain API
# credentials and must never appear in log output.
SENSITIVE_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "x-api-key",
        "x-els-apikey",
    }
)

# Matches http/https URLs (including query strings) inside larger strings.
_URL_PATTERN: re.Pattern[str] = re.compile(r"https?://[^\s'\"<>]+")


def _sanitize_url(url: str) -> str:
    """Return *url* with sensitive query-parameter values replaced by ``"***"``.

    Parameters
    ----------
    url : str
        A single URL, possibly containing a query string.

    Returns
    -------
    str
        The URL with any sensitive query-parameter values redacted.
    """
    parsed = urlparse(url)
    if not parsed.query:
        return url
    params = parse_qs(parsed.query, keep_blank_values=True)
    sanitized = {k: ["***"] if k.lower() in SENSITIVE_PARAM_NAMES else v for k, v in params.items()}
    return urlunparse(parsed._replace(query=urlencode(sanitized, doseq=True)))


def sanitize_message(text: str) -> str:
    """Replace sensitive query-parameter values in any URLs found in *text*.

    Scans *text* for ``http://`` / ``https://`` URLs and redacts the values of
    any query parameters whose names are in :data:`SENSITIVE_PARAM_NAMES`.
    All other content is left unchanged.

    Parameters
    ----------
    text : str
        Arbitrary text that may contain one or more URLs.

    Returns
    -------
    str
        A copy of *text* with sensitive URL parameters replaced by ``"***"``.
    """
    return _URL_PATTERN.sub(lambda m: _sanitize_url(m.group()), text)


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts API keys from URLs in every log record.

    Applies :func:`sanitize_message` to the formatted log message so that
    sensitive query parameters (e.g. ``apikey``) are never written to any
    log handler, regardless of which module emitted the record.

    The filter modifies ``record.msg`` and clears ``record.args`` so that the
    sanitized text is the final rendered message.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize sensitive data in *record* and allow it through.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to sanitize in place.

        Returns
        -------
        bool
            Always ``True``: every record is allowed through after sanitization.
        """
        # Render the full message first so we can sanitize the final string
        # without having to inspect the (potentially heterogeneous) args.
        record.msg = sanitize_message(record.getMessage())
        record.args = None
        return True


class _SanitizingHandler(logging.Handler):
    """No-output handler that sanitizes all findpapers log records in-place.

    Python logging filters attached to a logger are **not** invoked for records
    that propagate up from child loggers, only handlers are.  By installing
    this handler on the top-level ``findpapers`` logger, every record emitted
    anywhere in the package (e.g. ``findpapers.connectors.ieee``) passes
    through :func:`sanitize_message` before reaching the real output handlers
    on the root logger.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Sanitize *record* in-place; produce no output.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to sanitize in place.
        """
        record.msg = sanitize_message(record.getMessage())
        record.args = None


def configure_verbose_logging() -> None:
    """Enable DEBUG-level logging while suppressing noisy third-party loggers.

    Sets the root logger to DEBUG, adds a stderr ``StreamHandler`` when none
    exists (so DEBUG records are actually emitted), and restricts known noisy
    HTTP-related loggers to WARNING so that only findpapers' own debug
    messages appear.

    The ``_SanitizingHandler`` installed on the ``findpapers`` logger ensures
    that API credentials are redacted before records reach the stream handler.
    Calling this function multiple times is safe: the stream handler is only
    added once.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Only add a stderr handler when root has no console handler yet, which
    # avoids double-printing in environments that already configure one (e.g.
    # pytest, Django). logging_redirect_tqdm will temporarily replace this
    # handler with a tqdm-safe variant during parallel execution.
    _has_console_handler = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        and getattr(h, "stream", None) in {sys.stdout, sys.stderr}
        for h in root.handlers
    )
    if not _has_console_handler:
        _handler = logging.StreamHandler()
        _handler.setLevel(logging.DEBUG)
        root.addHandler(_handler)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


# Install the sanitizing handler on the findpapers package logger.
# Using a Handler (not a Filter) is intentional: logger-level filters are only
# applied to records emitted directly at that logger, whereas handlers receive
# all propagated records from the entire child-logger hierarchy.
logging.getLogger("findpapers").addHandler(_SanitizingHandler())
