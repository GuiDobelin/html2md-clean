"""Keep the README examples in sync with what the CLI really prints."""

import re
import shlex
from pathlib import Path

import pytest

from html2md_clean import cli

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
EXAMPLES = [
    (command, output)
    for _, command, output in re.findall(
        r"^(`{3,})text\n\$ (html2md-clean examples/[^\n]*)\n(.*?)^\1$", README, re.S | re.M
    )
]


def test_readme_has_examples():
    assert len(EXAMPLES) == 2


@pytest.mark.parametrize(("command", "expected"), EXAMPLES)
def test_readme_example_output(command, expected, capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    argv, _, head = command.partition(" | head -")
    assert cli.main(shlex.split(argv)[1:]) == 0
    out = capsys.readouterr().out
    if head:
        out = "".join(out.splitlines(keepends=True)[: int(head)])
    assert out == expected
