#!/usr/bin/env python3
"""Per-file metrics for the repo map: line counts, structure signals, score.

Split out from repo_map.py so neither module outgrows the 500-line convention
this tool exists to police.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath


# Line-comment prefixes per file extension. Extensions absent from this map get
# no comment detection at all - every non-blank line counts as code.
LINE_COMMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    ".py": ("#",),
    ".sh": ("#",),
    ".yml": ("#",),
    ".yaml": ("#",),
    ".conf": ("#",),
    ".ps1": ("#",),
    ".toml": ("#",),
    ".ts": ("//",),
    ".tsx": ("//",),
    ".js": ("//",),
    ".jsx": ("//",),
    ".css": ("//",),
    ".rs": ("//",),
    ".sql": ("--",),
}

# Extensions using C-style /* ... */ block comments.
BLOCK_COMMENT_EXTS = frozenset({".ts", ".tsx", ".js", ".jsx", ".css", ".rs"})


@dataclass(frozen=True)
class LineCounts:
    total: int
    blank: int
    comment: int
    code: int


def count_lines(text: str, ext: str) -> LineCounts:
    """Split text into blank, comment-only and code lines.

    A line counts as a comment only when the comment marker starts the line;
    trailing comments stay code, because the line still carries logic.
    """
    if not text:
        return LineCounts(total=0, blank=0, comment=0, code=0)

    prefixes = LINE_COMMENT_PREFIXES.get(ext, ())
    has_blocks = ext in BLOCK_COMMENT_EXTS
    lines = text.splitlines()

    blank = comment = code = 0
    in_block = False
    for raw in lines:
        stripped = raw.strip()
        if in_block:
            comment += 1
            if "*/" in stripped:
                in_block = False
                # Code trailing the block close makes the line count as code.
                if stripped.split("*/", 1)[1].strip():
                    comment -= 1
                    code += 1
            continue
        if not stripped:
            blank += 1
        elif has_blocks and stripped.startswith("/*"):
            if "*/" in stripped:
                if stripped.split("*/", 1)[1].strip():
                    code += 1
                else:
                    comment += 1
            else:
                comment += 1
                in_block = True
        elif prefixes and stripped.startswith(prefixes):
            comment += 1
        else:
            code += 1

    return LineCounts(total=len(lines), blank=blank, comment=comment, code=code)


# AST nodes that open an indented block. Nesting these is what makes a function
# hard to follow, so they define the depth metric.
_BLOCK_NODES: tuple[type[ast.AST], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.ExceptHandler,
    ast.Match,
    ast.match_case,
)

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class PythonMetrics:
    classes: int
    functions: int
    longest_fn: str | None
    longest_fn_loc: int
    max_depth: int


def analyze_python(text: str) -> PythonMetrics | None:
    """Extract structure metrics from Python source, or None if it won't parse.

    Functions include methods and nested definitions - a 900-line module built
    from many small helpers reads very differently from one built from three
    monsters, and only the per-function span tells them apart.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None

    classes = functions = 0
    longest_fn: str | None = None
    longest_fn_loc = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, _FUNCTION_NODES):
            functions += 1
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            if span > longest_fn_loc:
                longest_fn_loc = span
                longest_fn = node.name

    return PythonMetrics(
        classes=classes,
        functions=functions,
        longest_fn=longest_fn,
        longest_fn_loc=longest_fn_loc,
        max_depth=_max_block_depth(tree, 0),
    )


