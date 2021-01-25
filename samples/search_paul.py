import findpapers
import datetime

search_file = "search_paul.json"
output_dir = "/some/valid/dir"
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
categories = {
    "Research Type": [
        "Validation Research", "Evaluation Research", "Solution Proposal", "Philosophical", "Opinion", "Experience"
    ],
    "Contribution": [
        "Metric", "Tool", "Model", "Method"
    ]
}
highlights = ["propose", "achiev", "accuracy", "method", "metric", "result", "limitation", "state of the art"]
verbose = False

# search
findpapers.search(search_file, query, since, until, limit, limit_per_database, databases, publication_types, scopus_api_token, ieee_api_token, verbose=verbose)

# refine
findpapers.refine(search_file, categories, highlights, show_abstract=True, show_extra_info=True, verbose=verbose)

# download
findpapers.download(search_file, output_dir, only_selected_papers=True, proxy=proxy, verbose=verbose)

# generate bibtex
findpapers.generate_bibtex(search_file, output_dir, only_selected_papers=True, add_findpapers_citation=True, verbose=verbose)