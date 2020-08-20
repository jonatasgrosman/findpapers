from searcher.searcher import Searcher
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

Searcher.run(config)
