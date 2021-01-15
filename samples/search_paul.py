import findpapers
import datetime

search_file = "search_paul.json"
download_output_dir = "/some/valid/dir"
query = "([artificial intelligence] OR [AI] OR [machine learning] OR [ML] OR [deep learning] OR [DL]) AND [rock] AND ([music] OR [song]) AND NOT [drum*]"
since = datetime.date(2000, 1, 1)
until = datetime.date(2020, 12, 31)
proxy = "https://mccartney:super_secret_pass@liverpool.ac.uk:1234"
scopus_api_token = "SOME_SUPER_SECRET_TOKEN"
ieee_api_token = "SOME_SUPER_SECRET_TOKEN"
limit = 100
limit_per_database = 4
databases = ["acm", "ieee", "scopus"]
publication_types = ["journal", "conference proceedings"]
findpapers.utils.common_util.logging_initialize(True) #verbose

# search
findpapers.search(search_file, query, since, until, limit, limit_per_database, databases, publication_types, scopus_api_token, ieee_api_token)

# refine
findpapers.refine(search_file, show_abstract=True, show_extra_info=True)

# download
findpapers.download(search_file, download_output_dir, only_selected_papers=True, proxy=proxy)
