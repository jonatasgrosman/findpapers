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
    query: str = typer.Option(
        None, "-q", "--query", show_default=True,
        help='A query string that will be used to perform the papers search (If not provided it will be loaded from the environment variable FINDPAPERS_QUERY). E.g. [term A] AND ([term B] OR [term C]) AND NOT [term D]'
    ),
    query_filepath: str = typer.Option(
        None, "-f", "--query-file", show_default=True,
        help='A file path that contains the query string that will be used to perform the papers search'
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
        None, "-ld", "--limit-db", show_default=True,
        help="The max number of papers to collect per each database"
    ),
    databases: str = typer.Option(
        None, "-d", "--databases", show_default=True,
        help="A comma-separated list of databases where the search should be performed, if not specified all databases will be used (this parameter is case insensitive)"
    ),
    publication_types: str = typer.Option(
        None, "-p", "--publication-types", show_default=True,
        help="A comma-separated list of publication types to filter when searching, if not specified all the publication types will be collected (this parameter is case insensitive). The available publication types are: journal, conference proceedings, book, other"
    ),
    scopus_api_token: str = typer.Option(
        None, "-ts", "--token-scopus", show_default=True,
        help="A API token used to fetch data from Scopus database. If you don't have one go to https://dev.elsevier.com and get it. (If not provided it will be loaded from the environment variable FINDPAPERS_SCOPUS_API_TOKEN)"
    ),
    ieee_api_token: str = typer.Option(
        None, "-ti", "--token-ieee", show_default=True,
        help="A API token used to fetch data from IEEE database. If you don't have one go to https://developer.ieee.org and get it. (If not provided it will be loaded from the environment variable FINDPAPERS_IEEE_API_TOKEN)"
    ),
    proxy: str = typer.Option(
        None, "-x", "--proxy", show_default=True,
        help="proxy URL that can be used during requests"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    )
):
    """
        Search for papers metadata using a query.

        When you have a query and needs to get papers using it, this is the command that you'll need to call.
        This command will find papers from some databases based on the provided query.

        All the query terms need to be enclosed by square brackets and can be associated using boolean operators,
        and grouped using parentheses. The available boolean operators are "AND", "OR". "NOT".
        All boolean operators needs to be uppercased. The boolean operator "NOT" must be preceded by an "AND" operator.

        E.g.: [term A] AND ([term B] OR [term C]) AND NOT [term D]

        You can use some wildcards in the query too. Use ? to replace a single character or * to replace any number of characters.

        E.g.: 'son?' -> will match song, sons, ...

        E.g.: 'son*' -> will match song, sons, sonar, songwriting, ...

        Nowadays, we search for papers on ACM, arXiv, IEEE, PubMed, and Scopus database.
        The searching on IEEE and Scopus requires an API token, that must to be provided
        by the user using the -ts (or --scopus_api_token) and -te (or --ieee_api_token) arguments.
        If these tokens are not provided the search on these databases will be skipped.

        You can constraint the search by date using the -s (or --since) and -u (or --until) arguments
        following the pattern YYYY-MM-DD (E.g. 2020-12-31). 
        
        You can restrict the max number of retrieved papers by using -l (or --limit).
        And, restrict the max number of retrieved papers by database using -ld (or --limit_per_database) argument.

        You can control which databases you would like to use in your search by the -d (or --databases) option. This parameter
        accepts a comma-separated list of database names, and is case-insensitive. Nowadays the available databases are
        ACM, arXiv, IEEE, PubMed, Scopus

        E.g.:
        --databases "scopus,arxiv,acm"
        --databases "ieee,ACM,PubMed"

        You can control which publication types you would like to fetch in your search by the -p (or --publication-types) option. This parameter
        accepts a comma-separated list of database names, and is case-insensitive. Nowadays the available publication types are
        journal, conference proceedings, book, other. 
        When a particular publication does not fit into any of the other types it is classified as "other", e.g., magazines, newsletters, unpublished manuscripts.

        E.g.:
        --publication-types "journal,conference proceedings,BOOK,other"
        --publication-types "Journal,book"

        You can control the command logging verbosity by the -v (or --verbose) argument.
    """

    try:
        since = since.date() if since is not None else None
        until = until.date() if until is not None else None
        databases = [x.strip() for x in databases.split(',')] if databases is not None else None
        publication_types = [x.strip() for x in publication_types.split(',')] if publication_types is not None else None

        common_util.logging_initialize(verbose)

        if query is None and query_filepath is not None:
            with open(query_filepath, 'r') as f:
                query = f.read().strip()

        findpapers.search(outputpath, query, since, until, limit, limit_per_database,
                          databases, publication_types, scopus_api_token, ieee_api_token, proxy)
    except Exception as e:
        if verbose:
            logging.debug(e, exc_info=True)
        else:
            typer.echo(e)
        raise typer.Exit(code=1)


