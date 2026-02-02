# Findpapers

[![PyPI - License](https://img.shields.io/pypi/l/findpapers)](https://github.com/jonatasgrosman/findpapers/blob/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/findpapers)](https://pypi.org/project/findpapers)

Findpapers is an application that helps researchers who are looking for references for their work. The application will perform searches in several databases (currently arXiv, bioRxiv, IEEE, medRxiv, PubMed, and Scopus) from a user-defined search query.

# Requirements

- Python 3.10+

# Installation

```console
$ pip install findpapers
```

# How to use it?

Findpapers is designed to be used as a Python library.

```python
import findpapers
import datetime

search_file = "search.json"
query = "[happiness] AND ([joy] OR [peace of mind]) AND NOT [stressful]"
since = datetime.date(2020, 1, 1)
until = datetime.date(2024, 12, 31)

findpapers.search(search_file, query, since=since, until=until)
```

## Search query construction

The search queries must follow the rules:

- All the query terms need to be not empty and enclosed by square brackets. E.g., **[term a]**

- Terms cannot contain double quotes ("). E.g., **["term a"]** is invalid

- The query can contain boolean connectors (case-insensitive). The allowed connectors are **AND**, **OR**, and **AND NOT**. E.g., **[term a] AND [term b]** or **[term a] and not [term b]**

- All connectors must have at least one whitespace before and after them (tabs or newlines can be valid too). E.g., **[term a] OR [term b] OR [term c]**

- Connectors must be between terms or groups. A query with a single term cannot have connectors. E.g., **[term a] AND** or **AND [term a]** are invalid

- A subquery needs to be enclosed by parentheses. E.g., **[term a] AND ([term b] OR [term c])**

- The composition of terms is only allowed through boolean connectors. Queries like "**[term a] [term b]**" are invalid

We still have a few more rules that are **only applicable on bioRxiv and medRxiv databases**:

- On subqueries with parentheses, only 1-level grouping is supported, i.e., queries with 2-level grouping like **[term a] OR (([term b] OR [term c]) AND [term d])** are considered invalid

- Only "OR" connectors are allowed between parentheses, i.e., queries like **([term a] OR [term b]) AND ([term c] OR [term d])** are considered invalid

- Only "OR" and "AND" connectors are allowed, i.e., queries like **[term a] AND NOT [term b]** are considered invalid

- Mixed connectors are not allowed on queries (or subqueries when parentheses are used), i.e., queries like **[term a] OR [term b] AND [term b]** are considered invalid. But queries like **[term a] OR [term b] OR [term b]** are considered valid

You can use some wildcards in the query too. Use question mark (?) to replace exactly one character, and use an asterisk (*) to replace zero or more characters:

- **[son?]** will match song, sons, ... (But won't match "son")

- **[son\*]** will match son, song, sons, sonic, songwriting, ...

There are some rules that you'll need to follow when using wildcards:

- Cannot be used at the start of a search term;
- A minimum of 3 characters preceding the asterisk wildcard (*) is required;
- The asterisk wildcard (*) can only be used at the end of a search term;
- Can be used only in single terms;
- Only one wildcard can be included in a search term.

Note: The bioRxiv and medRxiv databases don't support any wildcards, and the IEEE and PubMed databases only support the "*" wildcard.

Let's see some examples of valid and invalid queries:

| Query  | Valid? |
| ------------- | ------------- |
| [term a]   |  Yes  |
| ([term a] OR [term b])   |  Yes  |
| [term a] OR [term b]  |  Yes  |
| [term a] AND [term b]   |  Yes  |
| [term a] AND NOT ([term b] OR [term c])  |  Yes  |
| [term a] OR ([term b] AND ([term\*] OR [t?rm]))  |  Yes |
| [term a]OR[term b]   |  **No** (no whitespace between terms and connector)  |
| ([term a] OR [term b]  |  **No** (missing parentheses)  |
| term a OR [term b]  |  **No** (missing square brackets)  |
| [term a] [term b]  |  **No** (missing connector)  |
| [term a] XOR [term b] |  **No** (invalid connector)   |
| [term a] OR NOT [term b] |  **No** (OR NOT is not a valid connector, use AND NOT instead)   |
| [] AND [term b]  |  **No** (empty term)  |
| ["term a"]  |  **No** (terms cannot contain double quotes)  |
| [term a] AND  |  **No** (connector at the end without following term)  |
| AND [term a]  |  **No** (connector at the beginning without preceding term)  |
|[some term\*]  |  **No** (wildcards can be used only in single terms)  |
|[?erm]  |  **No** (wildcards cannot be used at the start of a search term)  |
|[te*]  |  **No** (a minimum of 3 characters preceding the asterisk wildcard is required)  |
|[ter*s]  |  **No** (the asterisk wildcard can only be used at the end of a search term)  |
|[t?rm?]  |  **No** (only one wildcard can be included in a search term)  |

## Examples

```python
import findpapers
import datetime

search_file = "search.json"
query = "[happiness] AND ([joy] OR [peace of mind]) AND NOT [stressful]"

findpapers.search(search_file, query, since=datetime.date(2020, 1, 1))
findpapers.download(search_file, "/some/path/papers")
findpapers.generate_bibtex(search_file, "/some/path/mybib.bib")
```

# Want to help?

See the [contribution guidelines](https://github.com/jonatasgrosman/findpapers/blob/master/CONTRIBUTING.md)
if you'd like to contribute to Findpapers project.

Please follow the [Code of Conduct](https://github.com/jonatasgrosman/findpapers/blob/master/CODE_OF_CONDUCT.md).

You don't need to know how to code to contribute to the project. Even the improvement of our documentation is an outstanding contribution.

If this project has been useful for you, please share it with your friends. This project could be helpful for them too.

If you like this project and want to motivate the maintainers, give us a :star:. This kind of recognition will make us very happy with the work that we've done with :heart:

You can also [sponsor me](https://github.com/sponsors/jonatasgrosman) :heart_eyes:

# Citation
If you want to cite the tool you can use this:

```bibtex
@misc{grosman2020findpapers,
  title={{Findpapers: A tool for helping researchers who are looking for related works}},
  author={Grosman, Jonatas},
  howpublished={\url{https://github.com/jonatasgrosman/findpapers}},
  year={2020}
}
```
