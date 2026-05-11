---
name: checkcommitpush
description: Run the full quality suite, fix any issues found, commit all uncommitted changes with a well-formed message, and push to the current branch.
---

## Goal

Ensure the current branch is clean, fully tested, and pushed - ready for review or merge.

## Steps

### 1. Inspect uncommitted changes

Run `git status` and `git diff` (or `git diff --cached`) to understand what has changed and is not yet committed. This will inform the commit message.

### 2. Run the full quality suite

```
make check
```

`make check` runs, in order: `lint`, `format`, `types`, `complexity`, `security`, `deps-audit`, `docstrings`, `dead-code`, and `test`.

- **lint / format**: If there are fixable issues, re-run with `make lint FIX=1` and `make format FIX=1`.
- **types**: Mypy errors are NOT auto-fixed - resolve them manually.
- **test**: If tests fail, fix the root cause before proceeding. Do not skip or delete failing tests.
- Do NOT proceed to commit if `make check` still fails after fixes.

### 3. Craft the commit message

Follow the Conventional Commits format defined in `CONTRIBUTING.md`:

```
<type>(<scope>): <subject>

<body>
```

Rules:
- **type** must be one of: `feat`, `fix`, `perf`, `docs`, `test`, `chore`
- **scope** is optional; use a short lowercase identifier (e.g. `search`, `utils`)
- **subject**: imperative present tense, no capital first letter, no trailing dot, max 100 chars per line
- **body** is optional but recommended for non-trivial changes; explain *why*, not just *what*

Examples:
```
fix(search): handle empty results list without raising exception
```
```
feat(runners): add verbose logging and numeric metrics
```
```
chore: update dev dependencies and lock file
```

### 4. Stage, commit, and push

```bash
git add -A
git commit -m "<your message>"
git push origin HEAD
```

If the push is rejected (non-fast-forward), investigate before force-pushing - do not use `--force` unless explicitly asked.
