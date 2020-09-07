# Findpapers

Findpapers is a console application that helps researchers find papers by submitting a single query to multiple databases (currently ACM, arXiv, IEEE, PubMed, and Scopus)

## Requirements

- Python 3.7+

## Installation

```console
$ pip install findpapers
```

## Usage

We basically have 4 basic commands available in the tool:

- ```findpapers search```

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

    Usage example:

    ```console
    $ findpapers search /some/path/search.json "('machine learning' OR 'deep learning') AND 'music' AND NOT 'drum*'" -s 2019-01-01 -u 2020-12-31 -ld 100 -v -ts VALID_SCOPUS_API_TOKEN -te VALID_IEEE_API_TOKEN
    ```

- ```findpapers refine```

    When you have a search result and wanna refine it, this is the command that you'll need to call.
    This command will iterate through all the papers showing their collected data,
    then asking if you wanna select a particular paper or not

    You can show or hide the paper abstract by using the -a (or --abstract) flag.

    If a comma-separated list of categories is provided by the -c (or --categories) argument, 
    you can assign a category to the paper.

    And to help you on the refinement, this command can also highlight some terms on the paper's abstract 
    by a provided comma-separated list of them provided by the -h (or --highlights) argument.

    ```console
    $ findpapers refine /some/path/search.json -c "Category A, Category B" -h "result, state of art, improve, better" -v
    ```

- ```findpapers download```

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

    ```console
    $ findpapers download /some/path/search.json /some/path/papers/ -s -v
    ```

- ```findpapers download```

    Command used to generate a BibTeX file from a search result.

    You can generate the bibtex only for the selected papers by using the -s (or --selected) flag

    ```console
    $ findpapers bibtex /some/path/search.json /some/path/mybib.bib -s -v
    ```

More details about the commands can be found by running ```findpapers [command] --help```. 

You can control the commands logging verbosity by the -v (or --verbose) argument.

I know that this documentation is boring and incomplete, and it needs to be improved.
I just don't have time to do this for now. But if you wanna help me with it see the [contribution guidelines](https://gitlab.com/jonatasgrosman/findpapers/-/blob/master/CONTRIBUTING.md).


## FAQ

- I don't have the API token for Scopus and IEEE databases, how do I get them?

    Go to https://dev.elsevier.com and https://developer.ieee.org to get them

- When I tried to download the papers collected in my search, most of them were not downloaded, why did this happen?

    Most papers are behind a paywall, so you may not have access to download them using the network you're connected to. However, this problem can be worked around, if you have a proxy from the institution where you work/study that has broader access to these databases, you only need to define a environment variable called FINDPAPERS_PROXY with the URL that points to that proxy. Another possible cause of the download problem is some limitation in the heuristic that we use to download the papers, identifying this problem and coding a solution is a good opportunity for you to contribute to our project. See the [contribution guidelines](https://gitlab.com/jonatasgrosman/findpapers/-/blob/master/CONTRIBUTING.md)

- My institutional proxy has login and password, how can i include this in the proxy URL definition?

    Probably your institutional proxy can be defined with credentials following the pattern "https://[username]:[password]@[host]:[port]"


## Want to help?

See the [contribution guidelines](https://gitlab.com/jonatasgrosman/findpapers/-/blob/master/CONTRIBUTING.md)
if you'd like to contribute to Findpapers project.

You don't even need to know how to code to contribute to the project. Even the improvement of our documentation is an outstanding contribution.

If this project has been useful for you, please share it with your friends, this project could be helpful for them too.

And, if you like this project and wanna motivate the maintainers, give us a :star:. This kind of recognition will make us very happy with the work that we've done :heart:

---

**Note**: If you're seen this project from GitHub, this is just a mirror, 
the official project source code is hosted [here](https://gitlab.com/jonatasgrosman/findpapers) on GitLab.