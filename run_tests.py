#!/usr/bin/env python3
"""
BaluHost Test Runner
====================
Runs all available test suites (backend, frontend unit, frontend e2e).
Configurable via CLI arguments.

Usage:
    python run_tests.py                  # Run all tests
    python run_tests.py backend          # Backend only
    python run_tests.py frontend         # Frontend unit + e2e
    python run_tests.py frontend-unit    # Frontend unit only
    python run_tests.py frontend-e2e     # Frontend e2e only
    python run_tests.py -k test_auth     # Pass pytest -k filter to backend
    python run_tests.py --no-coverage    # Skip coverage report
    python run_tests.py --parallel       # Run suites in parallel
    python run_tests.py --verbose        # Verbose output
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
CLIENT_DIR = ROOT / "client"


# ── Result model ────────────────────────────────────────────────────

@dataclass
class SuiteResult:
    name: str
    returncode: int
    duration: float
    skipped: bool = False
    skip_reason: str = ""
    output: str = ""


# ── Colours (ANSI) ──────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[32m"
    RED    = "\033[31m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    DIM    = "\033[2m"


def _status(ok: bool) -> str:
    return f"{C.GREEN}PASS{C.RESET}" if ok else f"{C.RED}FAIL{C.RESET}"


def _header(text: str) -> None:
    width = 60
    print(f"\n{C.CYAN}{C.BOLD}{'═' * width}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}  {text}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}{'═' * width}{C.RESET}\n")


# ── Suite runners ───────────────────────────────────────────────────

def run_backend(args: argparse.Namespace, capture: bool = False) -> SuiteResult:
    """Run backend pytest suite."""
    if not (BACKEND_DIR / "tests").is_dir():
        return SuiteResult("Backend (pytest)", 0, 0, skipped=True,
                           skip_reason="backend/tests/ not found")

    cmd = [sys.executable, "-m", "pytest"]

    if args.verbose:
        cmd.append("-v")

    if args.no_coverage:
        cmd.extend(["--override-ini", "addopts="])

    if args.k:
        cmd.extend(["-k", args.k])

    if args.marker:
        cmd.extend(["-m", args.marker])

    if args.x:
        cmd.append("-x")

    if args.backend_args:
        cmd.extend(args.backend_args)

    return _run_suite("Backend (pytest)", cmd, BACKEND_DIR, capture)


def run_frontend_unit(args: argparse.Namespace, capture: bool = False) -> SuiteResult:
    """Run frontend vitest unit tests."""
    pkg = CLIENT_DIR / "package.json"
    if not pkg.is_file():
        return SuiteResult("Frontend Unit (vitest)", 0, 0, skipped=True,
                           skip_reason="client/package.json not found")

    cmd = ["npm", "run", "test", "--", "--run"]

    if args.verbose:
        cmd.append("--reporter=verbose")

    if args.frontend_args:
        cmd.extend(args.frontend_args)

    return _run_suite("Frontend Unit (vitest)", cmd, CLIENT_DIR, capture)


def run_frontend_e2e(args: argparse.Namespace, capture: bool = False) -> SuiteResult:
    """Run frontend Playwright e2e tests."""
    cfg = CLIENT_DIR / "playwright.config.ts"
    if not cfg.is_file():
        return SuiteResult("Frontend E2E (playwright)", 0, 0, skipped=True,
                           skip_reason="playwright.config.ts not found")

    cmd = ["npx", "playwright", "test"]

    if args.verbose:
        cmd.append("--reporter=list")

    if args.frontend_args:
        cmd.extend(args.frontend_args)

    return _run_suite("Frontend E2E (playwright)", cmd, CLIENT_DIR, capture)


# ── Execution helper ────────────────────────────────────────────────

def _run_suite(name: str, cmd: list[str], cwd: Path, capture: bool) -> SuiteResult:
    if not capture:
        _header(name)

    start = time.monotonic()
    try:
        if capture:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=600,
            )
            output = proc.stdout + proc.stderr
        else:
            proc = subprocess.run(cmd, cwd=cwd, timeout=600)
            output = ""
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        return SuiteResult(name, 1, duration, output="TIMEOUT after 600s")
    except FileNotFoundError as exc:
        duration = time.monotonic() - start
        return SuiteResult(name, 1, duration, output=f"Command not found: {exc}")

    duration = time.monotonic() - start
    return SuiteResult(name, proc.returncode, duration, output=output)


# ── Suite selection ─────────────────────────────────────────────────

SUITES = {
    "backend":       [run_backend],
    "frontend":      [run_frontend_unit, run_frontend_e2e],
    "frontend-unit": [run_frontend_unit],
    "frontend-e2e":  [run_frontend_e2e],
}


def resolve_suites(names: list[str]):
    """Return list of runner functions for the requested suite names."""
    if not names:
        # All suites
        return [run_backend, run_frontend_unit, run_frontend_e2e]

    runners = []
    for name in names:
        name_lower = name.lower()
        if name_lower not in SUITES:
            print(f"{C.RED}Unknown suite: {name}{C.RESET}")
            print(f"Available: {', '.join(SUITES.keys())}")
            sys.exit(1)
        for fn in SUITES[name_lower]:
            if fn not in runners:
                runners.append(fn)
    return runners


# ── Summary ─────────────────────────────────────────────────────────

def print_summary(results: list[SuiteResult]) -> int:
    _header("Test Summary")

    total_duration = sum(r.duration for r in results)
    failures = 0

    for r in results:
        if r.skipped:
            status = f"{C.YELLOW}SKIP{C.RESET}"
            detail = f" ({r.skip_reason})"
        else:
            status = _status(r.returncode == 0)
            detail = ""
            if r.returncode != 0:
                failures += 1

        dur = f"{C.DIM}{r.duration:.1f}s{C.RESET}"
        print(f"  {status}  {r.name:<30} {dur}{detail}")

    print(f"\n  Total time: {total_duration:.1f}s")

    if failures:
        print(f"\n  {C.RED}{C.BOLD}{failures} suite(s) failed{C.RESET}")
        return 1
    else:
        print(f"\n  {C.GREEN}{C.BOLD}All suites passed!{C.RESET}")
        return 0


# ── CLI ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="BaluHost Test Runner — run all test suites from a single command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Suites:
  backend          Backend pytest tests (1450+ tests)
  frontend         Frontend unit + e2e tests
  frontend-unit    Frontend vitest unit tests only
  frontend-e2e     Frontend Playwright e2e tests only

Examples:
  python run_tests.py                       Run everything
  python run_tests.py backend frontend-unit Run backend + frontend unit
  python run_tests.py backend -k auth       Backend tests matching 'auth'
  python run_tests.py backend -m asyncio    Backend tests with marker 'asyncio'
  python run_tests.py --parallel            Run suites concurrently
  python run_tests.py -x                    Stop backend on first failure
  python run_tests.py --list                List available suites
""",
    )

    p.add_argument(
        "suites", nargs="*", metavar="SUITE",
        help="Test suites to run (default: all). See below for options.",
    )
    p.add_argument(
        "--parallel", "-p", action="store_true",
        help="Run selected suites in parallel (output captured, printed at end)",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose output for all test runners",
    )
    p.add_argument(
        "--no-coverage", action="store_true",
        help="Disable pytest coverage reporting for backend",
    )
    p.add_argument(
        "--list", "-l", action="store_true",
        help="List available test suites and exit",
    )

    # Backend-specific
    bg = p.add_argument_group("Backend options")
    bg.add_argument("-k", metavar="EXPR", help="pytest -k filter expression")
    bg.add_argument("-m", "--marker", metavar="MARKER", help="pytest -m marker filter")
    bg.add_argument("-x", action="store_true", help="Stop backend tests on first failure")
    bg.add_argument(
        "--backend-args", nargs=argparse.REMAINDER, metavar="ARG",
        help="Extra args passed to pytest (after --)",
    )

    # Frontend-specific
    fg = p.add_argument_group("Frontend options")
    fg.add_argument(
        "--frontend-args", nargs=argparse.REMAINDER, metavar="ARG",
        help="Extra args passed to vitest/playwright (after --)",
    )

    return p


