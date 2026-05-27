# Query Syntax

Findpapers uses a custom boolean query language that gets translated into the native syntax of each database. This page describes all the rules.

## Basic Structure

- Terms must be enclosed in **square brackets**: `[term]`
- Terms cannot be empty or contain double quotes
- Boolean connectors join terms or groups

```
[machine learning] AND [healthcare]
```

## Shorthand Syntax

Square brackets are the canonical term delimiter, but two shorthand forms are accepted and **silently converted** before any validation takes place:

| Shorthand | Canonical equivalent | When used |
|-----------|---------------------|-----------|
| `"DL" OR "ML"` | `[DL] OR [ML]` | Double quotes wrap each term |
| `Deep Learning` | `[Deep Learning]` | No brackets **and** no quotes — the entire string becomes one term |

Filter codes before a double-quoted term are preserved:

```
ti"neural network" → ti[neural network]
```

> **Note:** Conversion is applied only when the query contains no square brackets at all. As soon as one `[` is found the query is treated as canonical.

## Boolean Connectors

Three connectors are available (case-insensitive):

| Connector | Meaning |
|-----------|---------|
| `AND` | Both terms must be present |
| `OR` | At least one term must be present |
| `AND NOT` | First term present, second excluded |

Connectors must have at least one whitespace before and after them.

All seven databases support all three boolean connectors.

## Grouping

Use parentheses to group subqueries:

```
[deep learning] AND ([image classification] OR [object detection])
```

Groups can be nested:

```
[term a] OR ([term b] AND ([term c] OR [term d]))
```

## Filter Codes

Filter codes restrict where a term is searched. Add them before the opening bracket or before a group:

```
ti[neural network] AND abs([image segmentation] OR [object detection])
```

| Code | Field | Description |
|------|-------|-------------|
| `ti` | Title | Search in paper title only |
| `abs` | Abstract | Search in abstract only |
| `key` | Keywords | Search in keywords only |
| `au` | Author | Search by author name |
| `src` | Source | Search by publication source name (journal, conference) |
| `aff` | Affiliation | Search by author affiliation |
| `tiabs` | Title + Abstract | Search in title and abstract |
| `tiabskey` | Title + Abstract + Keywords | Search in title, abstract, and keywords |

When no filter code is specified, the default behavior depends on the target database: `tiabskey` (title, abstract, and keywords) is used for databases that support it (IEEE, PubMed, Scopus, Web of Science), and `tiabs` (title and abstract) is used for the rest (arXiv, OpenAlex, Semantic Scholar).

### Filter Code Propagation

Filter codes propagate into groups. The innermost explicit filter always wins:

```
ti([neural network] OR abs[deep learning])
```

In this example, `[neural network]` inherits the `ti` filter from the group, but `[deep learning]` uses its own explicit `abs` filter.

Not all databases support every filter code. When a query uses a filter code that a database doesn't handle, that database is automatically skipped.

| Filter Code | Field | arXiv | IEEE | OpenAlex | PubMed | Scopus | Semantic Scholar | WoS |
|-------------|-------|-------|------|----------|--------|--------|------------------|-----|
| `ti` | Title | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `abs` | Abstract | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `key` | Keywords | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| `au` | Author | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `src` | Source | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |
| `aff` | Affiliation | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `tiabs` | Title + Abstract | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `tiabskey` | Title + Abstract + Keywords | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |

## Wildcards

Two wildcards are available:

| Wildcard | Meaning | Example |
|----------|---------|---------|
| `?` | Exactly one character | `[son?]` matches "song", "sons" (not "son") |
| `*` | Zero or more characters | `[son*]` matches "son", "song", "sonic", ... |

### Wildcard Rules

- Cannot be placed at the **start** of a term
- `*` can only be placed at the **end** of a term
- Only **one** wildcard per term
- Can only be used in **single-word** terms
- Minimum characters before `*` varies by database (see table below)

Not all databases support wildcards. When a query uses a wildcard that a database doesn't handle, that database is automatically skipped.

| Feature | arXiv | IEEE | OpenAlex | PubMed | Scopus | Semantic Scholar | WoS |
|---------|-------|------|----------|--------|--------|------------------|-----|
| `?` (single char) | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| `*` (zero or more) | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Min chars before `*` | 1 | 3 | - | 4 | 3 | 1 | 3 |


## Examples

### Realistic Queries

**Simple topic search** - find papers about a single topic:

```
[machine learning]
```

**Two topics combined** - find papers that cover both topics:

```
[machine learning] AND [healthcare]
```

**Alternative terms** - find papers that mention at least one of the synonyms:

