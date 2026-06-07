"""PyInstaller entry point for the standalone `baluhost-tui` binary.

PyInstaller bundles this module; it just hands off to the Click CLI. The
`baluhost_tui` package must be importable at build time (the workflow passes
`--paths .` from `backend/`).
"""
from baluhost_tui.main import cli

if __name__ == "__main__":
    cli()