def list_suites() -> None:
    print(f"\n{C.BOLD}Available test suites:{C.RESET}\n")
    info = {
        "backend":       ("Backend pytest", f"{BACKEND_DIR / 'tests'}"),
        "frontend-unit": ("Frontend vitest unit tests", f"{CLIENT_DIR / 'src' / '__tests__'}"),
        "frontend-e2e":  ("Frontend Playwright e2e", f"{CLIENT_DIR / 'tests' / 'e2e'}"),
        "frontend":      ("frontend-unit + frontend-e2e", ""),
    }
    for name, (desc, path) in info.items():
        loc = f"  {C.DIM}{path}{C.RESET}" if path else ""
        print(f"  {C.CYAN}{name:<16}{C.RESET} {desc}{loc}")
    print()


# ── Main ────────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        list_suites()
        return 0

    runners = resolve_suites(args.suites)

    print(f"{C.BOLD}BaluHost Test Runner{C.RESET}")
    print(f"Running {len(runners)} suite(s): "
          f"{', '.join((fn.__doc__ or fn.__name__).strip().split('.')[0] for fn in runners)}")

    if args.parallel and len(runners) > 1:
        # Parallel execution — capture output, print afterwards
        results: list[SuiteResult] = []
        with ThreadPoolExecutor(max_workers=len(runners)) as pool:
            futures = {pool.submit(fn, args, capture=True): fn for fn in runners}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                status = _status(result.returncode == 0) if not result.skipped else f"{C.YELLOW}SKIP{C.RESET}"
                print(f"  {status} {result.name} ({result.duration:.1f}s)")

        # Print captured output for failed suites
        for r in results:
            if r.returncode != 0 and r.output and not r.skipped:
                _header(f"{r.name} — Output")
                print(r.output)
    else:
        # Sequential execution — stream output directly
        results = []
        for fn in runners:
            result = fn(args, capture=False)
            results.append(result)

    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
