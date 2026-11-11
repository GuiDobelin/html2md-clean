# Contributing

Bug reports, ideas and pull requests are welcome.

1. For anything bigger than a small fix, open an issue first so we can agree on the approach.
2. Set up the dev environment:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```
3. Add tests for your change. Tests must run offline.
4. Make sure `pytest`, `ruff check .` and `ruff format --check .` pass.
5. Open a pull request describing what changed and why.
