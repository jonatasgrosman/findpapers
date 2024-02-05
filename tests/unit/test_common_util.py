import pytest
from typing import Callable, Any
import findpapers.utils.common_util as util


@pytest.mark.parametrize("string_format, numeric_format", [
    ("december", "12"),
    ("jan", "01"),
    ("February", "02"),
])
def test_get_numeric_month_by_string(string_format: str, numeric_format: str):

    assert util.get_numeric_month_by_string(string_format) == numeric_format


@pytest.mark.parametrize("func, result", [
    (lambda: None, None),
    (lambda: ":)", ":)"),
    (lambda: 10/0, None),  # forcing a ZeroDivisionError exception
])
def test_try_success(func: Callable, result: Any):

    assert util.try_success(func, 2, 1) == result
