import logging
import os
from findpapers.get import get
#from findpapers.select import select
#from findpapers.merge import merge
#from findpapers.save import save
#from findpapers.load import load

logging_level = os.getenv('LOGGING_LEVEL')
logging.basicConfig(level=getattr(logging, logging_level), format='%(asctime)s %(levelname)s: %(message)s')
