import json
import copy
import tempfile
import findpapers
from findpapers.models.search import Search
from findpapers.models.paper import Paper
import findpapers.utils.persistence_util as persistence_util


def test_output(search: Search, paper: Paper):

    paper.publication.category = "Journal"
    search.add_paper(paper)

    other_paper = copy.deepcopy(paper)
    other_paper.publication.issn = "ISSN-CONF"
    other_paper.publication.category = "Conference Proceedings"
    other_paper.title = "Conference paper title"
    other_paper.doi = "fake-doi-conference-paper"
    search.add_paper(other_paper)

    other_paper = copy.deepcopy(paper)
    other_paper.publication.issn = "ISSN-BOOK"
    other_paper.publication.category = "Book"
    other_paper.title = "Book paper title"
    other_paper.doi = "fake-doi-book-paper"
    search.add_paper(other_paper)

    other_paper = copy.deepcopy(paper)
    other_paper.publication = None
    other_paper.title = "Unpublished paper title"
    other_paper.doi = None
    search.add_paper(other_paper)

    search_path = tempfile.NamedTemporaryFile().name
    outputpath = tempfile.NamedTemporaryFile().name
    
    persistence_util.save(search, search_path)

    findpapers.generate_bibtex(search_path, outputpath)
    with open(outputpath) as fp:
        generated_bibtex = fp.read()

    article_header = "@article{drpaul1969awesome"
    inproceedings_header = "@inproceedings{drpaul1969conference"
    book_header = "@book{drpaul1969book"
    unpublished = "@unpublished{drpaul1969unpublished"

    assert article_header in generated_bibtex
    assert inproceedings_header in generated_bibtex
    assert book_header in generated_bibtex
    assert unpublished in generated_bibtex

