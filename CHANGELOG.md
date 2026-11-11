# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-11

### Added

- `convert()` / `html_to_markdown()`: HTML to CommonMark with GitHub tables, choosing the main
  content (`<main>`, top-level `<article>`s, or the page) and dropping page chrome.
- `decode_html()`: picks the encoding from the BOM, the HTTP charset or `<meta charset>`.
- `fetch()`: downloads http(s) pages with a size limit, content-type check and http(s)-only
  redirects.
- `html2md-clean` CLI for files, standard input and URLs, with `--full`, `--no-links`,
  `--no-images`, `--title`, `--front-matter`, `--base-url`, `--timeout` and `-o`.