```
[deep learning] OR [neural network] OR [artificial intelligence]
```

**Excluding a subtopic** - find reinforcement learning papers that are not about games:

```
[reinforcement learning] AND NOT [game]
```

**Complex boolean with grouping** - find papers about transformers applied to either vision or speech:

```
[transformer] AND ([computer vision] OR [speech recognition])
```

**Nested groups** - combine broader topics with specific sub-areas:

```
([natural language processing] OR [computational linguistics]) AND ([sentiment analysis] OR [text classification]) AND NOT [social media]
```

**Filter by title** - find papers with "attention" in the title:

```
ti[attention mechanism] AND [transformer]
```

**Multiple filter codes** - title and abstract targeting different terms:

```
ti[BERT] AND abs[fine-tuning] AND key[transfer learning]
```

**Filter code on a group** - apply a filter to an entire group of alternatives:

```
ti([convolutional neural network] OR [CNN]) AND abs[medical imaging]
```

**Author search** - find papers by a specific author on a topic:

```
au[Yoshua Bengio] AND [deep learning]
```

**Source filter** - search within a specific journal:

```
src[Nature] AND [gene editing] AND [CRISPR]
```

**Affiliation filter** - papers from a specific institution:

```
aff[Stanford University] AND [artificial intelligence]
```

**Wildcard with `*`** - match word variations (e.g., "neural", "neurological", "neuroscience"):

```
[neur*] AND [imaging]
```

**Wildcard with `?`** - match a single character variation:

```
[optimi?ation]
```

**Combining several features** - a realistic literature review query:

```
ti([deep learning] OR [neural network]) AND abs([medical imaging] OR [radiology]) AND NOT [survey]
```

### Valid vs. Invalid Syntax

| Query | Valid? | Why |
|-------|--------|-----|
| `[machine learning]` | ✅ | Single term |
| `[deep learning] AND [NLP]` | ✅ | Two terms with connector |
| `([term a] OR [term b])` | ✅ | Grouped alternatives |
| `[term a] AND NOT ([term b] OR [term c])` | ✅ | Exclusion with grouping |
| `ti[neural nets] AND abs[vision]` | ✅ | Filter codes on individual terms |
| `ti([CNN] OR [ResNet]) AND abs[classification]` | ✅ | Filter code on a group |
| `[term a] OR ([term b] AND ([term*] OR [t?rm]))` | ✅ | Wildcards inside nested groups |
| `[term a]OR[term b]` | ❌ | Missing whitespace around connector |
| `([term a] OR [term b]` | ❌ | Unbalanced parentheses |
| `"DL" OR "ML"` | ✅ | Shorthand: double quotes converted to brackets |
| `Deep Learning` | ✅ | Shorthand: bare text wrapped as a single term |
| `ti"Neural Network"` | ✅ | Shorthand: filter prefix preserved during conversion |
| `term a OR [term b]` | ❌ | Missing square brackets around `term a` (mixed syntax; bracket detected so no conversion) |
| `[term a] [term b]` | ❌ | Missing connector between terms |
| `[term a] XOR [term b]` | ❌ | Invalid connector (`XOR` is not supported) |
| `[] AND [term b]` | ❌ | Empty term |
| `["term a"]` | ❌ | Double quotes not allowed inside brackets |
| `[?erm]` | ❌ | Wildcard at start of term |
| `[ter*s]` | ❌ | `*` not at end of term |
| `[t?rm?]` | ❌ | Multiple wildcards in one term |
| `[some term*]` | ❌ | Wildcard in multi-word term |

## Error Handling

Invalid queries raise `QueryValidationError` at search time:

```python
from findpapers import Engine
from findpapers.exceptions import QueryValidationError

engine = Engine()
try:
    result = engine.search("[term a] XOR [term b]")
except QueryValidationError as e:
    print(f"Invalid query: {e}")
```

If a query is valid but not supported by a specific database (e.g., uses a filter code the database doesn't handle), that database is silently skipped and the search proceeds with the remaining databases.

## Database-Specific Notes

- **arXiv** uses server-side stemming - e.g., `[transformer]` also matches "transformations" and "transformed".
- **arXiv** and **Semantic Scholar** automatically replace hyphens with spaces in terms before sending the query (e.g., `[self-attention]` becomes `[self attention]`). All other databases receive terms exactly as typed - hyphens are preserved.
- **PubMed** phrase index is limited to approximately 3-word phrases. Longer exact phrases silently return zero results. Use short terms and combine with `AND` instead.
- **PubMed** author names must follow the "LastName Initials" format (e.g., `au[Doudna JA]` for 'Jennifer Anne Doudna'). Full first names do not match.
