import os
import datetime
import findpapers

query = '("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing")'
since = datetime.date(2020, 1, 1)
until = datetime.date(2020, 12, 31)
limit = 25
limit_per_database = 5
scopus_api_token = None
ieee_api_token = None

search = findpapers.run(query, since, until, limit,
                        limit_per_database, scopus_api_token, ieee_api_token)

filepath = 'some_search.json'
findpapers.save(search, filepath)
loaded_search = findpapers.load(filepath)

print(len(search.papers))
