import os
import logging
from findpapers.utils.outputfile_util import save, load, build_bibtex
from findpapers.utils.search_util import run, _get_paper_metadata_by_url
from findpapers.utils.refinement_util import refine
from findpapers.utils.download_util import download

VERBOSE =  os.getenv('FINDPAPERS_VERBOSE') is not None and os.getenv('FINDPAPERS_VERBOSE').lower() == 'true'

logging.basicConfig(level=getattr(logging, 'DEBUG' if VERBOSE else 'INFO'), format='%(asctime)s %(levelname)s: %(message)s')
