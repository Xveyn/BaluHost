"""Minimal parser for Valve's KeyValues (VDF) text format.

Supports only the subset Steam uses in ``libraryfolders.vdf`` and
``appmanifest_*.acf``: quoted keys/values and ``{}`` nested blocks. No macros,
no conditionals, no unquoted tokens. stdlib only — deliberately not the ``vdf``
PyPI package (repo rule: no new deps for small features).

``//`` line comments are NOT stripped. Steam writes these two files
programmatically and does not emit comments, so this is a non-issue in
practice; we intentionally avoid a comment pre-pass that could corrupt values
containing ``//``.
"""
from __future__ import annotations

import re

# Matches a quoted string (group 1), an opening brace (group 2), or a closing
# brace (group 3). Backslash escapes inside quotes are tolerated.
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|(\{)|(\})')


def _unescape(s: str) -> str:
    return s.replace('\\\\', '\\').replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')


def parse(text: str) -> dict:
    """Parse VDF *text* into nested dicts. Leaf values are ``str``."""
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN.finditer(text):
        if m.group(1) is not None:
            tokens.append(("str", _unescape(m.group(1))))
        elif m.group(2):
            tokens.append(("open", "{"))
        else:
            tokens.append(("close", "}"))

    root: dict = {}
    stack: list[dict] = [root]
    i, n = 0, len(tokens)
    while i < n:
        kind, val = tokens[i]
        if kind == "close":
            if len(stack) > 1:
                stack.pop()
            i += 1
            continue
        if kind == "open":
            # Anonymous block without a key — not expected in Steam files; skip.
            i += 1
            continue
        # kind == "str": this token is a key; the next token decides its value.
        key = val
        if i + 1 >= n:
            break  # dangling key, ignore
        nkind, nval = tokens[i + 1]
        if nkind == "open":
            child: dict = {}
            stack[-1][key] = child
            stack.append(child)
            i += 2
        elif nkind == "str":
            stack[-1][key] = nval
            i += 2
        else:  # "close" right after a key — malformed; store empty and let it close.
            stack[-1][key] = ""
            i += 1
    return root
