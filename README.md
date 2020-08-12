# Papers scrapper

Application that collects papers from arXiv, ACM and Scopus databases

## initial setup

- install python >= 3.5

- install dependencies: `pip install -r requirements.txt`

- copy the file `/config.sample.ini` to `/config.ini` and change its values properly

## About areas

- the available areas are: computer_science, economics, engineering, mathematics, physics, biology, chemistry, humanities

## About queries

- you can execute a list of queries, just need to separate them by a comma

- we only support OR statements inside parentheses, this kind of query won't work properly:

`"term_a" AND "term_b" AND ("term_c" AND "term_d" OR "term_e")`

... try to re-write your query to leave the AND outside the parentheses:

`"term_a" AND "term_b" AND "term_c" AND ("term_d" OR "term_e")`

- we only support one level parentheses queries like:

`"term_a" AND "term_b" AND ("term_c" OR "term_d" OR "term_e")`

... this kind of query will not work properly:

`"term_a" AND "term_b" AND ("term_c" OR ("term_d" OR "term_e"))`

... prefer to split the query like this:

`"term_a" AND "term_b" AND ("term_c" OR "term_d"), "term_a" AND "term_b" AND ("term_c" OR "term_e")`

## running

There are 3 executable scripts in this project: 

- runner.py (responsible for papers collection)

- filter.py (responsible for papers filtering)

- charts.py (responsible for display papers filtering summary)