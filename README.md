# Findpapers

Findpapers is an application that helps researchers who are looking for references for their research. The application will perform searches in several databases (currently ACM, arXiv, IEEE, PubMed, and Scopus) from a user-defined search query.

In summary, this tool will help you to perform the process below:

![Workflow](docs/workflow.png)

# Requirements

- Python 3.7+

# Installation

```console
$ pip install findpapers
```

# How to use it?

All application actions are command-line based. The available commands are 

- ```findpapers search```: Search for papers metadata using a query. This search will be made by matching the query with the paper's title, abstract, and keywords.

- ```findpapers refine```: Refine the search results by selecting/classifying the papers

- ```findpapers download```: Download full-text papers using the search results

- ```findpapers bibtex```: Generate a BibTeX file from the search results

You can control the commands logging verbosity by the **-v** (or **--verbose**) argument.

In the following sections, we will show how to use the findpapers commands. However, all the commands have the **--help** argument to display some summary about their usage, E.g., ```findpapers search --help```.

## Search query construction

First of all, we need to know how to build the search queries. The search queries must follow the rules:

- All the query terms need to be not empty and enclosed by square brackets. E.g., **[term a]**

- The query can contain boolean operators, but they must be uppercase. The allowed operators are AND, OR, and NOT. E.g., **[term a] AND [term b]**

- All the operators must have one space before and after them. E.g., **[term a] OR [term b] OR [term c]**

- The NOT operator must always be preceded by an AND operator E.g., **[term a] AND NOT [term b]**

- A subquery needs to be enclosed by parentheses. E.g., **[term a] AND ([term b] OR [term c])**

- The composition of terms is only allowed through boolean operators. Queries like "**[term a] [term b]**" are invalid

You can use some wildcards in the query too. Use **?** to replace a single character or **\*** to replace any number of characters:

- **[son?]** will match song, sons, ...

- **[son\*]** will match song, sons, sonic, songwriting, ...

Let's see some examples of valid and invalid queries:

