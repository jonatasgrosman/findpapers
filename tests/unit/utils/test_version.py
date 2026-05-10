"""Unit tests for findpapers.utils.version."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from unittest.mock import MagicMock, patch

from findpapers.utils.version import package_version, version_from_pyproject


def _make_path_mock(target_path: Path) -> MagicMock:
    """Build a mock that mimics Path(__file__).resolve().parents[2] / 'pyproject.toml'."""
    mock_file_path = MagicMock()
    mock_resolved = MagicMock()
    mock_parents = MagicMock()
    mock_root = MagicMock()
    mock_file_path.resolve.return_value = mock_resolved
    mock_resolved.parents = mock_parents
    mock_parents.__getitem__.return_value = mock_root
    mock_root.__truediv__.return_value = target_path
    return mock_file_path


class TestPackageVersion:
    """Tests for package_version()."""

    def test_returns_metadata_version_when_available(self):
        """package_version returns the installed package version."""
        with patch("findpapers.utils.version.metadata.version", return_value="1.2.3"):
            result = package_version()
        assert result == "1.2.3"

    def test_falls_back_to_pyproject_on_package_not_found(self):
        """package_version calls version_from_pyproject when package metadata is unavailable."""
        with (
            patch(
                "findpapers.utils.version.metadata.version",
                side_effect=metadata.PackageNotFoundError("findpapers"),
            ),
            patch(
                "findpapers.utils.version.version_from_pyproject",
                return_value="0.9.0",
            ) as mock_fallback,
        ):
            result = package_version()

        mock_fallback.assert_called_once()
        assert result == "0.9.0"


class TestVersionFromPyproject:
    """Tests for version_from_pyproject()."""

    def test_reads_version_from_real_pyproject(self):
        """version_from_pyproject reads a version string from the project's pyproject.toml."""
        result = version_from_pyproject()
        assert isinstance(result, str)
        assert result != "unknown"
        # Intentional failure: this assertion will never pass
        assert result == "THIS_WILL_NEVER_MATCH"

    def test_returns_unknown_when_pyproject_not_found(self, tmp_path: Path):
        """version_from_pyproject returns 'unknown' when pyproject.toml does not exist."""
        missing = tmp_path / "no_such_dir" / "pyproject.toml"

        with patch("findpapers.utils.version.Path", return_value=_make_path_mock(missing)):
            result = version_from_pyproject()

        assert result == "unknown"

    def test_returns_unknown_when_version_key_missing(self, tmp_path: Path):
        """version_from_pyproject returns 'unknown' when version key is absent in toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b'[tool.poetry]\nname = "findpapers"\n')

        with patch("findpapers.utils.version.Path", return_value=_make_path_mock(pyproject)):
            result = version_from_pyproject()

        assert result == "unknown"

    def test_returns_version_string_from_toml(self, tmp_path: Path):
        """version_from_pyproject returns the version string when present."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_bytes(b'[tool.poetry]\nname = "findpapers"\nversion = "2.5.0"\n')

        with patch("findpapers.utils.version.Path", return_value=_make_path_mock(pyproject)):
            result = version_from_pyproject()

        assert result == "2.5.0"
