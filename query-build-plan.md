# Query Build Plan - Conversão de Query Geral para Queries Específicas por Banco

Este documento descreve o plano detalhado para converter a query geral do Findpapers (representada pelo objeto `Query`) em queries específicas para cada banco de dados suportado.

## Índice

1. [Visão Geral](#visão-geral)
2. [Resumo de Suporte por Banco](#resumo-de-suporte-por-banco)
3. [Detalhamento por Banco](#detalhamento-por-banco)
   - [arXiv](#arxiv)
   - [PubMed](#pubmed)
   - [IEEE Xplore](#ieee-xplore)
   - [Scopus](#scopus)
   - [bioRxiv](#biorxiv)
   - [medRxiv](#medrxiv)
   - [OpenAlex](#openalex)
   - [Semantic Scholar](#semantic-scholar)
4. [Busca por Campos Específicos](#busca-por-campos-específicos)
   - [Comportamento Padrão por Base](#comportamento-padrão-por-base)
5. [Estratégia de Implementação](#estratégia-de-implementação)
6. [Tradeoffs e Limitações](#tradeoffs-e-limitações)

---

## Visão Geral

O Findpapers usa uma sintaxe de query universal que precisa ser convertida para o formato específico de cada banco de dados. A estrutura geral da query do Findpapers segue estas regras:

- Termos entre colchetes: `[termo]`
- Conectores booleanos: `AND`, `OR`, `AND NOT`
- Agrupamentos com parênteses: `([termo a] OR [termo b])`
- Wildcards: `?` (um caractere) e `*` (zero ou mais caracteres)

O objeto `Query` já realiza o parsing da string de query em uma árvore (tree) com os seguintes tipos de nós:
- `ROOT`: Nó raiz
- `TERM`: Termo de busca (valor do termo)
- `CONNECTOR`: Operador booleano (`AND`, `OR`, `AND NOT`)
- `GROUP`: Agrupamento de termos e conectores

---

## Resumo de Suporte por Banco

### Tabela de Suporte - Operadores Booleanos e Wildcards

| Feature | arXiv | PubMed | IEEE | Scopus | bioRxiv | medRxiv | OpenAlex | Semantic Scholar |
|---------|-------|--------|------|--------|---------|---------|----------|------------------|
| **AND** | ✅ `AND` | ✅ `AND` | ✅ `AND` | ✅ `AND` | ✅ (via match-all) | ✅ (via match-all) | ✅ `,` ou `+` | ✅ `+` (bulk) |
| **OR** | ✅ `OR` | ✅ `OR` | ✅ `OR` | ✅ `OR` | ✅ (via match-any) | ✅ (via match-any) | ✅ `\|` | ✅ `\|` (bulk) |
| **AND NOT** | ✅ `ANDNOT` | ✅ `NOT` | ✅ `NOT` | ✅ `AND NOT` | ❌ | ❌ | ✅ `!` | ✅ `-` (bulk) |
| **Parênteses** | ✅ `%28 %29` | ✅ `()` | ✅ `()` | ✅ `()` | ⚠️ 1 nível | ⚠️ 1 nível | ✅ `()` | ✅ `()` (bulk) |
| **Wildcard ?** | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Wildcard *** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Frases** | ✅ `%22...%22` | ✅ `"..."` | ✅ `"..."` | ✅ `"..."` ou `{...}` | ❌ | ❌ | ✅ `"..."` | ✅ `"..."` |

### Tabela de Suporte - Busca por Campos Específicos

| Campo | Código | arXiv | PubMed | IEEE | Scopus | bioRxiv | medRxiv | OpenAlex | Semantic Scholar |
|-------|--------|-------|--------|------|--------|---------|---------|----------|------------------|
| Título | `ti` | ✅ `ti:` | ✅ `[ti]` | ✅ `article_title` | ✅ `TITLE()` | ⚠️ | ⚠️ | ✅ `title.search` | ❌ |
| Abstract | `abs` | ✅ `abs:` | ✅ `[tiab]` | ✅ `abstract` | ✅ `ABS()` | ⚠️ | ⚠️ | ✅ `abstract.search` | ❌ |
| Keywords | `key` | ❌ | ✅ `[mh]` | ✅ `index_terms` | ✅ `KEY()` | ❌ | ❌ | ⚠️ via `concepts` | ❌ |
| Autor | `au` | ✅ `au:` | ✅ `[au]` | ✅ `author` | ✅ `AUTH()` | ❌ | ❌ | ✅ `authorships.author.display_name.search` | ⚠️ filter |
| Publicação | `pu` | ❌ | ✅ `[journal]` | ✅ `publication_title` | ✅ `SRCTITLE()` | ❌ | ❌ | ✅ `primary_location.source` | ✅ `venue` filter |
| Afiliação | `af` | ❌ | ✅ `[ad]` | ✅ `affiliation` | ✅ `AFFIL()` | ❌ | ❌ | ✅ `authorships.institutions` | ❌ |
| Todos campos | (default) | ✅ `all:` | ✅ `[tiab]` | ✅ `querytext` | ✅ `TITLE-ABS-KEY()` | ✅ | ✅ | ✅ `search` | ✅ `query` |

**Legenda:**
- ✅ Suporte nativo
- ⚠️ Suporte parcial (requer múltiplas requisições ou workaround)
- ❌ Não suportado

---

## Detalhamento por Banco

### arXiv

**Base URL:** `http://export.arxiv.org/api/query`

**Documentação:** https://info.arxiv.org/help/api/user-manual.html

#### Sintaxe de Query

```
search_query=<field>:<term>+<operator>+<field>:<term>
```

#### Conversão de Operadores

| Findpapers | arXiv |
|------------|-------|
| `AND` | `AND` ou `+` |
| `OR` | `OR` |
| `AND NOT` | `ANDNOT` |
| `[termo]` | `"termo"` ou apenas `termo` |
| `(...)` | `%28...%29` (URL encoded) |

#### Prefixos de Campo

| Campo | Prefixo arXiv | Descrição |
|-------|---------------|-----------|
| Título | `ti:` | Título do artigo |
| Abstract | `abs:` | Resumo |
| Autor | `au:` | Nome do autor |
| Comentário | `co:` | Comentários do autor |
| Referência | `jr:` | Referência de journal |
| Categoria | `cat:` | Categoria do arXiv |
| ID | `id:` | ID do arXiv |
| Todos | `all:` | Todos os campos acima |

#### Filtro de Data

```
submittedDate:[YYYYMMDDTTTT TO YYYYMMDDTTTT]
```

#### Exemplo de Conversão

**Query Findpapers:**
```
[machine learning] AND ([nlp] OR [natural language processing]) AND NOT [deep learning]
```

**Query arXiv:**
```
all:"machine learning" AND (all:nlp OR all:"natural language processing") ANDNOT all:"deep learning"
```

#### Pré-processamento de Termos

**Tratamento de hífens**: Antes de enviar a query ao arXiv, todos os hífens (`-`) nos termos devem ser substituídos por espaços. A documentação do arXiv confirma que "Hyphenated query terms yield no matches".

```python
def preprocess_term_for_arxiv(term: str) -> str:
    """Substitui hífens por espaços nos termos para evitar falha de matching."""
    return term.replace("-", " ")
```

#### Limitações
- Hífen deve ser substituído por espaço automaticamente (pré-processamento obrigatório)
- Máximo de 2000 resultados por requisição
- Rate limit de 3 segundos entre requisições

---

### PubMed

**Base URL:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`

**Documentação:** https://www.ncbi.nlm.nih.gov/books/NBK25500/

#### Processo de Busca (2 etapas)

1. **esearch.fcgi**: Busca e retorna lista de PMIDs
2. **efetch.fcgi**: Recupera metadados completos por PMID

#### Conversão de Operadores

| Findpapers | PubMed |
|------------|--------|
| `AND` | `AND` |
| `OR` | `OR` |
| `AND NOT` | `NOT` |
| `[termo]` | `"termo"[campo]` |
| `(...)` | `(...)` |

#### Tags de Campo

| Campo | Tag PubMed | Descrição |
|-------|------------|-----------|
| Título | `[ti]` | Apenas título |
| Título+Abstract | `[tiab]` | Título e abstract |
| Abstract | `[ab]` | Apenas abstract |
| Autor | `[au]` | Nome do autor |
| Keywords/MeSH | `[mh]` | MeSH terms |
| Journal | `[journal]` | Nome do periódico |
| Afiliação | `[ad]` | Afiliação do autor |
| Data | `[pdat]` | Data de publicação |

#### Filtro de Data

```
mindate=YYYY/MM/DD&maxdate=YYYY/MM/DD&datetype=pdat
```

#### Exemplo de Conversão

**Query Findpapers:**
```
[machine learning] AND ([nlp] OR [natural language processing])
```

**Query PubMed:**
```
("machine learning"[tiab]) AND ("nlp"[tiab] OR "natural language processing"[tiab])
```

#### Limitações
- Wildcard `?` não é suportado
- Rate limit: 3 req/seg (sem API key) ou 10 req/seg (com API key)
- Requer 2 chamadas de API (esearch + efetch)

---

### IEEE Xplore

**Base URL:** `https://ieeexploreapi.ieee.org/api/v1/search/articles`

**Documentação:** https://developer.ieee.org/docs/read/Metadata_API_details

#### Conversão de Operadores

| Findpapers | IEEE |
|------------|------|
| `AND` | `AND` |
| `OR` | `OR` |
| `AND NOT` | `NOT` |
| `[termo]` | `"termo"` |
| `(...)` | `(...)` |

#### Parâmetros de Campo

| Campo | Parâmetro IEEE | Descrição |
|-------|----------------|-----------|
| Todos | `querytext` | Busca em todos os campos |
| Título | `article_title` | Título do artigo |
| Abstract | `abstract` | Resumo |
| Autor | `author` | Nome do autor |
| Keywords | `index_terms` | Termos de indexação (IEEE + Author + MeSH) |
| Publicação | `publication_title` | Nome da publicação |
| Afiliação | `affiliation` | Afiliação (mín 3 caracteres) |

#### Filtro de Data

```
start_year=YYYY&end_year=YYYY
```

#### Exemplo de Conversão

**Query Findpapers:**
```
[machine learning] AND ([nlp] OR [natural language processing])
```

**Query IEEE (via querytext):**
```
querytext=("machine learning" AND ("nlp" OR "natural language processing"))
```

**Query IEEE (com campos):**
```
abstract="machine learning"&article_title="nlp"
```

#### Limitações
- Requer API key
- Máximo de 200 resultados por requisição
- Wildcard `?` não é suportado
- Wildcard `*` requer mínimo de 3 caracteres antes

---

### Scopus

**Base URL:** `https://api.elsevier.com/content/search/scopus`

**Documentação:** https://dev.elsevier.com/sc_search_tips.html

#### Conversão de Operadores

| Findpapers | Scopus |
|------------|--------|
| `AND` | `AND` |
| `OR` | `OR` |
| `AND NOT` | `AND NOT` |
| `[termo]` | `"termo"` |
| `(...)` | `(...)` |
| `{frase exata}` | Busca exata com caracteres especiais |

#### Campos de Busca

| Campo | Código Scopus | Descrição |
|-------|---------------|-----------|
| Título+Abs+Key | `TITLE-ABS-KEY()` | Combinação padrão |
| Título | `TITLE()` | Apenas título |
| Abstract | `ABS()` | Apenas abstract |
| Keywords | `KEY()` | Palavras-chave (autor + índice + químicas) |
| Autor | `AUTH()` | Nome do autor |
| Autor ID | `AU-ID()` | ID único do autor no Scopus |
| Afiliação | `AFFIL()` | Afiliação completa |
| Publicação | `SRCTITLE()` | Título da fonte |
| DOI | `DOI()` | Digital Object Identifier |
| Todos | `ALL()` | Todos os campos disponíveis |

#### Filtro de Data

```
PUBYEAR > 2019 AND PUBYEAR < 2023
```

Ou via parâmetro:
```
date=2020-2022
```

#### Operadores de Proximidade

| Operador | Descrição |
|----------|-----------|
| `W/n` | Termos dentro de n palavras, qualquer ordem |
| `PRE/n` | Primeiro termo precede o segundo em até n palavras |

#### Exemplo de Conversão

**Query Findpapers:**
```
[machine learning] AND ([nlp] OR [natural language processing])
```

**Query Scopus:**
```
TITLE-ABS-KEY("machine learning" AND ("nlp" OR "natural language processing"))
```

**Com campos específicos:**
```
TITLE("machine learning") AND ABS("nlp" OR "natural language processing")
```

#### Limitações
- Requer API key
- Ordem de precedência diferente: OR > AND > AND NOT
- Recomendado usar parênteses explícitos
- Views diferentes (STANDARD vs COMPLETE) têm restrições de acesso

---

### bioRxiv

**Base URL (busca):** `https://www.medrxiv.org/search/`

**Base URL (API):** `https://api.biorxiv.org/`

**Documentação:** https://www.medrxiv.org/content/search-tips

#### Processo de Busca (2 etapas)

1. **Web Scraping**: Busca no site para obter DOIs
2. **API**: Recupera metadados por DOI

#### Sintaxe de Busca (URL-encoded)

```
/search/abstract_title%3A{termos}%20abstract_title_flags%3A{flag}%20jcode%3Abiorxiv%20...
```

#### Flags de Busca

| Flag | Significado |
|------|-------------|
| `match-all` | Todos os termos devem aparecer (AND) |
| `match-any` | Qualquer termo pode aparecer (OR) |

#### Conversão de Operadores

| Findpapers | bioRxiv |
|------------|---------|
| `AND` | `match-all` + termos separados por `+` |
| `OR` | `match-any` + termos separados por `+` |
| `AND NOT` | ❌ Não suportado |
| `(...)` | Múltiplas requisições |

#### Limitações Severas

- ❌ **Não suporta AND NOT**
- ❌ **Não suporta wildcards**
- ⚠️ Apenas 1 nível de parênteses
- ⚠️ Apenas OR entre grupos de parênteses
- ⚠️ Não permite misturar AND e OR no mesmo grupo
- ⚠️ Requer web scraping (não há API de busca)
- ⚠️ Busca apenas em título e abstract combinados

#### Estratégia para Queries Complexas

Para queries como:
```
([termo A] OR [termo B]) AND ([termo C] OR [termo D])
```

É necessário fazer **N requisições** para cada combinação:
1. `termo A + termo C` (match-all)
2. `termo A + termo D` (match-all)
3. `termo B + termo C` (match-all)
4. `termo B + termo D` (match-all)

E depois unir os resultados (removendo duplicatas).

#### Limite de Combinações

Quando a query resultar em um número elevado de combinações, a busca **será executada normalmente** em todas as combinações, porém um **warning será logado** informando ao usuário que a busca poderá demorar.

O **limite de alerta é de 20 combinações**. Acima disso, o usuário é notificado sobre o potencial tempo de execução.

**Nota**: Este limite de alerta se aplica a **todos os bancos** (IEEE, bioRxiv, medRxiv, etc.) que precisem expandir a query em múltiplas requisições devido a limitações de suporte a operadores booleanos ou campos compostos.

Ver seção [Limite Global de Combinações](#limite-global-de-combinações) para detalhes de implementação.

---

### medRxiv

**Idêntico ao bioRxiv**, com as seguintes diferenças:

- `jcode`: `medrxiv` em vez de `biorxiv`
- API: `https://api.medrxiv.org/` (mas usa `api.biorxiv.org` para detalhes)

Todas as limitações do bioRxiv se aplicam.

---

### OpenAlex

**Base URL:** `https://api.openalex.org/works`

**Documentação:** https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities

#### Visão Geral

OpenAlex é um catálogo aberto de papers acadêmicos que oferece uma API REST com suporte robusto a buscas booleanas e filtros avançados. A busca pode ser feita via parâmetro `search` (busca geral em título, abstract e fulltext) ou via `filter` com operadores `.search`.

#### Conversão de Operadores

| Findpapers | OpenAlex |
|------------|----------|
| `AND` | `,` (vírgula) entre filters, ou espaço em `search` |
| `OR` | `\|` (pipe) dentro do mesmo filter |
| `AND NOT` | `!` (prefixo de negação) |
| `[termo]` | `termo` ou `"termo"` |
| `(...)` | `(...)` em boolean search |

#### Sintaxe de Boolean Search

OpenAlex suporta operadores booleanos (`AND`, `OR`, `NOT`) em maiúsculas dentro do parâmetro `search`:

```
?search=(elmo AND "sesame street") NOT (cookie OR monster)
```

**Importante**: Wildcards (`*`, `?`, `~`) **não são suportados**. Se a query contiver wildcards, a busca no OpenAlex será **abortada**.

#### Stemming

OpenAlex aplica stemming por padrão. Para **desabilitar o stemming** e buscar termos exatos, usar o sufixo `.no_stem`:

```
filter=title.search.no_stem:surgery
filter=abstract.search.no_stem:surgery
filter=title_and_abstract.search.no_stem:surgery
```

**Recomendação**: Por padrão, o Findpapers deve usar `.no_stem` para garantir precisão nas buscas e comportamento consistente entre bancos.

#### Parâmetros de Filtro/Busca

| Campo | Parâmetro OpenAlex | Descrição |
|-------|-------------------|-----------|
| Título | `title.search:` ou `display_name.search:` | Busca no título |
| Abstract | `abstract.search:` | Busca no abstract |
| Título+Abstract | `title_and_abstract.search:` | Combinação de título e abstract |
| Todos | `search` | Busca em título, abstract e fulltext |
| Autor | `authorships.author.display_name.search:` | Nome do autor |
| Afiliação | `authorships.institutions.display_name.search:` | Instituição |
| Publicação | `primary_location.source.display_name.search:` | Nome da fonte |
| Conceitos | `concepts.display_name:` | Conceitos (similar a keywords) |

#### Filtro de Data

```
filter=from_publication_date:2022-01-01,to_publication_date:2022-12-31
```

Ou usando o filtro `publication_year`:
```
filter=publication_year:2022
filter=publication_year:2020-2023
```

#### Exemplo de Conversão

**Query Findpapers:**
```
[machine learning] AND ([nlp] OR [natural language processing]) AND NOT [deep learning]
```

**Query OpenAlex (via search):**
```
?search=("machine learning" AND ("nlp" OR "natural language processing")) NOT "deep learning"
```

**Query OpenAlex (via filter):**
```
?filter=title_and_abstract.search:machine learning,title_and_abstract.search:nlp|natural language processing
```

#### Limitações
- Não suporta wildcards (`*`, `?`, `~`) - query será abortada se contiver wildcards
- OR só pode ser usado **dentro** do mesmo filter, não entre filters diferentes
- Rate limit: 10 req/seg (sem API key polite pool) ou 100k req/dia (com API key)
- Máximo de 10.000 resultados via paginação padrão, cursor para mais

#### Peculiaridades
- Usa stemming por padrão - **Findpapers deve usar `.no_stem` para precisão**
- Remove stop words automaticamente
- Suporte a busca semântica via endpoint separado (`/works/similar`)
- Busca em fulltext quando disponível

---

### Semantic Scholar

**Base URL:** `https://api.semanticscholar.org/graph/v1/`

**Documentação:** https://api.semanticscholar.org/api-docs

#### Visão Geral

Semantic Scholar oferece duas APIs principais de busca:
1. **Paper Relevance Search** (`/paper/search`): Busca simples por relevância, limite de 1.000 resultados
2. **Paper Bulk Search** (`/paper/search/bulk`): Busca com boolean operators, até 10 milhões de resultados

A **Bulk Search** é a mais adequada para queries complexas do Findpapers.

#### Conversão de Operadores (Bulk Search)

| Findpapers | Semantic Scholar Bulk |
|------------|----------------------|
| `AND` | `+` ou espaço (implícito) |
| `OR` | `\|` (pipe) |
| `AND NOT` | `-` (prefixo) |
| `[termo]` | `termo` ou `"termo"` |
| `(...)` | `(...)` |

#### Sintaxe de Boolean Search (Bulk)

```
query=fish ladder              # fish AND ladder
query=fish -ladder             # fish AND NOT ladder
query=fish | ladder            # fish OR ladder
query="fish ladder"            # frase exata
query=(fish ladder) | outflow  # (fish AND ladder) OR outflow
```

**Operadores adicionais**:
- `~N` após palavra: fuzzy match (edit distance N, default 2)
- `~N` após frase: termos podem estar separados por até N palavras
- Prefixo `*` para match de prefixo (ex: `mach*` para "machine")

#### Parâmetros de Filtro

| Campo | Parâmetro | Descrição |
|-------|-----------|-----------|
| Ano | `year` | `2019`, `2016-2020`, `2010-`, `-2015` |
| Data | `publicationDateOrYear` | `2019-03-05`, `2019-03`, `2016-03-05:2020-06-06` |
| Venue | `venue` | Nome da publicação (ex: `Nature,Radiology`) |
| Tipo | `publicationTypes` | `Review`, `JournalArticle`, `Conference`, etc. |
| Campo de estudo | `fieldsOfStudy` | `Computer Science`, `Medicine`, etc. |
| Citações mínimas | `minCitationCount` | Ex: `200` |
| PDF aberto | `openAccessPdf` | Sem valor (apenas presença) |

#### Processo de Busca

**Relevance Search** (`/paper/search`):
- Query em plain-text, sem boolean
- Busca em título e abstract
- Limite de 1.000 resultados
- Ordenado por relevância

**Bulk Search** (`/paper/search/bulk`):
- Suporte a boolean operators
- Query opcional (pode usar apenas filtros)
- Até 10 milhões de resultados via token de paginação
- Ordenação por `paperId`, `publicationDate`, ou `citationCount`

#### Filtro de Data

```
year=2019
year=2016-2020
publicationDateOrYear=2019-03-05:2020-06-06
```

#### Exemplo de Conversão

**Query Findpapers:**
```
[machine learning] AND ([nlp] OR [natural language processing]) AND NOT [deep learning]
```

**Query Semantic Scholar (Bulk Search):**
```
/paper/search/bulk?query="machine learning" (nlp | "natural language processing") -"deep learning"
```

**Query Semantic Scholar (Relevance Search):**
```
/paper/search?query=machine learning nlp
```
(Nota: Relevance Search não suporta boolean operators, então seria uma busca simplificada)

#### Endpoints de Suporte

| Endpoint | Descrição |
|----------|-----------|
| `/paper/{id}` | Detalhes de um paper por ID |
| `/paper/batch` | Detalhes de múltiplos papers (até 500) |
| `/paper/search` | Busca por relevância |
| `/paper/search/bulk` | Busca bulk com boolean |
| `/paper/search/match` | Busca exata por título |
| `/author/search` | Busca por autor |

#### IDs Suportados

Semantic Scholar aceita diversos formatos de ID:
- Semantic Scholar ID: `649def34f8be52c8b66281af98ae884c09aef38b`
- CorpusId: `CorpusId:215416146`
- DOI: `DOI:10.18653/v1/N18-3011`
- arXiv: `ARXIV:2106.15928`
- PubMed: `PMID:19872477`
- ACL: `ACL:W12-3903`

#### Limitações
- **Relevance Search**: Não suporta boolean operators, limite 1.000 resultados
- **Bulk Search**: Sem busca por campo específico (título, abstract separadamente)
- Wildcards tradicionais (`*`, `?`) não suportados (usa `~` para fuzzy)
- Hífen é tratado incorretamente (substituir por espaço)
- Rate limit: 1 req/seg (sem API key) ou 10 req/seg (com API key)
- Máximo de 10 MB de dados por requisição

#### Peculiaridades
- Busca apenas em título e abstract combinados (não permite separar)
- Filtros por autor e venue são via parâmetros separados, não na query
- Suporte a fuzzy search nativo
- API de autocomplete disponível para sugestões
- TLDR (resumo automático) disponível nos resultados

---

## Busca por Campos Específicos

### Proposta de Sintaxe

A proposta é estender a sintaxe atual permitindo especificar campos antes do termo:

```
abs[termo1] AND key[termo2]
```

Campos compostos (usando `:` como separador):
```
abs:ti[termo1] AND key[termo2]
```

Comportamento padrão (quando omitido):
```
[termo1]  ==  ti:abs[termo1]
```

**Todas as bases usam `ti:abs` como comportamento padrão.** Keywords (`key`) não são incluídas por padrão, mas podem ser adicionadas explicitamente quando desejado.

### Comportamento Padrão por Base

Quando o campo é omitido (ex: `[termo]`), **todas as bases buscam em título + abstract (`ti:abs`)**:

| Base | Comportamento Padrão | Campo Real | Para incluir Keywords |
|------|---------------------|------------|----------------------|
| **arXiv** | `ti:abs` | `ti:x OR abs:x` | ❌ Não disponível |
| **PubMed** | `ti:abs` | `[tiab]` | `[tiab] OR [mh]` |
| **IEEE** | `ti:abs` | `("Abstract":x OR "Article Title":x)` | Adicionar `OR "Index Terms":x` |
| **Scopus** | `ti:abs` | `TITLE-ABS()` | `TITLE-ABS-KEY()` |
| **bioRxiv** | `ti:abs` | `abstract_title` | ❌ Não disponível |
| **medRxiv** | `ti:abs` | `abstract_title` | ❌ Não disponível |
| **OpenAlex** | `ti:abs` | `title_and_abstract.search` | Combinar com `concepts.display_name` |
| **Semantic Scholar** | `ti:abs` | `query` | ❌ Não disponível |

#### Detalhamento do Comportamento Padrão

**arXiv** - `ti:termo OR abs:termo`
- Equivalente exato: `ti:abs`
- Combinação explícita de título e abstract
- **Alternativa ampla**: `all:termo` inclui au, co, jr, cat, id (não recomendado como padrão)

**PubMed** - `termo[tiab]`
- Equivalente: `ti:abs`
- Para incluir MeSH terms (keywords), seria necessário: `termo[tiab] OR termo[mh]`
- **Tradeoff**: Por padrão não inclui keywords. Pode expandir para `[tiab] OR [mh]` se desejado.

**IEEE** - `querytext=("Abstract":termo OR "Article Title":termo)`
- Equivalente exato: `ti:abs`
- Usa querytext com campos inline para combinar título e abstract
- **Alternativa ampla**: `querytext=termo` busca em todos os campos
- **Para incluir keywords**: adicionar `OR "Index Terms":termo`

**Scopus** - `TITLE-ABS(termo)`
- Equivalente exato: `ti:abs`
- Combinação nativa de título e abstract (sem keywords)
- **Alternativa ampla**: `TITLE-ABS-KEY(termo)` inclui keywords
- **Para incluir keywords**: usar `TITLE-ABS-KEY()` explicitamente

**bioRxiv / medRxiv** - `abstract_title:termo`
- Equivalente: `ti:abs`
- Não há campo de keywords disponível
- **Tradeoff**: Sem alternativa, keywords serão ignorados

**OpenAlex** - `filter=title_and_abstract.search:termo`
- Equivalente: `ti:abs`
- Busca apenas em título e abstract (sem fulltext)
- **Alternativa ampla**: `search=termo` inclui fulltext quando disponível
- **Para incluir keywords**: combinar com `concepts.display_name`
- **Tradeoff**: Sem keywords por padrão, mas comportamento mais preciso que `search`

**Semantic Scholar** - `query=termo`
- Equivalente: `ti:abs`
- Não há campo de keywords na busca
- **Tradeoff**: Como não suporta keywords (`key`), se a query solicitar este campo, a busca será **abortada**.

#### Configuração de Comportamento Padrão

```python
DEFAULT_FIELD_BEHAVIOR = {
    'arxiv': {
        'default_fields': ['ti', 'abs'],
        'actual_field': 'ti:x OR abs:x',  # Combinação explícita
        'includes_extra': [],
        'missing_fields': ['key'],
        'alternative_field': 'all',  # Inclui campos extras (au, co, jr, cat, id)
    },
    'pubmed': {
        'default_fields': ['ti', 'abs'],
        'actual_field': '[tiab]',
        'includes_extra': [],
        'missing_fields': ['key'],
        'optional_expansion': '[tiab] OR [mh]',  # Expansão opcional para incluir keywords
    },
    'ieee': {
        'default_fields': ['ti', 'abs'],
        'actual_field': '("Abstract":x OR "Article Title":x)',  # Via querytext
        'includes_extra': [],
        'missing_fields': ['key'],
        'alternative_field': 'querytext',  # Busca em todos os campos
        'optional_expansion': '("Abstract":x OR "Article Title":x OR "Index Terms":x)',
    },
    'scopus': {
        'default_fields': ['ti', 'abs'],
        'actual_field': 'TITLE-ABS',
        'includes_extra': [],
        'missing_fields': ['key'],
        'alternative_field': 'TITLE-ABS-KEY',  # Inclui keywords
    },
    'biorxiv': {
        'default_fields': ['ti', 'abs'],
        'actual_field': 'abstract_title',
        'includes_extra': [],
        'missing_fields': ['key'],
    },
    'medrxiv': {
        'default_fields': ['ti', 'abs'],
        'actual_field': 'abstract_title',
        'includes_extra': [],
        'missing_fields': ['key'],
    },
    'openalex': {
        'default_fields': ['ti', 'abs'],
        'actual_field': 'title_and_abstract.search',
        'includes_extra': [],
        'missing_fields': ['key'],
        'alternative_field': 'search',  # Inclui fulltext
        'optional_expansion': 'concepts.display_name',  # Para aproximar keywords
    },
    'semanticscholar': {
        'default_fields': ['ti', 'abs'],
        'actual_field': 'query',
        'includes_extra': [],
        'missing_fields': ['key'],
    },
}
```

#### Recomendação de Implementação

1. **Comportamento padrão conservador**: Usar o campo que melhor representa `ti:abs` sem incluir campos extras indesejados
2. **Flag de expansão**: Permitir configuração para expandir a busca incluindo keywords quando disponível
3. **Erro e Skip**: Se a query utilizar um campo não suportado pela base (ex: `key[...]` no Semantic Scholar ou `ti[...]` separado no bioRxiv), o searcher deve logar um erro informando a incompatibilidade e **pular a busca nesta base**. Não deve haver fallback silencioso ou parcial.

```python
def get_default_query_field(database: str, include_keywords: bool = False) -> str:
    """
    Retorna o campo padrão a ser usado quando nenhum campo é especificado.
    
    Args:
        database: Nome do banco de dados
        include_keywords: Se True, tenta incluir keywords quando disponível
    """
    config = DEFAULT_FIELD_BEHAVIOR[database]
    
    if include_keywords and 'optional_expansion' in config:
        return config['optional_expansion']
    
    return config['actual_field']
```

### Códigos de Campo Propostos

| Código | Campo | Descrição |
|--------|-------|-----------|
| `ti` | Título | Busca no título |
| `abs` | Abstract | Busca no resumo |
| `key` | Keywords | Busca nas palavras-chave |
| `au` | Autor | Busca por autor |
| `pu` | Publicação | Busca pelo nome da publicação |
| `af` | Afiliação | Busca pela instituição |

### Mapeamento por Banco

| Findpapers | arXiv | PubMed | IEEE | Scopus | OpenAlex | Semantic Scholar |
|------------|-------|--------|------|--------|----------|------------------|
| `ti[x]` | `ti:x` | `x[ti]` | `article_title=x` | `TITLE(x)` | `filter=title.search:x` | ❌ N/A |
| `abs[x]` | `abs:x` | `x[ab]` | `abstract=x` | `ABS(x)` | `filter=abstract.search:x` | ❌ N/A |
| `key[x]` | ❌ N/A | `x[mh]` | `index_terms=x` | `KEY(x)` | ⚠️ `concepts.display_name` | ❌ N/A |
| `au[x]` | `au:x` | `x[au]` | `author=x` | `AUTH(x)` | `authorships.author.display_name.search:x` | ⚠️ `authors` filter |
| `pu[x]` | ❌ N/A | `x[journal]` | `publication_title=x` | `SRCTITLE(x)` | `primary_location.source.display_name.search:x` | ⚠️ `venue` filter |
| `af[x]` | ❌ N/A | `x[ad]` | `affiliation=x` | `AFFIL(x)` | `authorships.institutions.display_name.search:x` | ❌ N/A |
| `ti:abs[x]` | `ti:x OR abs:x` | `x[tiab]` | ⚠️ 2 req | `TITLE(x) OR ABS(x)` | `filter=title_and_abstract.search:x` | ✅ `query=x` (nativo) |
| `ti:abs:key[x]` | `all:x` | `x[tiab]` | `querytext=x` | `TITLE-ABS-KEY(x)` | `search=x` | ✅ `query=x` (nativo) |

### Viabilidade por Banco

#### arXiv
- ✅ `ti`, `abs`, `au` - suporte nativo
- ❌ `key`, `pu`, `af` - não disponíveis
- ✅ Campos compostos via OR

#### PubMed
- ✅ Todos os campos suportados
- ✅ Tag especial `[tiab]` para título+abstract
- ✅ Campos compostos via OR

#### IEEE
- ✅ Todos os campos como parâmetros separados
- ⚠️ **Tradeoff**: Para combinar campos na mesma query, é necessário usar `querytext` com sintaxe de campo inline ou fazer múltiplas requisições

Exemplo IEEE com campos específicos:
```
abstract="machine learning"&article_title="nlp"
```

Ou via querytext:
```
querytext=("Abstract":"machine learning" AND "Article Title":"nlp")
```

#### Scopus
- ✅ Todos os campos suportados nativamente
- ✅ Campos compostos via wrappers como `TITLE-ABS-KEY()`

#### bioRxiv / medRxiv
- ⚠️ Busca apenas em `abstract_title` (título + abstract combinados)
- ❌ Não permite separar título de abstract
- ❌ Não suporta keywords, autor, publicação, afiliação
- **Tradeoff**: Ignorar campos não suportados ou não executar busca se campos específicos forem requeridos

#### OpenAlex
- ✅ `ti`, `abs` - suporte nativo via `.search` filters
- ✅ `au`, `af`, `pu` - suporte via filters específicos
- ⚠️ `key` - não há campo direto, mas `concepts` pode ser usado como aproximação
- ✅ Campos compostos: `title_and_abstract.search` combina título e abstract
- ✅ Suporte completo a boolean (AND, OR, NOT) via parâmetro `search`

#### Semantic Scholar
- ❌ `ti`, `abs`, `key`, `af` - **não permite busca por campo específico**
- ⚠️ `au` - apenas via filtro `authors`, não na query principal
- ⚠️ `pu` - apenas via filtro `venue`, não na query principal
- ✅ Busca geral em título+abstract combinados (nativo)
- ✅ Boolean operators suportados na Bulk Search API
- **Comportamento**: Se a query contiver especificadores de campo não suportados (`ti`, `abs`, `key`, `af`), a busca deverá ser **abortada** para esta base.

---

## Tratamento de Campos Compostos

Esta seção detalha como campos compostos (ex: `ti:abs[termo]`) serão tratados em cada banco, incluindo o número de requisições necessárias.

### Estratégia Geral

Quando um termo possui múltiplos campos (ex: `ti:abs:key[machine learning]`), existem três possíveis abordagens dependendo do suporte do banco:

1. **Suporte Nativo a OR entre Campos**: Uma única requisição com OR
2. **Múltiplas Requisições**: N requisições (uma por campo), unindo resultados
3. **Campo Agregado**: Usar campo que já combina os desejados (ex: `all:` no arXiv)

### Tabela de Estratégias por Banco

| Composição | arXiv | PubMed | IEEE | Scopus | bioRxiv/medRxiv | OpenAlex | Semantic Scholar |
|------------|-------|--------|------|--------|-----------------|----------|------------------|
| `ti:abs[x]` | 1 req (`ti:x OR abs:x`) | 1 req (`x[tiab]`) | 2 req | 1 req (`TITLE(x) OR ABS(x)`) | 1 req (nativo) | 1 req (`title_and_abstract.search`) | 1 req (nativo) |
| `ti:key[x]` | ❌ (key N/A) | 2 req | 2 req | 1 req (`TITLE(x) OR KEY(x)`) | ❌ | ⚠️ 2 req | ❌ (key N/A) |
| `abs:key[x]` | ❌ (key N/A) | 2 req | 2 req | 1 req (`ABS(x) OR KEY(x)`) | ❌ | ⚠️ 2 req | ❌ (key N/A) |
| `ti:abs:key[x]` | 1 req (`all:x`) | 1 req (`x[tiab]`) | 1 req (`querytext`) | 1 req (`TITLE-ABS-KEY(x)`) | 1 req (nativo) | 1 req (`search`) | 1 req (nativo) |
| `au:af[x]` | ❌ (af N/A) | 2 req | 2 req | 1 req (`AUTH(x) OR AFFIL(x)`) | ❌ | 2 req | ❌ (af N/A) |
| `ti:abs:au[x]` | 2 req | 3 req | 3 req | 1 req | ❌ | 2 req | ⚠️ 1+filter |

**Legenda:**
- `N req` = Número de requisições necessárias
- ❌ = Pelo menos um campo não é suportado

### Detalhamento por Banco

#### arXiv - Campos Compostos

O arXiv suporta OR diretamente na query string, então campos compostos podem ser resolvidos em **1 requisição** quando todos os campos são suportados:

```
# ti:abs[machine learning]
ti:"machine learning" OR abs:"machine learning"

# ti:abs:au[deep learning]  (au suportado)
ti:"deep learning" OR abs:"deep learning" OR au:"deep learning"
```

**Campos não suportados**: `key`, `pu`, `af`

Quando a composição inclui campo não suportado:
- A operação deve ser **abortada** e um erro logado para o usuário indicando que o arXiv não suporta o campo solicitado.

#### PubMed - Campos Compostos

O PubMed possui algumas tags especiais que combinam campos:
- `[tiab]` = título + abstract
- `[tw]` = text word (todos os campos de texto)

Para outras combinações, é necessário usar OR ou múltiplas requisições:

```
# ti:abs[x] -> tag especial disponível
x[tiab]

# ti:key[x] -> sem tag especial, usar OR
x[ti] OR x[mh]

# ti:abs:key[x] -> OR expandido
x[ti] OR x[ab] OR x[mh]
```

**Estratégia recomendada**: Usar OR na mesma requisição (PubMed suporta bem).

**Número de requisições**: Geralmente **1 requisição** (OR nativo), exceto se a query resultante for muito longa.

#### IEEE - Campos Compostos

O IEEE usa **parâmetros separados** para cada campo, o que complica composições:

```
# Campo único - parâmetro direto
article_title="machine learning"

# Campos compostos via querytext (1 requisição)
querytext=("Article Title":"machine learning" OR "Abstract":"machine learning")
```

**Problema**: A sintaxe `querytext` com campos inline não é bem documentada.

**Estratégia mais segura**: Múltiplas requisições

```
# ti:abs[machine learning] -> 2 requisições
Requisição 1: article_title="machine learning"
Requisição 2: abstract="machine learning"
-> União dos resultados (remover duplicatas por DOI)
```

**Fórmula**: Para N campos = N requisições

#### Scopus - Campos Compostos

O Scopus é o **mais flexível** - suporta OR entre campos nativamente:

```
# ti:abs[x]
TITLE(x) OR ABS(x)

# ti:abs:key[x] -> campo agregado disponível
TITLE-ABS-KEY(x)

# au:af[x]
AUTH(x) OR AFFIL(x)

# ti:au:pu[x]
TITLE(x) OR AUTH(x) OR SRCTITLE(x)
```

**Número de requisições**: Sempre **1 requisição** (OR nativo completo).

**Campos agregados disponíveis**:
- `TITLE-ABS-KEY()` = título + abstract + keywords
- `ALL()` = todos os campos

#### bioRxiv / medRxiv - Campos Compostos

Estes bancos são os **mais limitados**:

- Busca apenas em `abstract_title` (combinação fixa de título + abstract)
- Não há separação possível entre título e abstract
- Não suportam outros campos (keywords, autor, etc.)

**Mapeamento**:
- **Comportamento**: Se a query contiver campos não suportados (`key`, `au`, `pu`, `af`) ou tentar separar `ti` e `abs` (ex: `ti[termo]`), a busca deve ser **abortada**.

**Mapeamento**:
| Composição Findpapers | Resultado bioRxiv/medRxiv |
|----------------------|--------------------------|
| `ti[x]` | ❌ Erro/Skip |
| `abs[x]` | ❌ Erro/Skip |
| `ti:abs[x]` | ✅ `abstract_title` (comportamento nativo) |
| `key[x]` | ❌ Erro/Skip |
| `au[x]` | ❌ Erro/Skip
**Estratégia**: 
- Composições de `ti` e `abs` funcionam nativamente
- Outros campos são ignorados (com warning) ou causam erro

#### OpenAlex - Campos Compostos

OpenAlex oferece bom suporte a campos separados e alguns campos agregados:

- `title.search` - busca apenas no título
- `abstract.search` - busca apenas no abstract
- `title_and_abstract.search` - busca em título + abstract (campo agregado)
- `search` - busca em título + abstract + fulltext

**Mapeamento**:
| Composição Findpapers | Resultado OpenAlex |
|----------------------|-------------------|
| `ti[x]` | ✅ `filter=title.search:x` |
| `abs[x]` | ✅ `filter=abstract.search:x` |
| `ti:abs[x]` | ✅ `filter=title_and_abstract.search:x` (1 req) |
| `key[x]` | ⚠️ `filter=concepts.display_name:x` (aproximação) |
| `au[x]` | ✅ `filter=authorships.author.display_name.search:x` |
| `ti:abs:key[x]` | ✅ `search=x` (busca geral) |

**Estratégia para campos compostos não agregados**:
```python
# ti:au[machine learning] -> 2 requisições ou OR nativo
# OpenAlex não suporta OR entre filters diferentes
# Solução: múltiplas requisições ou usar search geral
```

**Número de requisições**:
- Campos com agregado disponível: 1 requisição
- Campos sem agregado: N requisições (um por campo)

#### Semantic Scholar - Campos Compostos

Semantic Scholar é **mais limitado** para busca por campos específicos:

- A busca principal (`query`) sempre busca em **título + abstract combinados**
- Não há como separar a busca por título ou abstract individualmente
- Filtros para autor e venue são **separados** da query principal

**Mapeamento**:
| Composição Findpapers | Resultado Semantic Scholar |
|----------------------|---------------------------|
| `ti[x]` | ⚠️ Usa `query=x` (inclui abstract) |
| `abs[x]` | ⚠️ Usa `query=x` (inclui título) |
| `ti:abs[x]` | ✅ `query=x` (comportamento nativo) |
| `key[x]` | ❌ Não suportado |
| `au[x]` | ⚠️ Filtro `authors` separado |
| `pu[x]` | ⚠️ Filtro `venue` separado |
| `af[x]` | ❌ Não suportado |
| `ti:abs:key[x]` | ⚠️ Usa `query=x` (key ignorado) |

**Estratégia para queries com autor**:
```
# ti:abs:au[machine learning] 
# -> query="machine learning"&authors=machine learning
# NOTA: isso não faz sentido semanticamente, 
#       autor deveria ser um termo separado
```

**Tradeoff**: 
- Para buscas de texto (ti, abs, key): usar `query` (sempre combinado)
- Para autor: usar filtro `authors` separadamente
- Para venue: usar filtro `venue` separadamente
- Composições mistas requerem lógica especial

### Cálculo de Requisições para Queries Complexas

Para uma query com múltiplos termos com campos compostos:

```
ti:abs[termo A] AND key[termo B] AND au:af[termo C]
```

**Cenário IEEE** (pior caso):
- `ti:abs[termo A]` = 2 requisições
- `key[termo B]` = 1 requisição  
- `au:af[termo C]` = 2 requisições

Como os termos estão conectados por AND, não podemos simplesmente multiplicar.
A estratégia é:
1. Executar cada combinação de campos separadamente
2. Fazer a interseção (AND) dos resultados em memória

**Total**: 2 + 1 + 2 = 5 requisições + processamento em memória

**Cenário Scopus** (melhor caso):
```
(TITLE(termo A) OR ABS(termo A)) AND KEY(termo B) AND (AUTH(termo C) OR AFFIL(termo C))
```
**Total**: 1 requisição

### Algoritmo de Expansão de Campos Compostos

```python
def expand_composite_fields(term: QueryNode, db_capabilities: dict) -> List[FieldQuery]:
    """
    Expande um termo com campos compostos em queries específicas por banco.
    
    Args:
        term: Nó do termo com fields=['ti', 'abs', 'key']
        db_capabilities: Dict com capacidades do banco
        
    Returns:
        Lista de queries de campo a serem executadas
    """
    fields = term.fields or ['ti', 'abs', 'key']  # default
    
    # Filtrar campos suportados
    supported = [f for f in fields if f in db_capabilities['supported_fields']]
    unsupported = [f for f in fields if f not in db_capabilities['supported_fields']]
    
    if unsupported:
        logger.warning(f"Campos não suportados ignorados: {unsupported}")
    
    # Verificar se há campo agregado disponível
    aggregate_field = db_capabilities.get('aggregate_fields', {}).get(tuple(sorted(supported)))
    
    if aggregate_field:
        # Uma única query com campo agregado
        return [FieldQuery(field=aggregate_field, value=term.value)]
    
    elif db_capabilities.get('supports_field_or', False):
        # Uma query com OR entre campos
        return [FieldQuery(field=supported, value=term.value, operator='OR')]
    
    else:
        # Múltiplas queries, uma por campo
        return [FieldQuery(field=f, value=term.value) for f in supported]
```

### Configuração de Capacidades por Banco

```python
DB_CAPABILITIES = {
    'arxiv': {
        'supported_fields': ['ti', 'abs', 'au'],
        'supports_field_or': True,
        'aggregate_fields': {
            ('abs', 'au', 'ti'): 'all',  # sorted tuple -> aggregate
        },
    },
    'pubmed': {
        'supported_fields': ['ti', 'abs', 'key', 'au', 'pu', 'af'],
        'supports_field_or': True,
        'aggregate_fields': {
            ('abs', 'ti'): 'tiab',
        },
    },
    'ieee': {
        'supported_fields': ['ti', 'abs', 'key', 'au', 'pu', 'af'],
        'supports_field_or': False,  # Requer múltiplas requisições
        'aggregate_fields': {
            ('abs', 'key', 'ti'): 'querytext',
        },
    },
    'scopus': {
        'supported_fields': ['ti', 'abs', 'key', 'au', 'pu', 'af'],
        'supports_field_or': True,
        'aggregate_fields': {
            ('abs', 'key', 'ti'): 'TITLE-ABS-KEY',
        },
    },
    'biorxiv': {
        'supported_fields': ['ti', 'abs'],  # Sempre combinados
        'supports_field_or': False,
        'aggregate_fields': {
            ('abs', 'ti'): 'abstract_title',
        },
        'force_aggregate': True,  # Sempre usa o agregado
    },
    'medrxiv': {
        'supported_fields': ['ti', 'abs'],
        'supports_field_or': False,
        'aggregate_fields': {
            ('abs', 'ti'): 'abstract_title',
        },
        'force_aggregate': True,
    },
    'openalex': {
        'supported_fields': ['ti', 'abs', 'au', 'pu', 'af'],  # key via concepts (aproximação)
        'supports_field_or': False,  # OR não funciona entre filters diferentes
        'aggregate_fields': {
            ('abs', 'ti'): 'title_and_abstract.search',
            ('abs', 'key', 'ti'): 'search',  # busca geral
        },
        'field_mapping': {
            'ti': 'title.search',
            'abs': 'abstract.search',
            'au': 'authorships.author.display_name.search',
            'pu': 'primary_location.source.display_name.search',
            'af': 'authorships.institutions.display_name.search',
            'key': 'concepts.display_name',  # aproximação
        },
    },
    'semanticscholar': {
        'supported_fields': ['ti', 'abs'],  # au e pu são filtros separados
        'supports_field_or': False,
        'aggregate_fields': {
            ('abs', 'ti'): 'query',  # busca nativa é ti+abs
            ('abs', 'key', 'ti'): 'query',
        },
        'force_aggregate': True,  # Sempre usa query para campos de texto
        'separate_filters': ['au', 'pu'],  # Campos tratados como filtros separados
        'filter_mapping': {
            'au': 'authors',
            'pu': 'venue',
        },
    },
}

### Busca com Filtro em Grupos

É possível aplicar filtros de campo a um grupo inteiro, propagando essa restrição para todos os termos dentro do grupo.

**Sintaxe**: `campos:([expressão])`

Exemplo: `abs:([term a] OR [term b])`

Isso equivale semanticamente a: `abs:[term a] OR abs:[term b]`

#### Regras de Propagação

A propagação de campos segue um modelo de "herança com override explícito", onde **o grupo mais interno sempre tem prioridade**. Quando um campo é especificado em um nó de Grupo (GROUP), ele é passado para os nós filhos de acordo com as seguintes regras:

1.  **Herança**: Se um nó filho (TERM ou outro GROUP) não possui campos especificados, ele herda os campos do nó pai.
2.  **Explicitude (Override)**: Se um nó filho possui campos explicitamente definidos na query, esses campos têm precedência sobre os campos herdados do pai. **O grupo mais interno sempre vence.**
    *   *Exemplo*: `abs:([a] OR ti:[b])` -> O termo `a` herda `abs`. O termo `b` usa `ti` (ignora `abs`).
    *   *Exemplo com grupos aninhados*: `abs:(ti:([A] OR [B]))` -> **Ambos os termos `A` e `B` usam apenas `ti`**, pois o grupo interno `ti:(...)` tem prioridade sobre o externo `abs:(...)`.
3.  **Default**: Se nenhum campo for especificado nem no termo nem herdado de nenhum ancestral, aplica-se o comportamento padrão (geralmente `ti:abs`, mas configurável por banco).

**Importante**: A prioridade é sempre do **mais interno para o mais externo**. O campo mais próximo do termo é o que será aplicado.

#### Compilação Prévia (Universalidade)

Como a propagação ocorre na etapa de parsing/pré-processamento do `findpapers` (antes da conversão para a API específica), **essa funcionalidade é compatível com todas as bases de dados**.

O adaptador de cada base receberá a query já expandida (ex: `abs:[a] OR abs:[b]`) e apenas precisará converter os termos individuais conforme sua capacidade, sem precisar saber que eles vieram de um grupo.

#### Exemplos de Conversão

| Query Original | Interpretação Lógica |
| :--- | :--- |
| `abs:([covid] OR [sars])` | `abs:[covid] OR abs:[sars]` |
| `ti:([machine learning] AND au:[bengio])` | `ti:[machine learning] AND au:[bengio]` *(au tem precedência no segundo termo)* |
| `ti:abs:([a] OR [b])` | `ti:abs:[a] OR ti:abs:[b]` |
| `ti:(abs:[a] OR key:[b])` | `abs:[a] OR key:[b]` |
```

---

## Estratégia de Implementação

### 1. Extensão do Modelo Query

Modificar a classe `Query` para suportar campos opcionais nos termos:

```python
@dataclass
class QueryNode:
    node_type: NodeType
    value: Optional[str] = None
    fields: Optional[List[str]] = None  # ['ti', 'abs', 'key'] ou None para default
    children: List["QueryNode"] = field(default_factory=list)
```

### 2. Parser de Campo e Grupos

Atualizar lógica de parsing para suportar campos em termos e em grupos.

```python
# Padrão base para campos (opcional) seguido de:
# 1. Termo entre parênteses ou colchetes
FIELD_PREFIX_PATTERN = r'(?:([a-z]+(?::[a-z]+)*):)?'
```

### 3. Propagação de Campos (Visitor)

Implementar lógica (ex: `Query.propagate_fields()`) que percorre a árvore após o parsing inicial e distribui os campos dos grupos para os termos filhos.

```python
def propagate_fields(node: QueryNode, parent_fields: List[str] = None):
    # Se o nó tem campos explícitos, eles prevalecem (override)
    current_fields = node.fields or parent_fields
    
    if node.node_type == NodeType.TERM:
        # Atribui campos finais ao termo
        node.fields = current_fields
        
    elif node.node_type == NodeType.GROUP:
        # Recursão para filhos passando os campos atuais
        for child in node.children:
            propagate_fields(child, current_fields)
        # Limpa campos do grupo para simplificar conversão subsequente
        node.fields = None 
```

### 4. Interface de Conversão no Searcher

Cada searcher implementará métodos de validação e conversão:

```python
class SearcherBase(ABC):
    @abstractmethod
    def validate_query(self, query: Query) -> QueryValidationResult:
        """Valida se a query é compatível com este banco.
        
        Deve verificar:
        - Conectores suportados (AND, OR, AND NOT)
        - Wildcards suportados (?, *)
        - Campos suportados (ti, abs, key, au, pu, af)
        - Nível de aninhamento de grupos
        - Qualquer outra limitação específica do banco
        
        Returns:
            QueryValidationResult indicando se a query é válida e quais
            features não são suportadas.
        """
        pass
    
    @abstractmethod
    def convert_query(self, query: Query) -> Union[str, Dict[str, Any]]:
        """Converte o objeto Query para o formato específico do banco.
        
        Este método só deve ser chamado APÓS validate_query() retornar válido.
        
        Returns:
            Query string ou dict de parâmetros no formato do banco.
        """
        pass
    
    @abstractmethod
    def preprocess_terms(self, query: Query) -> Query:
        """Aplica pré-processamento específico do banco nos termos.
        
        Exemplos:
        - arXiv: substituir hífens por espaços
        - Outros: escapar caracteres especiais
        
        Returns:
            Query com termos pré-processados.
        """
        pass
```

### 5. Validação de Query por Banco

Cada searcher deve implementar um método de validação que verifica se a query é compatível com o banco **antes** de executar a busca:

```python
class SearcherBase(ABC):
    @abstractmethod
    def validate_query(self, query: Query) -> QueryValidationResult:
        """Valida se a query é compatível com este banco de dados.
        
        Returns:
            QueryValidationResult com status e lista de incompatibilidades.
        """
        pass

@dataclass
class QueryValidationResult:
    is_valid: bool
    unsupported_features: List[str]  # Ex: ['wildcard ?', 'field:key', 'AND NOT']
    error_message: Optional[str] = None
```

### 6. Tratamento de Features Não Suportadas - Política de Skip

**Não há fallback.** Se qualquer feature da query (conector, wildcard, campo de busca, etc.) não for suportada pelo banco, a busca naquele banco específico será **completamente abortada** e um erro será logado para o usuário explicando o motivo.

```python
def search_database(self, query: Query) -> List[Paper]:
    validation = self.validate_query(query)
    
    if not validation.is_valid:
        logger.error(
            f"Busca em {self.name} abortada: query incompatível. "
            f"Features não suportadas: {', '.join(validation.unsupported_features)}. "
            f"{validation.error_message}"
        )
        return []  # Skip this database entirely
    
    # Proceed with search...
```

**Exemplos de features que causam skip**:
- Uso de `AND NOT` em bioRxiv/medRxiv
- Uso de wildcard `?` em PubMed, IEEE, OpenAlex, Semantic Scholar
- Uso de campo `key[...]` em arXiv ou Semantic Scholar
- Uso de campo `ti[...]` separado em bioRxiv/medRxiv
- Uso de campo `af[...]` em arXiv ou Semantic Scholar

**Importante**: A busca continua normalmente nos demais bancos que suportam a query.

### 7. Geração de Múltiplas Queries

Para bancos com limitações que requerem múltiplas requisições, implementar expansão de query.

#### Limite Global de Combinações

O **limite de alerta de 20 combinações** se aplica a **qualquer banco** que precise expandir a query em múltiplas requisições. Acima deste limite, a busca **continua normalmente**, mas um warning é emitido informando que a busca poderá demorar. Isso inclui:

- **bioRxiv/medRxiv**: Não suportam operadores booleanos complexos
- **IEEE**: Campos compostos podem requerer múltiplas requisições
- **Qualquer outro banco** com limitações similares

```python
QUERY_COMBINATIONS_WARNING_THRESHOLD = 20

def expand_query_for_db(query: Query, db_name: str) -> List[Query]:
    """
    Expande queries complexas em múltiplas queries simples
    para bancos com suporte limitado a booleanos ou campos compostos.
    
    TODAS as combinações serão executadas, mas um warning é emitido
    se exceder o threshold para alertar sobre tempo de execução.
    """
    # Converte (A OR B) AND (C OR D)
    # Em: [A AND C, A AND D, B AND C, B AND D]
    
    combinations = generate_all_combinations(query)
    
    if len(combinations) > QUERY_COMBINATIONS_WARNING_THRESHOLD:
        logger.warning(
            f"A query gerou {len(combinations)} combinações para {db_name}. "
            f"A busca será executada, mas poderá demorar. "
            f"Considere simplificar a query para melhor performance."
        )
    
    return combinations  # Executa TODAS as combinações
```

**Bancos afetados**:
| Banco | Quando precisa de múltiplas requisições |
|-------|----------------------------------------|
| bioRxiv/medRxiv | Queries com AND entre grupos OR |
| IEEE | Campos compostos (ti:abs) sem querytext |
| OpenAlex | OR entre filters diferentes |
| Semantic Scholar | Combinações de query + filtros separados |

---

## Tradeoffs e Limitações

### Tradeoffs Gerais

| Decisão | Prós | Contras |
|---------|------|---------|
| Múltiplas requisições para simular OR/AND | Maior cobertura | Mais lento, mais chamadas de API |
| Ignorar campos não suportados | Query sempre executa | Resultados menos precisos |
| Erro em campos não suportados | Usuário sabe que não vai funcionar | Menos flexibilidade |
| Conversão de AND NOT para NOT | Compatibilidade com mais bancos | Semântica ligeiramente diferente |

### Limitações por Banco

#### arXiv
- Sem busca por keywords, publicação, afiliação
- Hífen deve ser substituído por espaço automaticamente (pré-processamento obrigatório)
- Delay obrigatório de 3 segundos

#### PubMed
- Sem wildcard `?`
- Duas chamadas de API necessárias
- MeSH terms diferentes de keywords do autor

#### IEEE
- API key obrigatória
- Máximo 200 resultados por página
- Campos como parâmetros separados (pode limitar combinações complexas)

#### Scopus
- API key obrigatória
- Ordem de precedência booleana diferente
- Algumas views requerem entitlements especiais

#### bioRxiv / medRxiv
- **Mais limitados de todos**
- Sem NOT, sem wildcards
- Apenas 1 nível de parênteses
- Apenas OR entre grupos
- Sem mistura de AND/OR no mesmo nível
- Sem campos específicos além de título+abstract
- Requer web scraping
- Pode necessitar de muitas requisições para queries complexas

### Recomendações

1. **Para queries simples**: Todos os bancos funcionam bem
2. **Para queries com NOT**: Evitar bioRxiv/medRxiv ou aceitar resultados incompletos
3. **Para busca por campos**: Usar arXiv, PubMed, IEEE ou Scopus
4. **Para melhor precisão**: Scopus (mais campos) ou PubMed (MeSH terms)
5. **Para preprints**: bioRxiv/medRxiv com queries simples
6. **Para CS/Engineering**: IEEE + arXiv
7. **Para Medicina/Biomédica**: PubMed + Scopus + medRxiv

---

## Próximos Passos

1. [ ] Estender o modelo `QueryNode` para suportar campos
2. [ ] Atualizar o parser de query para reconhecer sintaxe de campos
3. [ ] Implementar método `validate_query()` em cada searcher para validação prévia
4. [ ] Implementar método `convert_query()` em cada searcher
5. [ ] Implementar expansão de query com warning para combinações > 20
6. [ ] Adicionar lógica de skip para features não suportadas (sem fallback)
7. [ ] Implementar pré-processamento de termos (ex: hífen -> espaço no arXiv)
8. [ ] Desabilitar stemming por padrão nos bancos que suportam (OpenAlex)
9. [ ] Criar testes unitários para conversão de query
10. [ ] Documentar limitações na documentação do usuário
11. [ ] Adicionar logs informativos quando bancos são skipados

---

## Estratégia de Testes

### Testes Unitários (Offline)

Os testes unitários utilizarão os dados já coletados na pasta `tests/data/`, que contém respostas reais das APIs de cada base. Isso permite:

- Testar a lógica de conversão de queries sem fazer requisições
- Testar o parsing de respostas das APIs
- Testar a lógica de validação de queries por banco
- Rodar testes rapidamente em CI sem depender de APIs externas

```python
# Exemplo: teste usando dados coletados
def test_arxiv_query_conversion():
    query = Query("[machine learning] AND [neural networks]")
    searcher = ArxivSearcher(query)
    converted = searcher.convert_query()
    assert converted == 'all:"machine learning" AND all:"neural networks"'

def test_arxiv_response_parsing():
    with open("tests/data/arxiv/sample_response.xml") as f:
        response = f.read()
    papers = ArxivSearcher.parse_response(response)
    assert len(papers) > 0
```

---

## Referências

- [arXiv API User Manual](https://info.arxiv.org/help/api/user-manual.html)
- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [IEEE Xplore API](https://developer.ieee.org/docs/read/Metadata_API_details)
- [Scopus Search Tips](https://dev.elsevier.com/sc_search_tips.html)
- [bioRxiv/medRxiv Search Tips](https://www.medrxiv.org/content/search-tips)
- [bioRxiv API](https://api.biorxiv.org/)
