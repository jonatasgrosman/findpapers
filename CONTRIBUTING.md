# Contributing to Findpapers

We would love for you to contribute to Findpapers and help make it even better than it is
today! As a contributor, here are the guidelines we would like you to follow:

 - [Found a Bug?](#issue)
 - [Missing a Feature?](#feature)
 - [Submission Guidelines](#submit)
 - [Coding Rules](#rules)
 - [Commit Message Guidelines](#commit)
 - [Building and Testing](#dev)

## <a name="issue"></a> Found a Bug?

If you find a bug in the source code, you can help us by
[submitting an issue](#submit-issue) to our [GitHub Repository](https://github.com/jonatasgrosman/findpapers). Even better, you can
[submit a Pull Request](#submit-pr) with a fix.

## <a name="feature"></a> Missing a Feature?

You can *request* a new feature by [submitting an issue](#submit-issue) to our GitHub
Repository. If you would like to *implement* a new feature, please submit an issue with
a proposal for your work first, to be sure that we can use it.
Please consider what kind of change it is:

* For a **Major Feature**, first open an issue and outline your proposal so that it can be
discussed. This will also allow us to better coordinate our efforts, prevent duplication of work,
and help you to craft the change so that it is successfully accepted into the project.

* **Small Features** can be crafted and directly [submitted as a Pull Request](#submit-pr).

## <a name="submit"></a> Submission Guidelines

In our development process we follow the [GitHub flow](https://docs.github.com/en/get-started/quickstart/github-flow), which is very powerful and easy to understand. 
That process enforces continuous delivery by **making anything in the main branch deployable**.
So everybody needs to keep the main branch as safe as possible and ready to be deployed at any time.

### <a name="submit-issue"></a> Submitting an Issue

Before you submit an issue, please search the issue tracker, maybe an issue for your problem already exists and the discussion might inform you of workarounds readily available.

We want to fix all the issues as soon as possible, but before fixing a bug we need to reproduce and confirm it. In order to reproduce bugs, we will systematically ask you to provide a minimal reproduction scenario. In this scenario you need to describe how we can reproduce the bug and provide all the additional information that you think will help us to reproduce it.

A minimal reproduction scenario allows us to quickly confirm a bug (or point out a coding problem) as well as confirm that we are fixing the right problem. And when it is possible, please create a standalone git repository demonstrating the problem.

Unfortunately, we are not able to investigate/fix bugs without a minimal reproduction, so if we don't hear back from you we are going to close an issue that doesn't have enough info to be reproduced.

You can file new issues by filling out our [new issue form](https://github.com/jonatasgrosman/findpapers/issues/new).

### <a name="submit-pr"></a> Submitting a Pull Request (PR)

Before you submit your Pull Request (PR), consider the following guidelines:

1. Search [GitHub](https://github.com/jonatasgrosman/findpapers/pulls) for an open or closed PR
  that relates to your submission. You don't want to duplicate effort.
1. Fork the jonatasgrosman/findpapers repo.
1. Make your changes in a new git branch:

     ```shell
     git checkout -b my-fix-branch main
     ```

1. Create your patch, **including appropriate test cases**.
1. Follow our [Coding Rules](#rules).
1. Run all quality checks (`make check`), as described in the section [Building and Testing](#dev),
  and ensure that all checks pass.
1. Commit your changes using a descriptive commit message that follows our
  [commit message conventions](#commit). Adherence to these conventions
  is necessary because release notes are automatically generated from these messages.

     ```shell
     git commit -a
     ```
    Note: the optional commit `-a` command line option will automatically "add" and "rm" edited files.

1. Push your branch to GitHub:

    ```shell
    git push origin my-fix-branch
    ```

1. In GitHub, send a pull request to `findpapers:main`.
1. If we suggest changes, then:
  * Make the required updates.
  * Re-run all quality checks to ensure that everything is still passing.
  * Rebase your branch and force push to your GitHub repository (this will update your Pull Request):

    ```shell
    git rebase main -i
    git push -f
    ```

That's it! Thank you for your contribution!

#### After your pull request is merged

After your pull request is merged, you can safely delete your branch and pull the changes
from the main (upstream) repository:

* Delete the remote branch on GitHub either through the GitHub web UI or your local shell as follows:

    ```shell
    git push origin --delete my-fix-branch
    ```

* Check out the main branch:

    ```shell
    git checkout main -f
    ```

* Delete the local branch:

    ```shell
    git branch -D my-fix-branch
    ```

* Update your main with the latest upstream version:

    ```shell
    git pull --ff upstream main
    ```

## <a name="rules"></a> Coding Rules

To ensure consistency throughout the source code, keep these rules in mind as you are working:

* Write code in English.
* Write comments in English.
* You must write comments to explain non-trivial parts of the code.
* All features or bug fixes must be tested by one or more specs (unit-tests).
* All methods must have type hints.
* All methods must have docstrings.
* The names of variables, functions, classes, files and modules should be descriptive.
* Keep functions and methods focused on a single task; avoid large monolithic functions.
* Line length should not exceed 100 characters.
* If you changed any code, run `make check` before committing.
* Aim to keep test coverage as close to 100% as possible.
* Public methods must include parameters, returns, and possible exceptions.
* We follow the [PEP8 Style Guide](https://peps.python.org/pep-0008/) for general coding.
* We follow the [Numpy Docstring Style Guide](https://numpydoc.readthedocs.io/en/latest/format.html) for code documentation.
* We use [mypy](http://mypy-lang.org/) for static type checking.
* Follow the [ruff](https://ruff.rs/) rules for linting and code formatting.
* When adding new dependencies, add them to the `pyproject.toml` file using Poetry.
* PRs can only be merged if the code passes all quality checks (tests, formatting, linting, type checks, etc.).
* No secret keys, passwords, or sensitive information should be committed to the repository.
* Use environment variables or configuration files (e.g., `.env`) to manage sensitive data.

## <a name="commit"></a> Commit Message Guidelines

Each commit message consists of a **header** and a **body**. The header has a special
format that includes a **type**, an optional **scope**, and a **subject**:

```
<type>(<scope>): <subject>
<BLANK LINE>
<body>
```

- The **header** is mandatory. The **body** is optional.

Any line of the commit message cannot be longer than 100 characters! This allows the message to be easier
to read in various git tools.

Examples:

```
docs: update changelog to 0.2
```

```
fix: error when saving to CSV with empty paper list

When the paper list was empty, saving to CSV raised an unhandled exception.

```

```
feat(runners): add verbose logging and numeric metrics
```

### Type

We use a concise set of commit types. Use one of the following in the commit header:

* **feat**: A new feature
* **fix**: A bug fix
* **perf**: Performance improvements
* **docs**: Documentation changes
* **test**: Tests and related changes
* **chore**: Maintenance, build, CI, or refactor tasks

### Scope

Scope is optional and should be a short lowercase identifier (no spaces). The scope could be
the name of the module, package being changed or a broader category that the change falls under.
There is no strict list of scopes, but here are some examples to guide you: `runners`,
`utils`, `search`, `persistence`...

### Subject

The subject contains a succinct description of the change:

* use the imperative, present tense: "change" not "changed" nor "changes"
* don't capitalize the first letter
* no dot (.) at the end

### Body

Just as in the **subject**, use the imperative, present tense: "change" not "changed" nor "changes".
The body should include the motivation for the change and contrast this with previous behavior.

## <a name="dev"></a> Building and Testing

Let's see what needs to be done on your machine before [submitting a Pull Request](#submit-pr).

### Prerequisite Software

Before you can build and test, you must install and configure the
following products on your development machine:

* [Python](https://www.python.org) (3.11+)

* [Git](http://git-scm.com)

* [Poetry](https://python-poetry.org/) (dependency management)

### Getting the Sources

Fork and clone the Findpapers repository:

1. Log in to your GitHub account or create one [here](https://github.com).
1. [Fork](https://docs.github.com/en/get-started/quickstart/fork-a-repo) the [Findpapers
   repository](https://github.com/jonatasgrosman/findpapers).
1. Clone your fork of the Findpapers repository and define an `upstream` remote pointing back to
   the Findpapers repository that you forked in the first place.

```shell
# Clone your GitHub repository:
git clone git@github.com:<github username>/findpapers.git

# Go to the Findpapers directory:
cd findpapers

# Add the Findpapers repository as an upstream remote to your repository:
git remote add upstream https://github.com/jonatasgrosman/findpapers.git
```

### Installing Dependencies

```shell
make setup
```

### Running Quality Checks

Run all quality checks at once (recommended before submitting a PR):

```shell
make check
```

Or run individual checks:

```shell
# Run unit tests with coverage
make test

# Run live integration tests against real external APIs
make test-integration

# Check code formatting (ruff)
make format

# Check lint issues (ruff)
make lint

# Run static type checks (mypy)
make types

# Check cyclomatic complexity (xenon)
make complexity

# Run static security analysis (bandit)
make security

# Check dependencies for known vulnerabilities (pip-audit)
make deps-audit

# Check docstring coverage (interrogate)
make docstrings

# Detect unused code (vulture)
make dead-code
```