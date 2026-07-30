"""baluhost_database_connections war deklariert, aber nie gesetzt (#300/#494)."""
import logging
from app.api.routes.metrics import collect_database_metrics, registry
from app.core.concurrency_probe import PoolSample


def test_database_connections_gauge_is_populated(db_session, monkeypatch):
    """Gauge muss den checked_out-Wert aus dem PoolSample lesen, nicht andere Felder.
    Mit unterschiedlichen Werten für alle Felder wird sichtbar, wenn der Code
    das falsche Feld liest: overflow=3, open_connections=9, size=5 würden
    unterschiedliche Fehler erzeugen."""
    monkeypatch.setattr(
        "app.api.routes.metrics.sample_pool",
        lambda engine: PoolSample(
            checked_out=7, overflow=3, open_connections=9, size=5, max_overflow=10
        )
    )

    collect_database_metrics(db_session)

    value = registry.get_sample_value("baluhost_database_connections")
    assert value == 7.0, f"Gauge should read checked_out (7), not another field (got {value})"


def test_collect_survives_a_pool_without_counters(db_session, monkeypatch, caplog):
    """Der StaticPool der Tests hat checkedout() nicht — der Guard `if pool is not None:`
    muss schützen. Ohne den Guard würde None.checked_out einen AttributeError werfen,
    der vom except Exception abgefangen und als WARNING geloggt wird. Mit dem Guard
    sollte kein WARNING geloggt werden."""
    monkeypatch.setattr(
        "app.api.routes.metrics.sample_pool", lambda engine: None
    )

    caplog.set_level(logging.WARNING, logger="app.api.routes.metrics")

    collect_database_metrics(db_session)  # darf nicht werfen

    # Mit dem Guard ist keine Warning zu erwarten.
    # Ohne den Guard hätte None.checked_out einen AttributeError erzeugt,
    # der vom except Exception abgefangen und geloggt würde.
    assert not caplog.records, (
        "No warning should be logged when pool is None and the guard is present. "
        f"Got records: {caplog.records}"
    )
