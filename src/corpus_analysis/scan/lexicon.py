"""User-supplied word lists. The shipped default is empty, and that is the point.

A lexicon written while looking at the corpus it will be run against is tuned to
that corpus by construction: the phrases that come to mind are the ones already
on the screen, so the resulting series partly measures its author. Behavioural
signals are the defaults for that reason (see `signals.py`), and anything
lexical is configuration a user supplies knowingly.

    {"correction": ["\\bwrong\\b", "\\bredo\\b"],
     "concession": ["\\bmy mistake\\b"]}

Load with `--lexicon path.json`. Every match is reported under the name the user
gave it; this module ships no names of its own.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: No word lists ship with this tool.
DEFAULT: dict[str, list[str]] = {}


def load(path: Path | str | None) -> dict[str, re.Pattern]:
    """Compile a lexicon file. `None` yields the empty default."""
    if path is None:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected an object of name -> patterns")

    out: dict[str, re.Pattern] = {}
    for group, patterns in raw.items():
        if not isinstance(patterns, list) or not patterns:
            raise ValueError(f"{path}: {group!r} must be a non-empty list")
        try:
            out[str(group)] = re.compile("|".join(patterns), re.I)
        except re.error as e:
            raise ValueError(f"{path}: {group!r} is not a valid pattern: {e}") from e
    return out


def match(lexicons: dict[str, re.Pattern], text: str) -> dict[str, bool]:
    """Which groups this text matches. Empty when no lexicon is configured."""
    if not text:
        return {}
    return {name: bool(pat.search(text)) for name, pat in lexicons.items()}
