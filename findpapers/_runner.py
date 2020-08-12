from scrapper.scrapper import Scrapper
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

Scrapper.run(config)
