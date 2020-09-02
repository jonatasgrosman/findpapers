import os
import datetime
import requests
import findpapers


# query = '("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing")'
# since = datetime.date(2020, 1, 1)
# until = datetime.date(2020, 12, 31)
# limit = 25
# limit_per_database = 5
# scopus_api_token = None
# ieee_api_token = None

# search = findpapers.run(query, since, until, limit,
#                         limit_per_database, scopus_api_token, ieee_api_token)

filepath = 'some_search.json'
# findpapers.save(search, filepath)
loaded_search = findpapers.load(filepath)

# categories = ['Very nice work', 'Fine', 'Garbage']
# highlights = ['new', 'novel', 'achiev', 'result', 'state of art', 'SOTA', 'limitation', 'future']
# findpapers.refine(filepath, show_abstract=True, categories=categories, highlights=highlights)

print(len(loaded_search.papers))

dirname = os.path.dirname(__file__)
outputdir = filename = os.path.join(dirname, 'data')

proxies = {}

https_proxy = os.getenv('HTTPS_PROXY')
if https_proxy is not None:
    proxies['https'] = https_proxy

http_proxy = os.getenv('HTTP_PROXY')
if https_proxy is not None:
    proxies['http'] = http_proxy


requests_session = requests.Session()
requests_session.proxies.update(proxies)

findpapers.download(loaded_search, outputdir, False, requests_session)