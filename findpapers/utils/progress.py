"""Utilities for creating consistently styled tqdm progress bars."""

from __future__ import annotations

from tqdm import tqdm


def make_progress_bar(
    desc: str | None = None,
    total: int | None = None,
    unit: str = "item",
    disable: bool = False,
    leave: bool = True,
    position: int | None = None,
) -> tqdm:
    """Create a tqdm progress bar with the project's standard style.

    Centralises all tqdm configuration so every runner produces visually
    uniform progress bars.  The shared defaults are:

    * ``leave=True``: the completed bar remains visible after finishing.
    * ``dynamic_ncols=True``: the bar adapts to the current terminal width.

    Parameters
    ----------
    desc : str | None
        Short label displayed before the bar (e.g. ``"Downloading"`` or a
        database name like ``"arxiv"``).  ``None`` omits the label.
    total : int | None
        Expected total number of units.  ``None`` leaves the bar in
        indeterminate mode.
    unit : str
        Singular label for one unit of work (e.g. ``"paper"``).
    disable : bool
        When ``True`` the progress bar is silenced: nothing is printed to
        stderr.  Useful for non-interactive environments or when log
        cleanliness is preferred.  Defaults to ``False``.
    leave : bool
        When ``True`` (default) the completed bar remains on screen.
        Pass ``False`` for transient bars that should clear themselves
        when done (e.g. per-item inner bars inside a larger loop).
    position : int | None
        Zero-based row offset for the bar.  ``None`` (default) lets tqdm
        assign the position automatically.  Set an explicit value when
        multiple bars must be shown simultaneously at fixed rows (e.g. one
        bar per parallel worker).

    Returns
    -------
    tqdm
        Configured, ready-to-use tqdm instance.  Callers are responsible
        for closing it (e.g. via a context manager or ``.close()``).

    Examples
    --------
    >>> pbar = make_progress_bar(desc="Downloading", total=100, unit="paper")
    >>> pbar.update(1)
    >>> pbar.close()
    """
    return tqdm(
        desc=desc,
        total=total,
        unit=unit,
        leave=leave,
        dynamic_ncols=True,
        disable=disable,
        position=position,
    )