| Query  | Valid? |
| ------------- | ------------- |
| ([term a] OR [term b])  |  Yes  |
| [term a] OR [term b]  |  Yes  |
| [term a] AND [term b]  |  Yes  |
| [term a] AND NOT ([term b] OR [term c])  |  Yes  |
| [term a] OR ([term b] AND ([term\*] OR [term ?]))  |  Yes |
| [term a]  |  Yes  |
| ([term a] OR [term b]  |  **No** (missing parentheses)  |
| [term a] or [term b] |  **No** (lowercase operator)  |
| term a OR [term b] |  **No** (missing square brackets)  |
| [term a] [term b] |  **No** (missing boolean operator)  |
| [term a] XOR [term b] |  **No** (invalid boolean operator)  |
| [term a] OR NOT [term b] |  **No** (NOT operator must be preceded by AND)  |
| [] AND [term b] |  **No** (empty term)  |


## Basic example (TL;DR)

- Searching for papers:

```console
$ findpapers search /some/path/search.json "[happiness] AND ([joy] OR [peace of mind]) AND NOT [stressful]"
```

- Refining search results:

```console
$ findpapers refine /some/path/search.json
```

- Downloading full-text from selected papers:

```console
$ findpapers download /some/path/search.json /some/path/papers/ -s
```

- Generating BibTeX file from selected papers:

```console
$ findpapers bibtex /some/path/search.json /some/path/mybib.bib -s
```

## Advanced example

This advanced usage documentation can be a bit boring to read (and write), so I think it's better to go for a storytelling approach here.

Let's take a look at Dr. McCartney's research. He's a computer scientist interested in AI and music, so he created a search query to collect papers that can help with his research and export it to an environment variable.

```console
$ export QUERY="([artificial intelligence] OR [AI] OR [machine learning] OR [ML] OR [deep learning] OR [DL]) AND ([music] OR [song])"
```

Dr. McCartney is interested in testing his query, so he decides to collect only 20 papers to test whether the query is suitable for his research.

```console
$ findpapers search /some/path/search_paul.json --query "$QUERY" --limit 20
```

But after taking a look at the results contained in the ```search_paul.json``` file, he notices two problems:
 - Only one database was used to collect the 20 papers
 - Some collected papers were about drums, but he doesn't like drums and drummers

So he decides to solve these problems by reformulating his query.

```console
$ export QUERY="([artificial intelligence] OR [AI] OR [machine learning] OR [ML] OR [deep learning] OR [DL]) AND ([music] OR [song]) AND NOT [drum*]"
```

And he will perform the search limiting the number of papers that can be collected by 4 per database.

```console
$ findpapers search /some/path/search_paul.json --query "$QUERY" --limit-db 4
```

Now his query returned the papers he wanted, but he realized one thing, no papers were collected from Scopus nor IEEE databases. Then he noticed that he needed to pass his Scopus and IEEE API access keys when calling the search command. So he went to https://dev.elsevier.com and https://developer.ieee.org, generated the access keys, and used them in the search.

```console
$ export IEEE_TOKEN=SOME_SUPER_SECRET_TOKEN

$ export SCOPUS_TOKEN=SOME_SUPER_SECRET_TOKEN

$ findpapers search /some/path/search_paul.json --query "$QUERY" --limit-db 4 --token-ieee "$IEEE_TOKEN" --token-scopus "$SCOPUS_TOKEN"
```

Now everything is working as he expected, so it's time to do the final papers search. So he defines that he wants to collect only works published between 2000 and 2020. He also decides that he only wants papers collected from ACM, IEEE, and Scopus.

```console
$ findpapers search /some/path/search_paul.json --query "$QUERY" --token-ieee "$IEEE_TOKEN" --token-scopus "$SCOPUS_TOKEN" --since 2000-01-01 --until 2020-12-31 --databases "acm,ieee,scopus"
```

The searching process took a long time, but after many cups of coffee, Dr. McCartney finally has a good list of papers with the potential to help in his research. All the information collected is in the ```search_paul.json``` file. He can now access this file manually to filter which works are most interesting for him, but he prefers to use the Findpapers ```refine``` command for this.

First, he wants to filter the papers looking only at their basic information.

```console
$ findpapers refine /some/path/search_paul.json
```

![Workflow](docs/refine-01.jpeg)

After completing the first round filtering of the collected papers, he decides to do new filtering on the selected ones looking at the paper's extra info and abstract now. He also chooses to perform some classification while doing this further filtering. And to help in this process, he decides to highlight some keywords contained in the abstract.

```console
$ export CATEGORIES_CONTRIBUTION="Contribution:Metric,Tool,Model,Method"

$ export CATEGORIES_RESEARCH_TYPE="Research Type:Validation Research,Solution Proposal,Philosophical,Opinion,Experience,Other"

$ export HIGHLIGHTS="propose,achiev,accuracy,method,metric,result,limitation"

$ findpapers refine /some/path/search_paul.json --selected --abstract --extra-info --categories "$CATEGORIES_CONTRIBUTION" --categories "$CATEGORIES_CONTRIBUTION" --highlights "$HIGHLIGHTS"
```

![Workflow](docs/refine-02.jpeg)

Now that he has selected all the papers he wanted, he will try to download the full-text from all of them that have a "Model" or "Tool" as a contribution.

```console
$ findpapers download /some/path/search_paul.json /some/path/papers --selected --categories "Contribution:Tool,Model"
```

He also wants to generate the BibTeX file from these papers.

```console
$ findpapers bibtex /some/path/search_paul.json /some/path/mybib.bib --selected --categories "Contribution:Tool,Model"
```

But when he compared the papers' data in the ```/some/path/mybib.bib```  file to the PDF files in the ```/some/path/papers``` folder, he noticed that many papers had not been downloaded.

So when checking the ```/some/path/papers/download.log``` file he could see the link of all papers that were not downloaded correctly, and noticed that some of them were not downloaded due to some limitation of Findpapers (currently the tool has a set of heuristics to perform the download that may not work in all cases). However, the vast majority of papers were not downloaded because they were behind a paywall. Dr. McCartney has access to these jobs within the network at the university where he works, but he is at home right now.

But he discovers two things that save him from this mess. First, the university provides a proxy for tunneling requests. Second, Findpapers accepts the configuration of a proxy URL via a variables environment.

```console
export FINDPAPERS_PROXY=https://mccartney:super_secret_pass@liverpool.ac.uk:1234

$ findpapers download /some/path/search_paul.json /some/path/papers --selected --categories "Contribution:Tool,Model"
```

Now the vast majority of the papers he has access have been downloaded correctly.

And at the end of it, he decides to download all the selected works and generate their BibTeX file too.

```console
$ findpapers download /some/path/search_paul.json /some/path/papers --selected

$ findpapers bibtex /some/path/search_paul.json /some/path/mybib.bib --selected
```

As you could see, all the information collected and enriched by the Findpapers is persisted in a single JSON file. From this file, it is possible to create interesting visualizations about the collected data ...

... so, use your imagination!

That's all, folks! We have reached the end of our journey. I hope Dr. McCartney can continue his research and publish his work without any major problems now.

With this story, we saw all the commands of the tool. I know this documentation is kind of weird, but I haven't had time to write more formal documentation of the tool yet. But you can help us to improve this, take a look at the next section and see how you can do that.


## Want to help?

See the [contribution guidelines](https://gitlab.com/jonatasgrosman/findpapers/-/blob/master/CONTRIBUTING.md)
if you'd like to contribute to Findpapers project.

You don't even need to know how to code to contribute to the project. Even the improvement of our documentation is an outstanding contribution.

If this project has been useful for you, please share it with your friends. This project could be helpful for them too.

And, if you like this project and wanna motivate the maintainers, give us a :star:. This kind of recognition will make us very happy with the work that we've done :heart:

---

**Note**: If you're seen this project from GitHub, this is just a mirror, 
the official project source code is hosted [here](https://gitlab.com/jonatasgrosman/findpapers) on GitLab.