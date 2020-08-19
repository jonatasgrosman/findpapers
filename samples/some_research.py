import findpapers
import datetime

query = '("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing")'
since = datetime.date(2020, 1, 1)
areas = ['computer_science']
limit = 30 # a just wanna 30 papers
scopus_api_token = None

search = findpapers.get(query, since, areas, limit, scopus_api_token)

print(len(search.papers))