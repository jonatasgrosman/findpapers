import findpapers
import datetime

query = '("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing")'
since = datetime.date(2020, 1, 1)
until = datetime.date(2020, 12, 31)
limit = 50  # a just wanna 50 papers
limit_per_database = 10
scopus_api_token = None
ieee_api_token = None

search = findpapers.get(query, since, until, limit,
                        limit_per_database, scopus_api_token, ieee_api_token)

print(len(search.papers))