def _max_block_depth(node: ast.AST, depth: int) -> int:
    """Deepest chain of nested block statements below node. Module level is 0."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        child_depth = depth + 1 if isinstance(child, _BLOCK_NODES) else depth
        deepest = max(deepest, _max_block_depth(child, child_depth))
    return deepest


# A top-level declaration that may open a block: `function x`, `const X = () => {`,
# `class X {`, each optionally exported. Anchored at column 0 on purpose - indented
# matches are members, not the outer block we want to measure.
_TS_DECL_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|const|let|var|class)\s+(\w+)"
)
_TS_HOOK_RE = re.compile(r"\buse[A-Z]\w*\s*\(")


@dataclass(frozen=True)
class TypescriptMetrics:
    exports: int
    hooks: int
    longest_block: str | None
    longest_block_loc: int


def analyze_typescript(text: str) -> TypescriptMetrics:
    """Estimate structure metrics for TS/TSX by counting braces.

    This is deliberately not a parser. Braces inside string literals, template
    literals, regexes or comments are counted like real ones, so block spans are
    an estimate - the report labels them as such. It is accurate enough to rank
    a 1400-line page component against a 90-line hook, which is all it is for.
    """
    exports = hooks = 0
    longest_block: str | None = None
    longest_block_loc = 0

    depth = 0
    open_line = 0
    open_name: str | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("export "):
            exports += 1
        hooks += len(_TS_HOOK_RE.findall(raw))

        delta = raw.count("{") - raw.count("}")
        if depth == 0 and delta > 0:
            match = _TS_DECL_RE.match(raw)
            if match:
                open_name = match.group(1)
                open_line = lineno
            else:
                open_name = None
        depth += delta
        if depth <= 0:
            if open_name is not None:
                span = lineno - open_line + 1
                if span > longest_block_loc:
                    longest_block_loc = span
                    longest_block = open_name
                open_name = None
            depth = 0

    return TypescriptMetrics(
        exports=exports,
        hooks=hooks,
        longest_block=longest_block,
        longest_block_loc=longest_block_loc,
    )


# Machine-written files. They are still mapped and still counted in the LOC
# totals, but their score is damped so migrations and locale bundles cannot
# crowd the split-candidate list. Kept visible here rather than hidden inside
# the scoring maths - see --include-generated to switch the damping off.
GENERATED_PATTERNS: tuple[str, ...] = (
    "backend/alembic/versions/*",
    "client/src/i18n/locales/*",
    "*package-lock.json",
    "*.lock",
    "*.min.js",
    "*.min.css",
)
GENERATED_DAMPING = 0.1

# Weights: how many score points each signal contributes at most.
SIZE_WEIGHT = 50
FUNCTION_WEIGHT = 30
DEPTH_WEIGHT = 20
DEPTH_POINTS_PER_LEVEL = 10


@dataclass(frozen=True)
class Thresholds:
    max_loc: int = 500
    max_fn_loc: int = 80
    max_depth: int = 5


@dataclass(frozen=True)
class ScoreResult:
    score: int
    reasons: tuple[str, ...]


def is_generated(path: str) -> bool:
    """True when a repo-relative path matches a known machine-written pattern."""
    return any(fnmatch(path, pattern) for pattern in GENERATED_PATTERNS)


def compute_score(
    *,
    loc: int,
    longest_fn_loc: int,
    max_depth: int,
    generated: bool,
    thresholds: Thresholds,
) -> ScoreResult:
    """Rank a file's need for a split on a 0-100 scale, with its reasons.

    Each signal only contributes once it passes its threshold, and every
    contribution is spelled out in reasons - a bare number would be a verdict
    nobody can check.
    """
    points = 0
    reasons: list[str] = []

    size = _overshoot_points(loc, thresholds.max_loc, SIZE_WEIGHT)
    if size:
        points += size
        reasons.append(f"{loc} LOC (limit {thresholds.max_loc})")

    fn = _overshoot_points(longest_fn_loc, thresholds.max_fn_loc, FUNCTION_WEIGHT)
    if fn:
        points += fn
        reasons.append(
            f"longest function {longest_fn_loc} LOC (limit {thresholds.max_fn_loc})"
        )

    if max_depth > thresholds.max_depth:
        levels = max_depth - thresholds.max_depth
        points += min(DEPTH_WEIGHT, levels * DEPTH_POINTS_PER_LEVEL)
        reasons.append(f"nesting depth {max_depth} (limit {thresholds.max_depth})")

    score = min(100, points)
    if generated and score:
        score = round(score * GENERATED_DAMPING)
        reasons.append("generated - score damped")

    return ScoreResult(score=score, reasons=tuple(reasons))


def _overshoot_points(value: int, limit: int, weight: int) -> int:
    """Award the full weight at twice the limit, nothing at or below it."""
    if limit <= 0 or value <= limit:
        return 0
    return min(weight, round(weight * (value / limit - 1)))


TYPESCRIPT_EXTS = frozenset({".ts", ".tsx", ".js", ".jsx"})


@dataclass(frozen=True)
class FileEntry:
    """One tracked file with its line counts, structure metrics and score."""

    path: str
    ext: str
    kind: str
    loc: int
    blank: int
    comment: int
    code: int
    symbols: int
    classes: int
    functions: int
    hooks: int
    longest_name: str | None
    longest_loc: int
    max_depth: int
    estimated: bool
    generated: bool
    score: int
    reasons: tuple[str, ...]


def analyze_file(
    path: str,
    text: str,
    *,
    thresholds: Thresholds,
    include_generated: bool = False,
) -> FileEntry:
    """Build the full record for one repo-relative path and its content.

    Python that fails to parse degrades to kind "other" rather than raising:
    a file we cannot read structurally still belongs on the LOC map.
    """
    path = path.replace("\\", "/")
    ext = PurePosixPath(path).suffix
    lines = count_lines(text, ext)
    generated = is_generated(path)

    kind = "other"
    symbols = classes = functions = hooks = 0
    longest_name: str | None = None
    longest_loc = max_depth = 0
    estimated = False

    if ext == ".py":
        py = analyze_python(text)
        if py is not None:
            kind = "python"
            classes, functions = py.classes, py.functions
            symbols = py.classes + py.functions
            longest_name, longest_loc = py.longest_fn, py.longest_fn_loc
            max_depth = py.max_depth
    elif ext in TYPESCRIPT_EXTS:
        ts = analyze_typescript(text)
        kind = "typescript"
        estimated = True
        symbols = ts.exports
        hooks = ts.hooks
        longest_name, longest_loc = ts.longest_block, ts.longest_block_loc

    result = compute_score(
        loc=lines.total,
        longest_fn_loc=longest_loc,
        max_depth=max_depth,
        generated=generated and not include_generated,
        thresholds=thresholds,
    )

    return FileEntry(
        path=path,
        ext=ext,
        kind=kind,
        loc=lines.total,
        blank=lines.blank,
        comment=lines.comment,
        code=lines.code,
        symbols=symbols,
        classes=classes,
        functions=functions,
        hooks=hooks,
        longest_name=longest_name,
        longest_loc=longest_loc,
        max_depth=max_depth,
        estimated=estimated,
        generated=generated,
        score=result.score,
        reasons=result.reasons,
    )

