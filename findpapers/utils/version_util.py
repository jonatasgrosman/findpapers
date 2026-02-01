"""Utilities for resolving package version information."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

import tomli


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
        data = tomli.load(handle)
    return str(data.get("tool", {}).get("poetry", {}).get("version", "unknown"))
