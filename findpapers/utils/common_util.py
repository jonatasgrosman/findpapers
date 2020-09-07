import time
import re
import traceback
import logging
import os
import subprocess
import threading
from typing import Optional
from pathlib import Path


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


def try_success(function, attempts: Optional[int] = 1, pre_delay: Optional[int] = 0, next_try_delay: Optional[int] = 3):
    """
    Try to execute a function and repeat this execution if it raises any exception.
    This function will try N times to succeed, by provided number of attempts.

    Note: you can provide a delay time for pre and post function call,
    so the total delayed time between calls is pre_delay + next_try_delay

    Parameters
    ----------
    function : a common function
            A function that will be tried N times
    attempts : int, optional
            number of attempts, by default 1
    pre_delay : int, optional
            The delay before each function attempts in seconds, by default 0
    next_try_delay : int, optional
            The delay between function attempts in seconds, by default 3

    Returns
    -------
    Object or None
            This method returns the returned value of function or None if function raise Exception in all attempts
    """
    try:
        if attempts > 0:
            time.sleep(pre_delay)
            return function()
        return None
    except Exception as e:
        logging.debug(e, exc_info=True)
        time.sleep(next_try_delay)
        return try_success(function, attempts-1)


def clear(): # pragma: no cover
    """
    Clear the console
    """
    if os.name in ('nt', 'dos'):
        subprocess.call("cls")
    elif os.name in ('linux', 'osx', 'posix'):
        subprocess.call("clear")
    else:
        print('\n') * 120


def check_write_access(path: str):
    """
    Check if you can write on the provided path or raise an error otherwise

    Parameters
    ----------
    path : str
        A OS path

    Raises
    ------
    PermissionError
        If you can't write on the provided path
    """

    try:
        with open(path, 'a'): pass
    except Exception:
        raise PermissionError('You can\'t write on the provided path')


def logging_initialize(verbose: Optional[bool] = False):
    """
    Logging initialize method. If verbose mode is True the logging will be initialized on DEBUG mode. 
    Otherwise, INFO mode will be used

    Parameters
    ----------
    verbose : bool, optional
        If the logging needs to be verbose, by default False
    """

    logging.basicConfig(level=getattr(logging, 'DEBUG' if verbose else 'INFO'),
                        format='%(asctime)s %(levelname)s: %(message)s')


# Based on tornado.ioloop.IOLoop.instance() approach.
# See https://github.com/facebook/tornado
# Whole idea for this metaclass is taken from: https://stackoverflow.com/a/6798042/2402281
class ThreadSafeSingletonMetaclass(type):
    _instances = {}
    _singleton_lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        # double-checked locking pattern (https://en.wikipedia.org/wiki/Double-checked_locking)
        if cls not in cls._instances:
            with cls._singleton_lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super(ThreadSafeSingletonMetaclass, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
