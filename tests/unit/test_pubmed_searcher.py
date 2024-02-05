import copy
import datetime
import pytest
import findpapers.searchers.pubmed_searcher as pubmed_searcher
from findpapers.models.search import Search
from findpapers.models.publication import Publication

paper_entry = {
    "PubmedArticleSet": {
        "PubmedArticle": {
            "MedlineCitation": {
                "Article": {
                    "Journal": {
                        "Title": "fake publication title",
                        "ISSN": {
                            "#text": "fake-issn"
                        },
                        "JournalIssue": {
                            "PubDate": {
                                "Month": "Feb",
                                "Year": "2020"
                            }
                        }
                    },
                    "ArticleTitle": "fake paper title",
                    "ArticleDate": {
                        "Day": "01",
                        "Month": "02",
                        "Year": "2020",
                    },
                    "Abstract": {
                        "AbstractText": "fake paper abstract"
                    },
                    "AuthorList": {
                        "Author": [
                            {"ForeName": "author", "LastName": "A"},
                            {"ForeName": "author", "LastName": "B"}
                        ]
                    }
                },
                "KeywordList": {
                    "Keyword": [
                        {"#text": "term A"},
                        {"#text": "term B"}
                    ]
                }
            },
            "PubmedData": {
                "ArticleIdList": {
                    "ArticleId": [
                        {"@IdType": "doi", "#text": "fake-doi"}
                    ]
                }
            }
        }
    }
}


def test_mocks():

    assert pubmed_searcher._get_api_result() is not None


def test_get_search_url(search: Search):

    start_record = 50

    query = search.query.replace(" AND NOT ", " NOT ")

    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query} AND has abstract [FILT] AND \"journal article\"[Publication Type]"
    url += f" AND {search.since.strftime('%Y/%m/%d')}:{search.until.strftime('%Y/%m/%d')}[Date - Publication]"
    url += f"&retstart={start_record}&retmax=50&sort=pub+date"

    assert pubmed_searcher._get_search_url(search, start_record) == url


def test_get_publication():

    publication = pubmed_searcher._get_publication(paper_entry)

    assert publication.title == "fake publication title"
    assert publication.issn == "fake-issn"
    assert publication.isbn is None
    assert publication.publisher is None
    assert publication.category == "Journal"


def test_get_paper(publication: Publication):

    paper = pubmed_searcher._get_paper(paper_entry, publication)

    assert paper.publication == publication

    assert paper.title == "fake paper title"
    assert paper.publication_date == datetime.date(2020, 2, 1)
    assert paper.doi == "fake-doi"
    assert paper.citations is None
    assert paper.abstract == "fake paper abstract"
    assert len(paper.authors) == 2
    assert "author A" in paper.authors
    assert len(paper.keywords) == 2
    assert "term A" in paper.keywords
    assert len(paper.urls) == 0

    alternative_paper_entry = copy.deepcopy(paper_entry)
    del alternative_paper_entry["PubmedArticleSet"]["PubmedArticle"]["MedlineCitation"]["Article"]["ArticleDate"]
    alternative_paper_entry["PubmedArticleSet"]["PubmedArticle"][
        "MedlineCitation"]["Article"]["Abstract"]["AbstractText"] = [{"#text": "fake paper abstract"}, {"#text": None}]
    del alternative_paper_entry["PubmedArticleSet"]["PubmedArticle"]["MedlineCitation"]["KeywordList"]

    paper = pubmed_searcher._get_paper(alternative_paper_entry, publication)
    assert paper.publication_date == datetime.date(2020, 2, 1)
    assert paper.abstract == "fake paper abstract\n"

    alternative_paper_entry = copy.deepcopy(paper_entry)
    alternative_paper_entry["PubmedArticleSet"]["PubmedArticle"][
        "MedlineCitation"]["Article"]["ArticleDate"]["Month"] = "INVALID MONTH"

    paper = pubmed_searcher._get_paper(alternative_paper_entry, publication)
    assert paper.publication_date == datetime.date(2020, 1, 1)


def test_run(search: Search):

    search.limit = 51
    pubmed_searcher.run(search)

    assert len(search.papers) == 51