@app.command("refine")
def refine(
    filepath: str = typer.Argument(
        ..., help='A valid file path for the search result file'
    ),
    categories: List[str] = typer.Option(
        [], "-c", "--categories", show_default=True,
        help="A comma-separated list of categories to assign to the papers with their facet following the pattern: <facet>:<term_b>,<term_c>,..."
    ),
    highlights: str = typer.Option(
        None, "-h", "--highlights", show_default=True,
        help="A comma-separated list of terms to be highlighted on the abstract"
    ),
    show_abstract: bool = typer.Option(
        False, "-a", "--abstract", show_default=True,
        help="A flag to indicate if the paper's abstract should be shown or not"
    ),
    show_extra_info: bool = typer.Option(
        False, "-e", "--extra-info", show_default=True,
        help="A flag to indicate if the paper's extra info should be shown or not"
    ),
    only_selected_papers: bool = typer.Option(
        False, "-s", "--selected", show_default=True,
        help="If only the selected papers will be refined"
    ),
    only_removed_papers: bool = typer.Option(
        False, "-r", "--removed", show_default=True,
        help="If only the removed papers will be refined"
    ),
    read_only: bool = typer.Option(
        False, "-l", "--list", show_default=True,
        help="If this flag is present, this function call will only list the papers"
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
    you can assign a category to the paper. You need to define these categories following the pattern: <facet>:<term_b>,<term_c>,...

    E.g.: 
    --categories "Contribution:Metric,Tool,Model,Method"
    --categories "Research Type:Validation Research,Evaluation Research,Solution Proposal,Philosophical,Opinion,Experience"
    
    The -c parameter can be defined several times, so you can define as many facets as you want
    The -c parameter is case-sensitive.

    And to help you on the refinement, this command can also highlight some terms on the paper's abstract 
    by a provided comma-separated list of them provided by the -h (or --highlights) argument.

    You can control the command logging verbosity by the -v (or --verbose) argument.
    """

    try:
        common_util.logging_initialize(verbose)
        highlights = [x.strip() for x in highlights.split(',')] if highlights is not None else None
        
        categories_by_facet = {} if len(categories) > 0 else None
        for categories_string in categories:
            string_split = categories_string.split(':')
            facet = string_split[0].strip()
            categories_by_facet[facet] = [x.strip() for x in string_split[1].split(',')]

        findpapers.refine(filepath, categories_by_facet, highlights, show_abstract, show_extra_info, only_selected_papers, only_removed_papers, read_only)
    except Exception as e:
        if verbose:
            logging.debug(e, exc_info=True)
        else:
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
    categories: List[str] = typer.Option(
        [], "-c", "--categories", show_default=True,
        help="A comma-separated list of categories (categorization can be done on refine command) that will be used to filter which papers will be downloaded, using the following pattern: <facet>:<term_b>,<term_c>,..."
    ),
    proxy: str = typer.Option(
        None, "-x", "--proxy", show_default=True,
        help="proxy URL that can be used during requests"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    )
):
    """
    Download full-text papers using the search results.

    If you've done your search, (probably made the search refinement too) and wanna download the papers, 
    this is the command that you need to call. This command will try to download the PDF version of the papers to
    the output directory path.

    You can download only the selected papers by using the -s (or --selected) flag

    You can filter which kind of categorized papers will be downloaded providing 
    a comma-separated list of categories is provided by the -c (or --categories) argument, 
    You need to define these categories following the pattern: <facet>:<term_b>,<term_c>,...

    E.g.: 
    --categories "Contribution:Metric,Tool"
    
    The -c parameter can be defined several times, so you can define as many filters as you want
    The -c parameter is case-sensitive.

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

        categories_by_facet = {} if len(categories) > 0 else None
        for categories_string in categories:
            string_split = categories_string.split(':')
            facet = string_split[0].strip()
            categories_by_facet[facet] = [x.strip() for x in string_split[1].split(',')]

        findpapers.download(filepath, outputpath, only_selected_papers, categories_by_facet, proxy)
    except Exception as e:
        if verbose:
            logging.debug(e, exc_info=True)
        else:
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
    categories: List[str] = typer.Option(
        [], "-c", "--categories", show_default=True,
        help="A comma-separated list of categories (categorization can be done on refine command) that will be used to filter which papers will be used for bibtex generation, using the following pattern: <facet>:<term_b>,<term_c>,..."
    ),
    add_findpapers_citation: bool = typer.Option(
        False, "-f", "--findpapers", show_default=True,
        help="A flag to indicate if you want to add an entry for Findpapers in your BibTeX output file"
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", show_default=True,
        help="If you wanna a verbose mode logging"
    )
):
    """
    Generate a BibTeX file from the search results.

    You can generate the bibtex only for the selected papers by using the -s (or --selected) flag

    You can filter which kind of categorized papers will be used for bibtex generation providing 
    a comma-separated list of categories is provided by the -c (or --categories) argument, 
    You need to define these categories following the pattern: <facet>:<term_b>,<term_c>,...

    E.g.: 
    --categories "Contribution:Metric,Tool"
    
    The -c parameter can be defined several times, so you can define as many filters as you want.
    The -c parameter is case-sensitive.

    You can control the command logging verbosity by the -v (or --verbose) argument.

    """

    try:
        common_util.logging_initialize(verbose)

        categories_by_facet = {} if len(categories) > 0 else None
        for categories_string in categories:
            string_split = categories_string.split(':')
            facet = string_split[0].strip()
            categories_by_facet[facet] = [x.strip() for x in string_split[1].split(',')]
        
        findpapers.generate_bibtex(filepath, outputpath, only_selected_papers, categories_by_facet, add_findpapers_citation)
    except Exception as e:
        if verbose:
            logging.debug(e, exc_info=True)
        else:
            typer.echo(e)
        raise typer.Exit(code=1)


@app.command("version")
def version():
    """
    Show current findpapers version
    """

    typer.echo(f"findpapers {findpapers.__version__}")
    

def main():
    app()
