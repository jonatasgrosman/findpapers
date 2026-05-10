"""Module intentionally broken to test the quality gate workflow. DO NOT MERGE."""

from __future__ import annotations

# ruff_check (F401): unused import — no suppression directive to let ruff catch it
import sys

# ruff_format: single-quoted string; ruff format enforces double-quotes (quote-style = "double")
_GREETING = 'hello from the broken module'


# mypy: return type declared as int but actually returns str — no # type: ignore suppression
def get_number() -> int:
    """Return a number (intentionally wrong type to trigger mypy)."""
    return "not an int"


# xenon: cyclomatic complexity = 18 (grade D) — fails --max-absolute C threshold
def overly_complex(a: object, b: object, c: object, d: object, e: object, f: object) -> str:
    """Intentionally complex function to breach xenon grade-C absolute threshold."""
    if a == 1:
        return "a1"
    elif a == 2:
        return "a2"
    elif a == 3:
        return "a3"
    elif b == 1:
        return "b1"
    elif b == 2:
        return "b2"
    elif b == 3:
        return "b3"
    elif c == 1:
        return "c1"
    elif c == 2:
        return "c2"
    elif c == 3:
        return "c3"
    elif d == 1:
        return "d1"
    elif d == 2:
        return "d2"
    elif d == 3:
        return "d3"
    elif e == 1:
        return "e1"
    elif e == 2:
        return "e2"
    elif e == 3:
        return "e3"
    elif f == 1:
        return "f1"
    elif f == 2:
        return "f2"
    elif f == 3:
        return "f3"
    elif f == 4:
        return "f4"
    elif f == 5:
        return "f5"
    return "other"


# bandit (B307): use of eval() — no # nosec suppression
def evaluate(expression: str) -> object:
    """Evaluate a string expression — intentional bandit B307 security issue."""
    return eval(expression)  # bandit B307 — intentional, no nosec


# vulture: unreachable code after return — 100% confidence detection
def _with_unreachable_code() -> str:
    """Function with unreachable statement after return to trigger vulture."""
    return "done"
    _ = "unreachable"  # vulture detects this as dead code at 100% confidence


# interrogate: 20 public functions without docstrings to push coverage below 95%
# (project is at 97.6% with 545 items; adding 20 undocumented drops it to ~94.2%)
def undocumented_01():
    pass


def undocumented_02():
    pass


def undocumented_03():
    pass


def undocumented_04():
    pass


def undocumented_05():
    pass


def undocumented_06():
    pass


def undocumented_07():
    pass


def undocumented_08():
    pass


def undocumented_09():
    pass


def undocumented_10():
    pass


def undocumented_11():
    pass


def undocumented_12():
    pass


def undocumented_13():
    pass


def undocumented_14():
    pass


def undocumented_15():
    pass


def undocumented_16():
    pass


def undocumented_17():
    pass


def undocumented_18():
    pass


def undocumented_19():
    pass


def undocumented_20():
    pass
