import logging
import os
from findpapers.search_handler import run, save, load
#from findpapers.select import select

logging_level = os.getenv('LOGGING_LEVEL')
if logging_level is None:
    logging_level = 'INFO'

logging.basicConfig(level=getattr(logging, logging_level), format='%(asctime)s %(levelname)s: %(message)s')
