# Download

The `engine.download()` method downloads PDFs for a list of papers. It tries all known URLs for each paper and follows HTML landing pages to resolve the actual PDF link.

## Basic Usage

```python
import findpapers

engine = findpapers.Engine()

result = engine.search("[deep learning] AND [medical imaging]")

# Download PDFs
metrics = engine.download(result.papers, "./pdfs")

print(f"Downloaded {metrics['downloaded_papers']} of {metrics['total_papers']} papers")
```

## Parameters

```python
metrics = engine.download(
    papers,                         # list[Paper] - papers to download
    output_directory,               # str - directory to save PDFs
    num_workers=1,                  # int - number of parallel workers
    timeout=30.0,                   # float | None - per-download timeout in seconds
    verbose=False,                  # bool - enable detailed logging
    show_progress=True,             # bool - show progress bars
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `papers` | `list[Paper]` | *(required)* | Papers whose PDFs should be downloaded - typically obtained from `engine.search(...).papers` |
| `output_directory` | `str` | *(required)* | Directory where PDF files and the download log will be written. Created automatically if it does not exist |
| `num_workers` | `int` | `1` | Number of parallel download workers |
| `timeout` | `float \| None` | `30.0` | Per-request HTTP timeout in seconds. `None` disables the timeout |
| `verbose` | `bool` | `False` | Enable detailed DEBUG-level log messages |
| `show_progress` | `bool` | `True` | Display a tqdm progress bar while papers are being downloaded |

## Return Value

Returns a `dict` with the following keys:

| Key | Type | Description |
|-----|------|-------------|
| `total_papers` | `int` | Number of papers attempted |
| `downloaded_papers` | `int` | Number of successfully downloaded PDFs |
| `runtime_in_seconds` | `float` | Wall-clock time of the download process |

## Output Files

Downloaded PDFs are saved to the specified `output_directory` with a `YEAR-title.pdf` naming scheme. A `download_log.txt` file is created in the output directory with the status of each download (success or failure with reason).

```
pdfs/
├── 2023-attention-is-all-you-need.pdf
├── 2023-bert-pre-training-of-deep-bidirectional.pdf
├── 2024-vision-transformer-for-medical-imaging.pdf
└── download_log.txt
```

## Parallel Execution

Speed up downloads by using multiple workers:

```python
metrics = engine.download(result.papers, "./pdfs", num_workers=8)
```

Parallel downloads can significantly reduce total time when fetching many papers.

## Timeout

The `timeout` parameter controls the HTTP timeout for each individual download request:

```python
# Increase timeout for large files or slow connections
metrics = engine.download(result.papers, "./pdfs", timeout=60.0)

# Disable timeout (not recommended)
metrics = engine.download(result.papers, "./pdfs", timeout=None)
```

## Proxy and SSL

Download requests use the proxy and SSL settings configured on the `Engine`:

```python
engine = findpapers.Engine(
    proxy="http://proxy.example.com:8080",
    ssl_verify=False,
)

metrics = engine.download(result.papers, "./pdfs")
```

See [Configuration](https://github.com/jonatasgrosman/findpapers/blob/main/docs/configuration.md) for details on proxy and SSL settings.

## Typical Workflow

Downloading usually comes after searching papers.

```python
import findpapers

engine = findpapers.Engine()

# 1. Search
result = engine.search("[machine learning] AND [healthcare]")

# 2. Download
metrics = engine.download(result.papers, "./pdfs", num_workers=8)

print(f"Downloaded {metrics['downloaded_papers']} of {metrics['total_papers']} papers")

# 3. Save results
findpapers.save_to_json(result, "results.json")
```
