"""Deploy smoke-check: is the nginx configuration writable by anyone but root? (#862)

The check reads the box's actual state (owner and mode of every entry under
the nginx config directory), never an installer template — the installer has
always written the site as root, and on BaluNode it was `sven:sven 0664`
anyway.

Tests run unprivileged, so "root" is injected: the trusted owner is the test
user, the trusted group the test user's primary group. A foreign owner is
produced by trusting a uid nobody has.
"""
import inspect
import os
import pwd
import stat
from pathlib import Path

from app.services import nginx_perms
from app.services.nginx_perms import check_tree

ME = os.getuid()
MY_GROUP = os.getgid()
NOBODY_HAS_THIS_ID = 2**31 - 7


def _tree(tmp_path: Path) -> Path:
    """A miniature /etc/nginx, everything 0644/0755 and owned by the test user."""
    root = tmp_path / "nginx"
    (root / "sites-available").mkdir(parents=True)
    (root / "sites-enabled").mkdir()
    (root / "snippets").mkdir()
    for directory in (root, root / "sites-available", root / "sites-enabled", root / "snippets"):
        directory.chmod(0o755)
    for name in ("nginx.conf", "sites-available/baluhost", "snippets/ssl-params.conf"):
        (root / name).write_text("# conf\n", encoding="utf-8")
        (root / name).chmod(0o644)
    (root / "sites-enabled" / "baluhost").symlink_to(root / "sites-available" / "baluhost")
    return root


def _check(root: Path, uid: int = ME, gid: int = MY_GROUP) -> list[str]:
    return check_tree(root, trusted_uid=uid, trusted_gid=gid)


def _warns(lines: list[str]) -> list[str]:
    """Finding lines only — without the trailing fix/hint lines."""
    return [line for line in lines if line.startswith("WARN: /")]


# ─── Der gute Fall ───────────────────────────────────────────────────


def test_sauberer_baum_ergibt_genau_eine_pass_zeile(tmp_path):
    lines = _check(_tree(tmp_path))
    assert len(lines) == 1
    assert lines[0].startswith("PASS: ")
    assert str(tmp_path / "nginx") in lines[0]


def test_fehlendes_verzeichnis_ist_kein_befund(tmp_path):
    """Eine Box ohne nginx (Dev-Rechner, Fork ohne Reverse-Proxy) darf den
    Deploy-Log nicht mit einer Warnung fuellen, an der nichts zu tun ist."""
    lines = _check(tmp_path / "gibt-es-nicht")
    assert len(lines) == 1
    assert lines[0].startswith("PASS: ")
    assert "nothing to check" in lines[0]


# ─── Der Befund aus #862 ─────────────────────────────────────────────


def test_fremder_besitzer_wird_gemeldet(tmp_path):
    """Der Zustand auf BaluNode: die Site gehoert nicht root."""
    root = _tree(tmp_path)
    lines = _check(root, uid=NOBODY_HAS_THIS_ID)
    site = str(root / "sites-available" / "baluhost")
    hit = [line for line in _warns(lines) if line.startswith(f"WARN: {site}:")]
    assert len(hit) == 1
    assert "owned by" in hit[0]


def test_besitzer_wird_beim_namen_genannt_nicht_geraten(tmp_path):
    """Kein Skript raet, wie der Dienstnutzer heisst (#581) -- die Zeile nennt
    den Besitzer, den die Datei tatsaechlich hat."""
    root = _tree(tmp_path)
    lines = _check(root, uid=NOBODY_HAS_THIS_ID)
    hit = next(line for line in _warns(lines) if "nginx.conf" in line)
    assert f"owned by {pwd.getpwuid(ME).pw_name}" in hit


