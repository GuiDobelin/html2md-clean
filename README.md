# html2md-clean

**Convert web pages into clean Markdown without boilerplate, using only the standard library**

[![CI](https://github.com/GuiDobelin/html2md-clean/actions/workflows/ci.yml/badge.svg)](https://github.com/GuiDobelin/html2md-clean/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

<!-- TODO: one paragraph on the problem this solves and who it is for. -->

```text
$ html2md-clean --help
```

## Install

```bash
pip install "git+https://github.com/GuiDobelin/html2md-clean"
```

## Usage

### CLI

```bash
html2md-clean ...
```

### Python

```python
import html2md_clean
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

## Ecosystem

Part of a set of small tools around [citerag](https://github.com/GuiDobelin/citerag), a self-hostable
RAG API that answers questions about your documents with verifiable citations.

## License

[MIT](LICENSE)
