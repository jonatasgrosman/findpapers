import os
import logging
from findpapers.utils.outputfile_util import save, load
from findpapers.utils.run_util import run
from findpapers.utils.refine_util import refine


logging_level = os.getenv('LOGGING_LEVEL')
if logging_level is None:  # pragma: no cover
    logging_level = 'INFO'

logging.basicConfig(level=getattr(logging, logging_level),
                    format='%(asctime)s %(levelname)s: %(message)s')
