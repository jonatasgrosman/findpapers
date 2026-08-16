"""Shared logging helpers for connectors' paginated search loops.

Every search connector implements its own ``while True`` pagination loop
(with different position semantics: page number, offset, or cursor/token),
but they all share the same two silent-failure shapes:

1. A request that errors out mid-pagination.
2. A page that comes back empty *before* the API's own reported total is
   reached (as opposed to a normal, expected end of results).

Both cases previously stopped pagination with little or no log output,
leaving callers (and progress bars relying on the connector's self-reported
total) with no indication that a search stopped short. Centralising the
message here keeps the wording consistent across connectors and means each
one only has to pass in its own pagination-position semantics.
"""

from __future__ import annotations

import logging


def log_pagination_request_failure(
    logger: logging.Logger,
    *,
    connector_label: str,
    processed: int,
    total: int | None,
    position_label: str,
    position: object,
    exc: Exception,
) -> None:
    """Log a paginated request failure, including how much was retrieved.

    Parameters
    ----------
    logger : logging.Logger
        The calling connector's module logger.
    connector_label : str
        Human-readable connector name for the message (e.g. ``"WoS"``).
    processed : int
        Number of items retrieved before the failure.
    total : int | None
        Estimated total the API reported, if known.
    position_label : str
        Name of the pagination position parameter (e.g. ``"page"``,
        ``"offset"``, ``"cursor"``, ``"token"``).
    position : object
        Value of the pagination position parameter at the time of failure.
    exc : Exception
        The exception raised while requesting the page.
    """
    logger.warning(
        "%s: search stopped early after retrieving %d of an estimated %s "
        "papers (request for %s=%s failed: %s). Returning the papers "
        "collected so far.",
        connector_label,
        processed,
        total if total is not None else "unknown",
        position_label,
        position,
        exc,
    )
    logger.debug("%s request exception details:", connector_label, exc_info=True)


def log_pagination_empty_before_total(
    logger: logging.Logger,
    *,
    connector_label: str,
    processed: int,
    total: int | None,
    position_label: str,
    position: object,
) -> None:
    """Log a warning when a page comes back empty before the reported total.

    A no-op when ``total`` is unknown or already reached - that's simply a
    normal end of results, not something worth flagging.

    Parameters
    ----------
    logger : logging.Logger
        The calling connector's module logger.
    connector_label : str
        Human-readable connector name for the message (e.g. ``"WoS"``).
    processed : int
        Number of items retrieved so far.
    total : int | None
        Estimated total the API reported, if known.
    position_label : str
        Name of the pagination position parameter.
    position : object
        Value of the pagination position parameter for the empty page.
    """
    if total is not None and processed < total:
        logger.warning(
            "%s: API returned no more results after %d of an estimated %d "
            "(%s=%s). This may indicate a pagination limit on the %s side "
            "rather than an error.",
            connector_label,
            processed,
            total,
            position_label,
            position,
            connector_label,
        )
