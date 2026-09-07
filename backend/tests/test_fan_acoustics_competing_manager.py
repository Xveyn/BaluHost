"""Erkennung eines zweiten Verwalters der Akustik-Knoten (#570 Punkt 2).

Ein auskommentierter pmfw_options-Block ist keine Konkurrenz -- LACT liest
ihn nicht, also darf BaluHost deswegen nicht warnen.
"""
from pathlib import Path

from app.api.routes import fans as fans_module


def _lact_config(tmp_path: Path, text: str, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(text, encoding="utf-8")
    monkeypatch.setattr(fans_module, "LACT_CONFIG_PATH", cfg)


def test_ein_aktiver_block_meldet_lact(tmp_path, monkeypatch):
    _lact_config(tmp_path, "gpus:\n  1002:744C:\n    pmfw_options:\n      acoustic_limit: 3000\n", monkeypatch)
    assert fans_module._competing_manager() == "lact"


def test_ein_auskommentierter_block_meldet_nichts(tmp_path, monkeypatch):
    _lact_config(tmp_path, "gpus:\n  1002:744C:\n    # pmfw_options:\n    #   acoustic_limit: 3000\n", monkeypatch)
    assert fans_module._competing_manager() is None


def test_eingerueckt_auskommentiert_meldet_ebenfalls_nichts(tmp_path, monkeypatch):
    _lact_config(tmp_path, "gpus:\n      #pmfw_options:\n", monkeypatch)
    assert fans_module._competing_manager() is None


def test_ein_nachgestellter_kommentar_hebt_den_schluessel_nicht_auf(tmp_path, monkeypatch):
    _lact_config(tmp_path, "    pmfw_options:  # von BaluHost uebernommen\n", monkeypatch)
    assert fans_module._competing_manager() == "lact"


def test_eine_fehlende_datei_meldet_nichts(tmp_path, monkeypatch):
    monkeypatch.setattr(fans_module, "LACT_CONFIG_PATH", tmp_path / "gibt-es-nicht.yaml")
    assert fans_module._competing_manager() is None


def test_eine_datei_in_latin1_macht_den_get_nicht_kaputt(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_bytes(b"pmfw_options:\n# Kommentar mit \xfc\n")
    monkeypatch.setattr(fans_module, "LACT_CONFIG_PATH", cfg)
    assert fans_module._competing_manager() in ("lact", None)