def test_unbekannte_uid_wird_als_zahl_genannt(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    real_stat = os.stat

    def fake_stat(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if str(path).endswith("nginx.conf"):
            fields = list(result)
            fields[stat.ST_UID] = NOBODY_HAS_THIS_ID
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(nginx_perms.os, "stat", fake_stat)
    hit = next(line for line in _warns(_check(root)) if "nginx.conf" in line)
    assert f"owned by uid {NOBODY_HAS_THIS_ID}" in hit


def test_gruppenschreibbar_fuer_fremde_gruppe_wird_gemeldet(tmp_path):
    root = _tree(tmp_path)
    site = root / "sites-available" / "baluhost"
    site.chmod(0o664)
    lines = _check(root, gid=NOBODY_HAS_THIS_ID)
    hit = [line for line in _warns(lines) if line.startswith(f"WARN: {site}:")]
    assert len(hit) == 1
    assert "group-writable" in hit[0]


def test_gruppenschreibbar_fuer_die_root_gruppe_ist_kein_befund(tmp_path):
    """root:root 0664 gibt niemandem etwas, der nicht ohnehin root ist."""
    root = _tree(tmp_path)
    (root / "sites-available" / "baluhost").chmod(0o664)
    assert _warns(_check(root)) == []


def test_weltschreibbar_wird_gemeldet(tmp_path):
    root = _tree(tmp_path)
    conf = root / "snippets" / "ssl-params.conf"
    conf.chmod(0o646)
    hit = [line for line in _warns(_check(root)) if line.startswith(f"WARN: {conf}:")]
    assert len(hit) == 1
    assert "world-writable" in hit[0]


def test_schreibbares_verzeichnis_wird_gemeldet(tmp_path):
    """Wer in sites-enabled/ schreiben darf, legt dort eine eigene Site ab --
    der Modus der Dateien darin spielt dann keine Rolle mehr."""
    root = _tree(tmp_path)
    enabled = root / "sites-enabled"
    enabled.chmod(0o757)
    hit = [line for line in _warns(_check(root)) if line.startswith(f"WARN: {enabled}:")]
    assert len(hit) == 1


def test_das_wurzelverzeichnis_selbst_wird_geprueft(tmp_path):
    root = _tree(tmp_path)
    root.chmod(0o757)
    assert any(line.startswith(f"WARN: {root}:") for line in _warns(_check(root)))


# ─── Symlinks ────────────────────────────────────────────────────────


def test_symlink_in_den_baum_wird_nicht_doppelt_gemeldet(tmp_path):
    """sites-enabled/baluhost -> sites-available/baluhost ist eine Datei, nicht
    zwei: der Befund steht am Ziel."""
    root = _tree(tmp_path)
    (root / "sites-available" / "baluhost").chmod(0o646)
    warns = _warns(_check(root))
    assert len(warns) == 1
    assert warns[0].startswith(f"WARN: {root / 'sites-available' / 'baluhost'}:")


def test_symlink_aus_dem_baum_heraus_prueft_das_ziel(tmp_path):
    """FRONTEND_DEPLOYMENT.md verlinkt die Site in einen Checkout im
    Home-Verzeichnis. nginx laedt dann, was dort liegt."""
    root = _tree(tmp_path)
    outside = tmp_path / "checkout" / "baluhost-http.conf"
    outside.parent.mkdir()
    outside.write_text("# conf\n", encoding="utf-8")
    outside.chmod(0o646)
    link = root / "sites-enabled" / "extern"
    link.symlink_to(outside)

    warns = _warns(_check(root))
    assert len(warns) == 1
    assert warns[0].startswith(f"WARN: {link}:")
    assert str(outside) in warns[0]


def test_haengender_symlink_ist_kein_absturz(tmp_path):
    root = _tree(tmp_path)
    (root / "sites-enabled" / "tot").symlink_to(tmp_path / "weg")
    lines = _check(root)
    assert len(lines) == 1
    assert lines[0].startswith("PASS: ")


# ─── Die Korrekturzeile ──────────────────────────────────────────────


def test_korrekturzeile_nennt_genau_die_betroffenen_pfade(tmp_path):
    root = _tree(tmp_path)
    site = root / "sites-available" / "baluhost"
    site.chmod(0o664)
    lines = _check(root, gid=NOBODY_HAS_THIS_ID)
    fix = [line for line in lines if line.startswith("WARN: fix: ")]
    assert len(fix) == 1
    assert "sudo chmod go-w" in fix[0]
    assert str(site) in fix[0]
    assert "nginx.conf" not in fix[0]
    assert "chown" not in fix[0], "der Besitzer stimmt -- chown waere ein Befehl ohne Anlass"


def test_korrekturzeile_setzt_den_besitzer_wo_er_falsch_ist(tmp_path):
    root = _tree(tmp_path)
    lines = _check(root, uid=NOBODY_HAS_THIS_ID)
    fix = next(line for line in lines if line.startswith("WARN: fix: "))
    assert "sudo chown root:root" in fix
    assert str(root / "nginx.conf") in fix


def test_korrekturzeile_fasst_kein_ziel_ausserhalb_des_baums_an(tmp_path):
    """Ein `chown root` auf eine Datei in einem Checkout wuerde den Checkout
    beschaedigen. Dort ist der Link das Problem, nicht die Datei."""
    root = _tree(tmp_path)
    outside = tmp_path / "checkout.conf"
    outside.write_text("# conf\n", encoding="utf-8")
    outside.chmod(0o646)
    (root / "sites-enabled" / "extern").symlink_to(outside)

    lines = _check(root)
    assert not any(line.startswith("WARN: fix: ") for line in lines)
    assert any("replace the link" in line for line in lines)


def test_pfade_mit_leerzeichen_sind_in_der_korrekturzeile_gequotet(tmp_path):
    root = _tree(tmp_path)
    odd = root / "sites-available" / "alte site"
    odd.write_text("# conf\n", encoding="utf-8")
    odd.chmod(0o646)
    fix = next(line for line in _check(root) if line.startswith("WARN: fix: "))
    assert f"'{odd}'" in fix


# ─── Einstiegspunkt ──────────────────────────────────────────────────


def test_main_endet_ohne_strict_immer_mit_0(tmp_path, capsys):
    """Der Deploy darf an diesem Check nie scheitern -- er meldet nur."""
    root = _tree(tmp_path)
    (root / "nginx.conf").chmod(0o646)
    assert nginx_perms.main(["--config-dir", str(root)]) == 0
    assert "WARN: " in capsys.readouterr().out


def test_main_strict_endet_bei_befund_mit_1(tmp_path, capsys):
    """verify-install.sh braucht einen Exit-Code, kein Log zum Lesen.

    Weltschreibbar statt "falscher Besitzer": main() vertraut nur root, und
    der CI-Container fuehrt die Suite als root aus -- dort gehoerte der Baum
    dem Richtigen."""
    root = _tree(tmp_path)
    (root / "nginx.conf").chmod(0o646)
    assert nginx_perms.main(["--config-dir", str(root), "--strict"]) == 1
    assert "world-writable" in capsys.readouterr().out


def test_main_strict_endet_ohne_befund_mit_0(tmp_path, capsys):
    assert nginx_perms.main(["--config-dir", str(tmp_path / "fehlt"), "--strict"]) == 0
    assert "PASS: " in capsys.readouterr().out


def test_main_ueberlebt_einen_absturz_der_pruefung(tmp_path, capsys, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(nginx_perms, "check_tree", boom)
    assert nginx_perms.main(["--config-dir", str(tmp_path)]) == 0
    assert "WARN: nginx permission check could not run: kaputt" in capsys.readouterr().out


def test_main_strict_wertet_einen_absturz_als_befund(tmp_path, capsys, monkeypatch):
    """Eine Pruefung, die nicht lief, hat nichts bestaetigt."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(nginx_perms, "check_tree", boom)
    assert nginx_perms.main(["--config-dir", str(tmp_path), "--strict"]) == 1


def test_vertrauter_besitzer_ist_standardmaessig_root():
    """Die Injektion ist fuer Tests da. Ohne sie gilt: nur root."""
    signature = inspect.signature(check_tree)
    assert signature.parameters["trusted_uid"].default == 0
    assert signature.parameters["trusted_gid"].default == 0
