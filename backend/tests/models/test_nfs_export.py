"""Tests for the NfsExport model."""
from sqlalchemy.orm import Session

from app.models.nfs_export import NfsExport


def test_nfs_export_roundtrip(db_session: Session):
    exp = NfsExport(
        path="Media",
        clients="192.168.1.0/24",
        read_only=False,
        root_squash=True,
        enabled=True,
        comment="media share",
    )
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)

    assert exp.id is not None
    got = db_session.query(NfsExport).filter_by(path="Media").one()
    assert got.clients == "192.168.1.0/24"
    assert got.read_only is False
    assert got.root_squash is True
    assert got.enabled is True
    assert got.comment == "media share"


def test_nfs_export_defaults(db_session: Session):
    exp = NfsExport(path="Docs", clients="*")
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)
    assert exp.read_only is False
    assert exp.root_squash is True
    assert exp.enabled is True
