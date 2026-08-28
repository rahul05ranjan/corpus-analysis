"""Every figure a report prints carries its epistemic status.

Three labels, and nothing else:

    counted   arithmetic over records; entailed by the corpus
    derived   counted values combined under a stated rule; the rule is cited
    proxy     stands in for something not recorded; the assumption is named

A report is built from `Figure` objects, so a number cannot reach the page
without one. `lint()` re-checks the rendered text, which is what the test
asserts on: the artifact, not the builder that produced it.

The rule this enforces came from reports whose most quotable numbers did not
survive review, because their assumptions were never written down next to them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COUNTED = "counted"
DERIVED = "derived"
PROXY = "proxy"
LABELS = (COUNTED, DERIVED, PROXY)

#: Digits a prose line may carry without a label: dates, section references,
#: heading and list numbering. Everything else is a figure and needs one.
_ALLOWED = (
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"§\d+(?:\.\d+)*"),
    re.compile(r"^\s*#{1,6}\s+\d+(?:\.\d+)*\."),
    re.compile(r"^\s*\d+\.\s"),
    re.compile(r"^\s*-\s\d+\.\s"),
)

_MARKER = re.compile(r"\[(counted|derived|proxy)(?::[^\]]*)?\]")
_SEPARATOR = re.compile(r"^\|[\s\-:|]+\|$")


class UnlabeledFigure(ValueError):
    """A number reached the page without an epistemic status."""


@dataclass(frozen=True, slots=True)
class Figure:
    """One number and what licenses it."""

    name: str
    value: object
    label: str
    basis: str = ""

    def __post_init__(self) -> None:
        if self.label not in LABELS:
            raise UnlabeledFigure(
                f"{self.name}: label must be one of {LABELS}, not {self.label!r}"
            )
        if self.label in (DERIVED, PROXY) and not self.basis.strip():
            raise UnlabeledFigure(
                f"{self.name}: a {self.label} figure must name its "
                f"{'rule' if self.label == DERIVED else 'assumption'}"
            )

    def marker(self) -> str:
        return f"[{self.label}]" if not self.basis else f"[{self.label}: {self.basis}]"

    def render(self) -> str:
        """`name value [label]` — the standalone form, for a prose line."""
        return f"{self.name} {self.value} {self.marker()}"


@dataclass(frozen=True, slots=True)
class Column:
    """A table column. Its label covers every cell beneath it."""

    name: str
    label: str
    basis: str = ""

    def __post_init__(self) -> None:
        Figure(self.name, 0, self.label, self.basis)  # same validation

    def header(self) -> str:
        m = f"[{self.label}]" if not self.basis else f"[{self.label}: {self.basis}]"
        return f"{self.name} {m}"


class Report:
    """A markdown report that cannot print an unlabeled number."""

    def __init__(self, title: str) -> None:
        self._lines: list[str] = [f"# {title}", ""]

    def prose(self, text: str) -> Report:
        for line in text.splitlines() or [""]:
            if _bare_digits(line):
                raise UnlabeledFigure(
                    f"prose carries an unlabeled number: {line.strip()!r}. "
                    "Numbers reach a report as Figures."
                )
            self._lines.append(line)
        self._lines.append("")
        return self

    def heading(self, text: str) -> Report:
        self._lines.append(f"## {text}")
        self._lines.append("")
        return self

    def figures(self, *figures: Figure) -> Report:
        for f in figures:
            self._lines.append(f"- {f.render()}")
        self._lines.append("")
        return self

    def table(self, columns: list[Column], rows: list[list[object]]) -> Report:
        if not columns:
            raise ValueError("a table needs at least one column")
        self._lines.append(
            "| " + " | ".join(_table_cell(c.header()) for c in columns) + " |"
        )
        self._lines.append("|" + "---|" * len(columns))
        for row in rows:
            if len(row) != len(columns):
                raise ValueError(
                    f"row has {len(row)} cells for {len(columns)} columns"
                )
            self._lines.append(
                "| " + " | ".join(_table_cell(c) for c in row) + " |"
            )
        self._lines.append("")
        return self

    def render(self) -> str:
        text = "\n".join(self._lines).rstrip() + "\n"
        lint(text)  # the builder's own output must pass the gate it enforces
        return text


def _bare_digits(line: str) -> bool:
    """True when `line` carries a digit that no label covers."""
    if _MARKER.search(line):
        return False
    stripped = line
    for pat in _ALLOWED:
        stripped = pat.sub("", stripped)
    return any(ch.isdigit() for ch in stripped)


def _table_cell(value: object) -> str:
    """One physical Markdown cell, even when source text contains delimiters."""
    return (str(value).replace("&", "&amp;").replace("|", "&#124;")
            .replace("\r", " ").replace("\n", " "))


def _table_cells(line: str) -> list[str]:
    """Split a Markdown row on pipes that are not backslash-escaped."""
    cells: list[str] = []
    start = 1 if line.startswith("|") else 0
    slash_run = 0
    for i in range(start, len(line)):
        ch = line[i]
        if ch == "\\":
            slash_run += 1
            continue
        if ch == "|" and slash_run % 2 == 0:
            cells.append(line[start:i].strip())
            start = i + 1
        slash_run = 0
    tail = line[start:].strip()
    if tail:
        cells.append(tail)
    return cells


def lint(text: str) -> None:
    """Raise on the first line carrying an unlabeled number.

    Table cells are covered by their column header, so a header whose columns
    all carry markers licenses every row beneath it. A table that loses its
    header loses its rows with it.
    """
    in_table = False
    table_ok = False
    table_columns = 0
    for n, line in enumerate(text.splitlines(), start=1):
        if line.startswith("|"):
            if _SEPARATOR.match(line):
                continue
            if not in_table:
                in_table = True
                cells = _table_cells(line)
                table_columns = len(cells)
                table_ok = all(_MARKER.search(c) for c in cells if c)
                if not table_ok:
                    raise UnlabeledFigure(
                        f"line {n}: table header has a column with no label: "
                        f"{line.strip()!r}"
                    )
            elif not table_ok:
                raise UnlabeledFigure(f"line {n}: table row under an unlabeled header")
            elif len(_table_cells(line)) != table_columns:
                raise UnlabeledFigure(
                    f"line {n}: table row has {len(_table_cells(line))} cells; "
                    f"header has {table_columns}"
                )
            continue
        in_table = False
        if _bare_digits(line):
            raise UnlabeledFigure(f"line {n}: unlabeled number in {line.strip()!r}")
