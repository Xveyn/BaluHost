"""Deploy smoke-check: do the installed systemd units match their templates? (#689)

Run as ``python -m app.services.unit_drift [--install-dir /opt/baluhost]``.
ALWAYS exits 0 and prints ``PASS: …`` / ``WARN: …`` lines for the deploy log,
like ``app.plugins.verify_index_signature``.

Why this exists: ``ci-deploy.sh`` never renders unit files — only
``deploy/install/modules/10-systemd-services.sh`` does, on a manual installer
run. A template change therefore lands in the repo and under
``/opt/baluhost/deploy/`` and stops there. ``--proxy-headers`` sat in the
template for months while the running backend never had it, and the test for
it read only the template text, so it stayed green the whole time.

This check reads the box's actual state instead:
  1. the unit file systemd loaded (``FragmentPath``) vs. the rendered template,
  2. the *effective* ``ExecStart`` from ``systemctl show`` vs. the template's —
     that also catches a drop-in overriding a correct unit file,
  3. any drop-ins at all, and ``NeedDaemonReload=yes``.

Only the units module 10 manages are checked. ``baluhost-backend-local`` is
left out until its template is fixed and an installer path exists (#717).
"""
from __future__ import annotations

import argparse
import difflib
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

MANAGED_UNITS = (
    "baluhost-backend",
    "baluhost-scheduler",
    "baluhost-webdav",
    "baluhost-monitoring",
)

_SHOW_PROPERTIES = ("LoadState", "FragmentPath", "DropInPaths", "NeedDaemonReload",
                    "User", "ExecStart")
_ARGV_RE = re.compile(r"argv\[\]=(.*?) ; ignore_errors=")
_MAX_DIFF_LINES = 40


def render_template(text: str, values: dict[str, str]) -> str:
    """Same substitution as ``process_template`` in ``deploy/install/lib/common.sh``."""
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", value)
    return text


def parse_exec_start(unit_text: str) -> list[str]:
    """argv of the (last) ``ExecStart=`` line, with ``\\`` continuations joined."""
    joined = re.sub(r"\\\n", " ", unit_text)
    argv: list[str] = []
    for line in joined.splitlines():
        line = line.strip()
        if line.startswith("ExecStart="):
            argv = shlex.split(line[len("ExecStart="):])
    return argv


def parse_show_argv(value: str) -> list[list[str]]:
    """Every command's argv from a ``systemctl show -p ExecStart`` value."""
    return [shlex.split(m) for m in _ARGV_RE.findall(value)]


def _normalize(text: str) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _check_unit(unit: str, expected: str, show: dict[str, str],
                read_file: Callable[[str], str]) -> tuple[list[str], bool]:
    """Return ``(warn lines, needs_rerender)`` for one unit."""
    if show.get("LoadState") != "loaded" or not show.get("FragmentPath"):
        return [f"WARN: {unit}: not installed (LoadState={show.get('LoadState', '?')})"], True

    warns: list[str] = []
    rerender = False

    installed = read_file(show["FragmentPath"])
    if _normalize(installed) != _normalize(expected):
        rerender = True
        warns.append(f"WARN: {unit}: {show['FragmentPath']} differs from template")
        diff = list(difflib.unified_diff(
            _normalize(expected), _normalize(installed),
            fromfile="template (rendered)", tofile="installed", lineterm="", n=1))
        for line in diff[:_MAX_DIFF_LINES]:
            warns.append(f"    {line}")
        if len(diff) > _MAX_DIFF_LINES:
            warns.append(f"    … {len(diff) - _MAX_DIFF_LINES} more diff lines")

    want = parse_exec_start(expected)
    running = parse_show_argv(show.get("ExecStart", ""))
    if running != [want]:
        warns.append(f"WARN: {unit}: effective ExecStart differs from template")
        warns.append(f"    template: {shlex.join(want)}")
        for argv in running or [[]]:
            warns.append(f"    systemd:  {shlex.join(argv) or '(none)'}")

    dropins = show.get("DropInPaths", "").split()
    if dropins:
        warns.append(f"WARN: {unit}: drop-in(s) override the template: {' '.join(dropins)}"
                     " — remove once the template carries the change")

    if show.get("NeedDaemonReload") == "yes":
        rerender = True
        warns.append(f"WARN: {unit}: unit file changed on disk, systemd needs daemon-reload")

    return warns, rerender


def check_units(
    install_dir: str,
    read_template: Callable[[str], str],
    read_file: Callable[[str], str],
    systemctl_show: Callable[[str], dict[str, str]],
) -> list[str]:
    """Return PASS/WARN lines. Never raises for per-unit failures."""
    lines: list[str] = []
    rerender = False

    try:
        # The template's User= can't be checked against itself: take the
        # service user from the running backend, as install-amd-gpu-permissions.sh
        # does, instead of guessing a default that is wrong on this very box.
        user = systemctl_show(MANAGED_UNITS[0]).get("User", "")
    except Exception as exc:  # noqa: BLE001 - smoke-check must not crash
        return [f"WARN: unit drift check could not query systemd: {exc}"]
    if not user:
        return ["WARN: unit drift check: service user unknown "
                f"(no User= on {MANAGED_UNITS[0]}) — cannot render templates"]

    values = {
        "BALUHOST_USER": user,
        "INSTALL_DIR": install_dir,
        "VENV_BIN": f"{install_dir}/backend/.venv/bin",
    }

    for unit in MANAGED_UNITS:
        try:
            expected = render_template(read_template(unit), values)
            warns, needs = _check_unit(unit, expected, systemctl_show(unit), read_file)
        except Exception as exc:  # noqa: BLE001 - one unit must not hide the others
            warns, needs = [f"WARN: {unit}: check failed: {exc}"], False
        lines.extend(warns)
        rerender = rerender or needs

    if not lines:
        return [f"PASS: {len(MANAGED_UNITS)} systemd units match their templates"]
    if rerender:
        lines.append("WARN: fix: sudo bash "
                     f"{install_dir}/deploy/install/install.sh --module 10-systemd-services"
                     " — then restart the affected units")
    return lines


def _systemctl_show(unit: str) -> dict[str, str]:
    args = ["systemctl", "show", f"{unit}.service"]
    for prop in _SHOW_PROPERTIES:
        args += ["-p", prop]
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    props: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        props[key] = value
    return props


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Wrap the whole body: this entrypoint must NEVER fail a deploy on its own.
    try:
        parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
        parser.add_argument("--install-dir", default="/opt/baluhost")
        args = parser.parse_args(argv)
        template_dir = Path(args.install_dir) / "deploy" / "install" / "templates"

        for line in check_units(
            install_dir=args.install_dir,
            read_template=lambda unit: (template_dir / f"{unit}.service").read_text(encoding="utf-8"),
            read_file=lambda path: Path(path).read_text(encoding="utf-8"),
            systemctl_show=_systemctl_show,
        ):
            print(line)
    except Exception as exc:  # noqa: BLE001 - never fail a deploy from here
        print(f"WARN: unit drift check could not run: {exc}")
    return 0  # always non-fatal


if __name__ == "__main__":
    sys.exit(main())
