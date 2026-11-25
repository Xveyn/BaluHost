"""Deploy smoke-check: can anyone but root rewrite the nginx configuration? (#862)

Run as ``python -m app.services.nginx_perms [--config-dir /etc/nginx] [--strict]``.
Without ``--strict`` it ALWAYS exits 0 and prints ``PASS: …`` / ``WARN: …`` lines
for the deploy log, like ``app.services.unit_drift``. With ``--strict`` (used by
``deploy/install/verify/verify-install.sh``) a finding ends with 1.

Why this exists: the service user may ``sudo systemctl reload nginx``
(``baluhost-deploy-sudoers``), and nginx' master process runs as root. A site
file the service user can write is therefore a way to reconfigure a root
process — arbitrary proxies, paths and ``server`` blocks, live after one
reload. On BaluNode both site files were ``sven:sven 0664``. No installer
script creates that state — they all write as root — but none repaired or
reported it either: ``process_template`` and ``cp`` keep the owner and mode of
a file that already exists.

This check reads the box's actual state instead of a template: owner and mode
of every file and directory under the config directory. An entry is a finding
when it is not owned by root, or writable by a group other than root's, or
world-writable. It never asks *who* the service user is — the rule is "root
only", so there is no user name to guess (#581); a finding names the owner the
entry actually has.

Deliberately out of scope:
  * files the configuration merely *refers to* — certificates, the web root.
    Those are data; a plugin may own its certificate directory by design.
  * the parent directories of a link target outside the config directory. Such
    a link is reported once, at the link; the fix is to replace it.
"""
from __future__ import annotations

import argparse
import grp
import os
import pwd
import shlex
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

DEFAULT_CONFIG_DIR = "/etc/nginx"


@dataclass(frozen=True)
class _Finding:
    path: str  # the entry inside the config directory
    target: Optional[str]  # set when *path* is a link pointing outside of it
    wrong_owner: bool
    writable: bool
    reasons: tuple[str, ...]
    mode: int


def _user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return f"uid {uid}"


def _group_name(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return f"gid {gid}"


def _inspect(path: str, target: Optional[str], trusted_uid: int,
             trusted_gid: int) -> Optional[_Finding]:
    """Hold one entry against the rule; ``None`` when it is fine."""
    st = os.stat(target or path)
    mode = stat.S_IMODE(st.st_mode)
    reasons: list[str] = []

    wrong_owner = st.st_uid != trusted_uid
    if wrong_owner:
        reasons.append(f"owned by {_user_name(st.st_uid)}")

    writable = False
    if mode & stat.S_IWGRP and st.st_gid != trusted_gid:
        writable = True
        reasons.append(f"group-writable for {_group_name(st.st_gid)}")
    if mode & stat.S_IWOTH:
        writable = True
        reasons.append("world-writable")

    if not reasons:
        return None
    return _Finding(path=path, target=target, wrong_owner=wrong_owner,
                    writable=writable, reasons=tuple(reasons), mode=mode)


def _entries(config_dir: str) -> list[tuple[str, Optional[str]]]:
    """Every entry to check as ``(path, external link target or None)``.

    A link that stays inside the tree is skipped — its target is an entry of
    its own. A dangling link is skipped too: nginx cannot load it.
    """
    real_root = os.path.realpath(config_dir)
    entries: list[tuple[str, Optional[str]]] = [(config_dir, None)]
    for current, dirnames, filenames in os.walk(config_dir):
        for name in sorted(dirnames) + sorted(filenames):
            path = os.path.join(current, name)
            if not os.path.islink(path):
                entries.append((path, None))
                continue
            target = os.path.realpath(path)
            if not os.path.exists(target):
                continue
            if target == real_root or target.startswith(real_root + os.sep):
                continue
            entries.append((path, target))
    return entries


def check_tree(config_dir: Union[str, Path], *, trusted_uid: int = 0,
               trusted_gid: int = 0) -> list[str]:
    """Return PASS/WARN lines for the nginx configuration under *config_dir*.

    Args:
        config_dir: nginx' configuration directory.
        trusted_uid: The only owner an entry may have. Root; injectable because
            the test suite does not run as root.
        trusted_gid: The only group that may have write access.

    Returns:
        One ``PASS:`` line, or one ``WARN:`` line per finding followed by the
        command that fixes them.
    """
    config_dir = str(config_dir)
    if not os.path.isdir(config_dir):
        return [f"PASS: {config_dir} does not exist — nothing to check"]

    entries = _entries(config_dir)
    findings = [
        finding
        for path, target in entries
        if (finding := _inspect(path, target, trusted_uid, trusted_gid)) is not None
    ]
    if not findings:
        return [f"PASS: {len(entries)} entries under {config_dir} are owned by root "
                "and writable by nobody else"]

    lines: list[str] = []
    for finding in findings:
        detail = f"{', '.join(finding.reasons)} (mode {finding.mode:04o})"
        if finding.target is None:
            lines.append(f"WARN: {finding.path}: {detail}")
        else:
            # No chown/chmod for these: the target may sit in a checkout or a
            # home directory, where "make it root's" breaks something else.
            lines.append(f"WARN: {finding.path}: links to {finding.target} outside "
                         f"{config_dir}, {detail} — replace the link with a "
                         "root-owned copy")

    inside = [finding for finding in findings if finding.target is None]
    commands: list[str] = []
    chown = [shlex.quote(finding.path) for finding in inside if finding.wrong_owner]
    if chown:
        commands.append(f"sudo chown root:root {' '.join(chown)}")
    chmod = [shlex.quote(finding.path) for finding in inside if finding.writable]
    if chmod:
        commands.append(f"sudo chmod go-w {' '.join(chmod)}")
    if commands:
        lines.append(f"WARN: fix: {' && '.join(commands)}")
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--config-dir", default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on a finding (default: always 0)")
    args = parser.parse_args(argv)

    # Wrap the check itself: without --strict this entrypoint must NEVER fail
    # a deploy on its own.
    try:
        lines = check_tree(args.config_dir)
    except Exception as exc:  # noqa: BLE001 - never fail a deploy from here
        lines = [f"WARN: nginx permission check could not run: {exc}"]
    for line in lines:
        print(line)

    found = any(line.startswith("WARN: ") for line in lines)
    return 1 if args.strict and found else 0


if __name__ == "__main__":
    sys.exit(main())
