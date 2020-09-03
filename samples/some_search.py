import os
import datetime
import requests
import findpapers

dirname = os.path.dirname(__file__)
search_filepath = filename = os.path.join(dirname, 'paul_search.json')
bibtex_filepath = filename = os.path.join(dirname, 'paul_search.bib')

# query = '("machine learning" OR "deep learning") AND "music" AND NOT "drum*"'
# since = datetime.date(2019, 1, 1)
# until = datetime.date(2020, 12, 31)
# limit = 100
# limit_per_database = 20
# scopus_api_token = None
# ieee_api_token = None

# search = findpapers.run(query, since, until, limit,
#                         limit_per_database, scopus_api_token, ieee_api_token)

# findpapers.save(search, search_filepath)
# print(len(search.papers))


# loaded_search = findpapers.load(search_filepath)
# print(len(loaded_search.papers))


# categories = ['Very nice work', 'Fine', 'Garbage']
# highlights = ['new', 'novel', 'achiev', 'result', 'state of art', 'SOTA', 'limitation', 'future']
# findpapers.refine(filepath, show_abstract=True, categories=categories, highlights=highlights)


# outputdir = filename = os.path.join(dirname, 'data')

# proxies = {}

# https_proxy = os.getenv('HTTPS_PROXY_URL')
# if https_proxy is not None:
#     proxies['https'] = https_proxy

# http_proxy = os.getenv('HTTPS_PROXY_URL')
# if https_proxy is not None:
#     proxies['http'] = http_proxy

# requests_session = requests.Session()
# requests_session.proxies.update(proxies)

# findpapers.download(loaded_search, outputdir, False, requests_session)




findpapers.build_bibtex(search_filepath, bibtex_filepath)
