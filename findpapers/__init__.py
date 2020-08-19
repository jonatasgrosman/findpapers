import logging
import os
from findpapers.get import get
#from findpapers.select import select
#from findpapers.merge import merge
#from findpapers.save import save
#from findpapers.load import load

#evaluate the inclusion of
#https://dev.springernature.com/
#https://developer.ieee.org/

logging_level = os.getenv('LOGGING_LEVEL')

if logging_level is None or len(logging_level.strip()) == 0 or logging_level.strip() == 'INFO':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')
else:
    logging.basicConfig(level=getattr(logging, logging_level), format='%(asctime)s %(name)s %(levelname)s:%(message)s')
