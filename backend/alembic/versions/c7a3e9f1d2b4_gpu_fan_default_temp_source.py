"""AMD-GPU-Luefter einmalig auf die GPU-Temperaturquelle stellen (#606)

Revision ID: c7a3e9f1d2b4
Revises: b4e1d8a2c7f3
Create Date: 2026-09-18 00:00:00.000000

Bis #606 bekam jeder neu angelegte Luefter den CPU-Sensor als Quelle, auch
ein GPU-Luefter. Der Code-Fix wirkt nur bei der Erstanlage; _load_fan_configs
fasst bestehende Zeilen bewusst nie an. Diese Migration holt den Bestand
genau einmal nach.

Erfasst werden nur Zeilen, deren Quelle aus der Default-Welt stammt (leer,
hwmon:-Kennung oder nackte Alt-ID). gpu:, mix: und disk: waren nie ein
Default, also eine bewusste Wahl -- die bleiben. Einen bewusst gesetzten
hwmon-Sensor kann die Migration vom Default nicht unterscheiden (Aenderungen
an Luefter-Configs werden nicht auditiert); das ist die im Issue akzeptierte
Unschaerfe. Weil Alembic die Revision nur einmal anwendet, bleibt eine
spaetere Umstellung durch den Nutzer erhalten.

Der GPU-Luefter wird am Treiber erkannt: die stabile fan_id beginnt mit
"amdgpu-" (#532), und name lautet immer "<treiber> PWM<n>" -- letzteres
erfasst auch Zeilen, die noch eine hwmon-indizierte fan_id tragen.
Deaktivierte Zeilen sind eingeschlossen: eine per #585 wieder aufgenommene
Zeile kaeme sonst mit dem alten Fehler zurueck.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a3e9f1d2b4'
down_revision: Union[str, Sequence[str], None] = 'b4e1d8a2c7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Als Literal, nicht aus fan_sources importiert: die Migration muss auch
# laufen, wenn sich der Anwendungscode spaeter aendert.
_GPU_SOURCE = "gpu:junction"
_USER_CHOSEN_PREFIXES = ("gpu:", "mix:", "disk:")


def retarget_gpu_fans(bind) -> int:
    """Setzt die Quelle der betroffenen Zeilen um; gibt deren Anzahl zurueck.

    updated_at bleibt absichtlich unveraendert (Core-Update, kein ORM-onupdate):
    der Identitaets-Abgleich waehlt bei Kollisionen die juengste Zeile, und eine
    Datenkorrektur soll diese Reihenfolge nicht verschieben.
    """
    fan_configs = sa.table(
        "fan_configs",
        sa.column("fan_id", sa.String),
        sa.column("name", sa.String),
        sa.column("temp_sensor_id", sa.String),
    )
    sensor = fan_configs.c.temp_sensor_id
    stmt = (
        sa.update(fan_configs)
        .where(sa.or_(
            fan_configs.c.fan_id.like("amdgpu-%"),
            fan_configs.c.name.like("amdgpu PWM%"),
        ))
        .where(sa.or_(
            sensor.is_(None),
            sa.not_(sa.or_(*(sensor.like(p + "%") for p in _USER_CHOSEN_PREFIXES))),
        ))
        .values(temp_sensor_id=_GPU_SOURCE)
    )
    return bind.execute(stmt).rowcount


def upgrade() -> None:
    """Stellt AMD-GPU-Luefter mit Default-Quelle auf gpu:junction um."""
    retarget_gpu_fans(op.get_bind())


def downgrade() -> None:
    """Kein Rueckweg: der vorherige Sensor ist nicht gespeichert.

    Er war ohnehin falsch (CPU- oder Mainboard-Sensor fuer eine
    Grafikkarte); die neue Quelle bleibt auch nach einem Downgrade gueltig.
    """
