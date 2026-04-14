"""``baluhost-sdk`` command-line entry point.

Exposes two commands used by plugin authors before publishing to the
marketplace:

- ``baluhost-sdk validate <plugin_dir>`` — static checks against plugin.json.
- ``baluhost-sdk dry-install <plugin_dir>`` — validate + run the full resolver
  against the Core's locked environment snapshot.

Exit codes:
- ``0`` on success
- ``1`` on validation or resolver failure
- ``2`` on usage / I/O errors (handled by click)
"""
from __future__ import annotations

from pathlib import Path

import click

from app.plugins.core_versions import CoreVersionsError, load_core_versions
from app.plugins.sdk.dry_install import DryInstallReport, dry_install
from app.plugins.sdk.validator import ValidationReport, validate_plugin


@click.group()
def cli() -> None:
    """Developer tooling for BaluHost plugin authors."""


def _print_validation(report: ValidationReport) -> None:
    if report.manifest is not None:
        click.echo(
            f"Plugin: {report.manifest.name} {report.manifest.version} "
            f"({report.manifest.display_name})"
        )
    else:
        click.echo(f"Plugin: <unparsed> at {report.plugin_dir}")

    if not report.issues:
        click.secho("  No issues found.", fg="green")
        return

    for issue in report.errors:
        click.secho(f"  [error:{issue.code}] {issue.message}", fg="red")
    for issue in report.warnings:
        click.secho(f"  [warning:{issue.code}] {issue.message}", fg="yellow")


@cli.command()
@click.argument(
    "plugin_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def validate(plugin_dir: Path) -> None:
    """Run static checks on a plugin source directory."""
    report = validate_plugin(plugin_dir)
    _print_validation(report)

    if not report.ok:
        click.secho("validate: FAILED", fg="red")
        raise SystemExit(1)
    if report.warnings:
        click.secho("validate: ok (with warnings)", fg="yellow")
    else:
        click.secho("validate: ok", fg="green")


def _print_dry_install(report: DryInstallReport) -> None:
    _print_validation(report.validation)

    if report.resolution is None:
        return

    click.echo("")
    if report.core_versions is not None:
        click.echo(
            f"Core: BaluHost {report.core_versions.baluhost_version} "
            f"(python {report.core_versions.python_version}, "
            f"{len(report.core_versions.packages)} packages)"
        )

    res = report.resolution
    if res.shared_satisfied:
        click.echo("  Shared (satisfied by Core):")
        for raw in res.shared_satisfied:
            click.echo(f"    - {raw}")
    if res.isolated_to_install:
        click.echo("  Isolated (would install into plugin's site-packages):")
        for raw in res.isolated_to_install:
            click.echo(f"    - {raw}")

    if res.conflicts:
        click.secho("  Conflicts:", fg="red")
        for c in res.conflicts:
            click.secho(
                f"    - {c.package} ({c.source}): need {c.requirement}, found {c.found}",
                fg="red",
            )
            click.echo(f"      → {c.suggestion}")


@cli.command("dry-install")
@click.argument(
    "plugin_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--core-versions",
    "core_versions_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to an alternate core_versions.json (defaults to the installed Core's copy).",
)
def dry_install_cmd(plugin_dir: Path, core_versions_path: Path | None) -> None:
    """Validate a plugin and simulate installation against the Core."""
    cv = None
    if core_versions_path is not None:
        try:
            cv = load_core_versions(core_versions_path)
        except CoreVersionsError as exc:
            click.secho(f"dry-install: failed to load core_versions: {exc}", fg="red")
            raise SystemExit(1)

    try:
        report = dry_install(plugin_dir, core_versions=cv)
    except CoreVersionsError as exc:
        click.secho(f"dry-install: failed to load core_versions: {exc}", fg="red")
        raise SystemExit(1)

    _print_dry_install(report)

    if not report.ok:
        click.secho("dry-install: FAILED", fg="red")
        raise SystemExit(1)
    if report.validation.warnings:
        click.secho("dry-install: ok (with warnings)", fg="yellow")
    else:
        click.secho("dry-install: ok", fg="green")


if __name__ == "__main__":  # pragma: no cover
    cli()
