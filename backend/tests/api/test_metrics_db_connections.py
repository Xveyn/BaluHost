"""baluhost_database_connections war deklariert, aber nie gesetzt (#300/#494)."""
from app.api.routes.metrics import collect_database_metrics, registry


def test_database_connections_gauge_is_populated(db_session):
    collect_database_metrics(db_session)

    value = registry.get_sample_value("baluhost_database_connections")
    assert value is not None, "Gauge wurde nicht gesetzt"
    assert value >= 0


def test_collect_survives_a_pool_without_counters(db_session, monkeypatch):
    """Der StaticPool der Tests hat checkedout() nicht — das darf den
    kompletten Metrik-Endpoint nicht mitreißen."""
    monkeypatch.setattr(
        "app.api.routes.metrics.sample_pool", lambda engine: None
    )

    collect_database_metrics(db_session)  # darf nicht werfen
