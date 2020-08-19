import findpapers
import datetime

query = '"machine learning" OR "deep learning"'
since = datetime.date(2019, 1, 1)
areas = ['computer_science']
scopus_api_token = None

findpapers.get(query, since, areas, scopus_api_token)