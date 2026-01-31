# Copilot Instructions

## Environment Guidelines

* To set up the development environment for the first time, run `make setup` in the project root folder.
* We use [Poetry](https://python-poetry.org/) for dependency management and packaging. To install the dependencies, run `venv/bin/poetry install` in the project root folder.
* All poetry commands should be run inside the venv, e.g., `venv/bin/poetry <command>`.
* To run the tests, use the command `make test`.
* To run the linter and code formatter checks, use the command `make lint`.

## Code Guidelines

To ensure consistency throughout the source code, keep these rules in mind as you are working:

* Write code in English.
* Write comments in English.
* Write comments where necessary to explain non-trivial parts of the code.
* All features or bug fixes must be tested by one or more specs (unit-tests).
* All methods must have type hints.
* All methods must have docstrings.
* The names of variables, functions, classes, and modules should be descriptive.
* Keep functions and methods focused on a single task; avoid large monolithic functions.
* Line length should not exceed 100 characters.
* If you changed any code, run `make lint` and `make test` before committing.
* Aim to keep test coverage as close to 100% as possible.
* public methods must include parameters, returns, and possible exceptions.
* We follow the [PEP8 Style Guide][pep8-style-guide] for general coding.
* We follow the [Numpy Docstirng Style Guide][numpy-docstring-style-guide] for code documentation.
* Use type hints as much as possible. We use [mypy](http://mypy-lang.org/) for static type checking.
* Follow the [isort](https://pycqa.github.io/isort/) rules for import sorting.
* Follow the [black](https://black.readthedocs.io/en/stable/) rules for code formatting.
* Follow the [ruff](https://ruff.rs/) rules for linting.
* When adding new dependencies, add them to the `pyproject.toml` file using Poetry.
* PRs can only be merged if the code is formatted properly and all tests are passing.
* No secret keys, passwords, or sensitive information should be committed to the repository.
* Use environment variables or configuration files (e.g., `.env`) to manage sensitive data.


## Commit Message Guidelines

Each commit message consists of a **header** and a **body**.  The header has a special
format that includes a **type** and a **subject**:

```
<type>: <subject>
<BLANK LINE>
<body>
```

The **header** is mandatory. The **body** is optional.

Any line of the commit message cannot be longer 100 characters! This allows the message to be easier
to read in various git tools.

```
docs: update changelog to 0.2
```
```
fix: need to depend on latest rxjs and zone.js

The version in our package.json gets copied to the one we publish, and users need the latest of these.

```

### Type

We use a concise set of commit types. Use one of the following in the commit header:

* **feat**: A new feature
* **fix**: A bug fix
* **perf**: Performance improvements
* **docs**: Documentation changes
* **test**: Tests and related changes
* **chore**: Maintenance, build, CI, or refactor tasks

### Subject

The subject contains a succinct description of the change:

* use the imperative, present tense: "change" not "changed" nor "changes"
* don't capitalize the first letter
* no dot (.) at the end

### Body

Just as in the **subject**, use the imperative, present tense: "change" not "changed" nor "changes".
The body should include the motivation for the change and contrast this with previous behavior.
