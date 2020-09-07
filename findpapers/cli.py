import typer
import re
import random
import logging
from datetime import datetime
from typing import Tuple, List
import findpapers
import findpapers.utils.common_util as common_util


app = typer.Typer()


@app.command("search")
def search(
    outputpath: str = typer.Argument(
        ..., help='A valid file path where the search result JSON file will be placed'
    ),
    query: str = typer.Argument(
        ..., help='A query string that will be used to perform the papers search. E.g. "term A" AND ("term B" OR "term C") AND NOT "term D"'
    ),
    since: datetime = typer.Option(
        None, "-s", "--since", show_default=True,
        help="A lower bound (inclusive) date that will be used to filter the search results. Following the pattern YYYY-MM-DD. E.g. 2020-12-31",
        formats=["%Y-%m-%d"]
    ),
    until: datetime = typer.Option(
        None, "-u", "--until", show_default=True,
        help="A upper bound (inclusive) date that will be used to filter the search results. Following the pattern YYYY-MM-DD. E.g. 2020-12-31",
        formats=["%Y-%m-%d"]
    ),
    limit: int = typer.Option(
        None, "-l", "--limit", show_default=True,
        help="The max number of papers to collect"
    ),
    limit_per_database: int = typer.Option(
        None, "-ld", "--limit_per_database", show_default=True,
        help="The max number of papers to collect per each database"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    ),
    scopus_api_token: str = typer.Option(
        None, "-ts", "--scopus_api_token", show_default=True,
        help="A API token used to fetch data from Scopus database. If you don't have one go to https://dev.elsevier.com and get it"
    ),
    ieee_api_token: str = typer.Option(
        None, "-te", "--ieee_api_token", show_default=True,
        help="A API token used to fetch data from IEEE database. If you don't have one go to https://developer.ieee.org and get it"
    )
):
    """
        Search for papers using a query.

        When you have a query and needs to get papers using it, this is the command that you'll need to call.
        This command will find papers from some databases based on the provided query.

        All the query terms need to be enclosed by single quotes (') and can be associated using boolean operators,
        and grouped using parentheses. The available boolean operators are "AND", "OR". "NOT".
        All boolean operators needs to be uppercased. The boolean operator "NOT" must be preceded by an "AND" operator.

        E.g.: 'term A' AND ('term B' OR 'term C') AND NOT 'term D'

        You can use some wildcards in the query too. Use ? to replace a single character or * to replace any number of characters.

        E.g.: 'son?' -> will match song, sons, ...

        E.g.: 'son*' -> will match song, sons, sonar, songwriting, ...

        Nowadays, we search for papers on ACM, arXiv, IEEE, PubMed, and Scopus database.
        The searching on IEEE and Scopus requires an API token, that must to be provided
        by the user using the -ts (or --scopus_api_token) and -te (or --ieee_api_token) arguments.
        If these tokens are not provided the search on these databases will be skipped.

        You can constraint the search by date using the -s (or --since) and -u (or --until) arguments
        following the pattern YYYY-MM-DD (E.g. 2020-12-31). 
        
        You can restrict the max number of retrived papers by using -l (or --limit).
        And, restrict the max number of retrived papers by database using -ld (or --limit_per_database) argument.

        You can control the command logging verbosity by the -v (or --verbose) argument.
    """

    try:
        common_util.logging_initialize(verbose)
        query = query.replace('\'', '"') # replacing single quotes by double quotes
        findpapers.search(outputpath, query, since.date(), until.date(),
                          limit, limit_per_database, scopus_api_token, ieee_api_token)
    except Exception as e:
        typer.echo(e)
        logging.debug(e, exc_info=True)
        raise typer.Exit(code=1)


@app.command("refine")
def refine(
    filepath: str = typer.Argument(
        ..., help='A valid file path for the search result file'
    ),
    show_abstract: bool = typer.Option(
        True, "-a", "--show_abstract", show_default=True,
        help="A flag to indicate if the abstract should be shown or not"
    ),
    categories: str = typer.Option(
        None, "-c", "--categories", show_default=True,
        help="A comma-separated list of categories to assign to the papers"
    ),
    highlights: str = typer.Option(
        None, "-h", "--highlights", show_default=True,
        help="A comma-separated list of terms to be highlighted on the abstract"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    )
):
    """
    Refine the search results by selecting/classifying the papers.

    When you have a search result and wanna refine it, this is the command that you'll need to call.
    This command will iterate through all the papers showing their collected data,
    then asking if you wanna select a particular paper or not

    You can show or hide the paper abstract by using the -a (or --abstract) flag.

    If a comma-separated list of categories is provided by the -c (or --categories) argument, 
    you can assign a category to the paper.

    And to help you on the refinement, this command can also highlight some terms on the paper's abstract 
    by a provided comma-separated list of them provided by the -h (or --highlights) argument.

    You can control the command logging verbosity by the -v (or --verbose) argument.
    """

    try:
        common_util.logging_initialize(verbose)
        categories = [x.strip() for x in categories.split(',')] if categories is not None else None
        highlights = [x.strip() for x in highlights.split(',')]if highlights is not None else None
        findpapers.refine(filepath, show_abstract, categories, highlights)
    except Exception as e:
        typer.echo(e)
        raise typer.Exit(code=1)


@app.command("download")
def download(
    filepath: str = typer.Argument(
        ..., help='A valid file path for the search result file'
    ),
    outputpath: str = typer.Argument(
        ..., help='A valid directory path where the downloaded papers will be placed'
    ),
    only_selected_papers: bool = typer.Option(
        False, "-s", "--selected", show_default=True,
        help="A flag to indicate if only selected papers (selections can be done on refine command) will be downloaded"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    )
):
    """
    Download papers using the search results.

    If you've done your search, (probably made the search refinement too) and wanna download the papers, 
    this is the command that you need to call. This command will try to download the PDF version of the papers to
    the output directory path.

    You can download only the selected papers by using the -s (or --selected) flag

    We use some heuristics to do our job, but sometime they won't work properly, and we cannot be able
    to download the papers, but we logging the downloads or failures in a file download.log
    placed on the output directory, you can check out the log to find what papers cannot be downloaded
    and try to get them manually later. 

    Note: Some papers are behind a paywall and won't be able to be downloaded by this command. 
    However, if you have a proxy provided for the institution where you study or work that permit you 
    to "break" this paywall. You can use this proxy configuration here
    by setting the environment variable FINDPAPERS_PROXY.
    
    You can control the command logging verbosity by the -v (or --verbose) argument.
    """

    try:
        common_util.logging_initialize(verbose)
        findpapers.download(filepath, outputpath, only_selected_papers)
    except Exception as e:
        typer.echo(e)
        raise typer.Exit(code=1)


@app.command("bibtex")
def bibtex(
    filepath: str = typer.Argument(
        ..., help='A valid file path for the search result file'
    ),
    outputpath: str = typer.Argument(
        ..., help='A valid directory path where the generated bibtex will be placed'
    ),
    only_selected_papers: bool = typer.Option(
        False, "-s", "--selected", show_default=True,
        help="A flag to indicate if only selected papers (selections be done on refine command) will be used for bibtex generation"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    )
):
    """
    Command used to generate a BibTeX file from a search result.

    You can generate the bibtex only for the selected papers by using the -s (or --selected) flag
    """

    try:
        common_util.logging_initialize(verbose)
        findpapers.generate_bibtex(
            filepath, outputpath, only_selected_papers)
    except Exception as e:
        typer.echo(e)
        raise typer.Exit(code=1)


def main():
    app()
