#!/usr/bin/env python3
"""Fail if any Python source file under ``findpapers/`` or ``tests/`` contains
a non-ASCII character.

``ruff``'s ``RUF001``/``RUF002``/``RUF003`` rules only flag Unicode characters
that are visually confusable with a specific ASCII character (e.g. EN DASH
with HYPHEN-MINUS). They do not catch other non-ASCII punctuation commonly
pasted from rich text, such as EM DASH, arrows, ellipsis, or emoji. This
script closes that gap by rejecting any byte outside the ASCII range, as
required by the "Coding Rules" section of CONTRIBUTING.md.

Data fixtures (e.g. ``tests/data/**/*.json``) are intentionally out of scope:
they hold real records captured from external APIs and may legitimately
contain non-ASCII characters (e.g. paper titles, author names).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("findpapers", "tests")


def find_violations() -> list[tuple[Path, int, int, str]]:
    """Scan target directories and return every non-ASCII character found.

    Returns
    -------
    list[tuple[Path, int, int, str]]
        One entry per offending character: (file, line number, column
        number, the character itself).
    """
    violations: list[tuple[Path, int, int, str]] = []
    for scan_dir in SCAN_DIRS:
        for path in sorted((ROOT / scan_dir).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                for col_no, char in enumerate(line, start=1):
                    if ord(char) > 127:
                        violations.append((path.relative_to(ROOT), line_no, col_no, char))
    return violations


def main() -> int:
    """Run the scan and print any violations found.

    Returns
    -------
    int
        Process exit code: 0 when no violation is found, 1 otherwise.
    """
    violations = find_violations()
    if not violations:
        print("No non-ASCII characters found.")
        return 0

    for path, line_no, col_no, char in violations:
        print(f"{path}:{line_no}:{col_no}: non-ASCII character U+{ord(char):04X} ({char!r})")
    print(f"\nFound {len(violations)} non-ASCII character(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
