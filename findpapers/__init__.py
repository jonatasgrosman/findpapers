import os
import logging
from typing import Optional
from findpapers.tools.bibtex_generator_tool import generate_bibtex
from findpapers.tools.search_runner_tool import search
from findpapers.tools.refiner_tool import refine
from findpapers.tools.downloader_tool import download

## 09/17/2022 Disable importlib metadata check. This module is used as a relative import in the main package.
## try:
##     import importlib.metadata as importlib_metadata
## except ModuleNotFoundError:
##     import importlib_metadata
## 
## __version__ = importlib_metadata.version(__name__)
