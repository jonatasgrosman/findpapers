import time
import re
import edlib
import traceback
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_numeric_month_by_string(string: str) -> str:
    """
    Get a numeric month representation given a month string representation

    Parameters
    ----------
    string : str
       Month string representation (e.g., jan, january, Jan, Feb, December)

    Returns
    -------
    str
       A month numeric representation (e.g. jan -> 01)
        """

    months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
              'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

    return str(months.index(string[:3].lower()) + 1).zfill(2)


def try_with_repetitions(function, repetitions: Optional[int] = 1, delay: Optional[int] = 3):
    """
    Try to execute a function and repeat this execution if it raises any exception.
    This function will try N times to active success, given by provided number of repetitions.

    Parameters
    ----------
    function : a common function
            A function that will be tried N times
    repetitions : int, optional
            number of repetitions, by default 1
    delay : int, optional
            The delay between function attempts in seconds, by default 3

    Returns
    -------
    Object or None
            This method returns the returned value of function or None if function raise Exception in all attempts
    """
    try:
        if repetitions > 0:
            time.sleep(delay)
            return function()
        return None
    except Exception as e:
        logger.error(e)
        return try_with_repetitions(function, repetitions-1)
