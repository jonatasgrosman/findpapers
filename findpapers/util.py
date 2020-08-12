import time 
import re
import edlib
import traceback


def try_n(func, n=1, delay=3, print_error=True):
	try:
		if n > 0:
			time.sleep(delay)
			return func()
		return None
	except Exception as e:
		if print_error:
			print_exception(e)
		return try_n(func, n-1)


def try_to_return_or_none(func, print_error=True):
	try:
		return func()
	except Exception as e:
		if print_error:
			print_exception(e)
		return None


def get_numbers_from_string(string):
	return re.findall(r'\b\d+\b', string)


def get_numeric_month_by_string(string):
	months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
	return str(months.index(string[:3].lower()) + 1).zfill(2)


def print_exception(exception):
	error_traceback = traceback.TracebackException.from_exception(exception)
	print(f"Error: {exception} \n Traceback: {''.join(error_traceback.stack.format())}")