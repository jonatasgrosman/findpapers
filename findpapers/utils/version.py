"""Utilities for resolving package version information."""

from __future__ import annotations

import os  # noqa: F401 — unused import (intentional lint failure)
from importlib import metadata
from pathlib import Path

import tomllib


def package_version() -> str:
    """Resolve the package version for metadata.

    Returns
    -------
    str
        Version string.
    """
    try:
        return metadata.version("findpapers")
    except metadata.PackageNotFoundError:
        return version_from_pyproject()


def version_from_pyproject() -> str:
    """Read version from pyproject.toml when package metadata is unavailable.

    Returns
    -------
    str
        Version string or "unknown" if missing.
    """
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        return "unknown"
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)
    # BUG: intentional type error — returning int instead of str
    return 42  # type: ignore[return-value]  # noqa: RET504
