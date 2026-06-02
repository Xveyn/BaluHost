# Power-Pille: Profil/Preset anzeigen — Design

**Date:** 2026-06-02
**Status:** Approved
**Author:** Sven (Xveyn) + Claude
**Context:** Erweiterung der Topbar-Statusleiste (`docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md`)

## Problem

Die Power-Pille in der Topbar-Statusleiste zeigt aktuell nur die **Stufe** (idle/low/medium/surge),
die der PowerManager je nach Last/Demand wählt — vom Nutzer als „Intensität" wahrgenommen.
Das **benannte Preset** (z.B. „Balanced", „Performance" oder ein eigenes), das die CPU-Steuerung
tatsächlich konfiguriert, wird nicht angezeigt.

Heutiges Verhalten (`backend/app/services/status_bar/collectors.py:30-46`):

```python
@_safe()
async def collect_power(db, role):
    status = await get_power_manager().get_power_status()
    profile = (getattr(status, "current_profile", None) or ...)
    if not profile:
        return None
    raw = getattr(profile, "value", profile)
    label = str(raw).replace("_", " ").title()
    return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}
```

→ Pille zeigt nur z.B. `⚡ Surge`.

## Leitprinzip

**Die Pille zeigt das, was in der Praxis die CPU-Frequenz bestimmt.**

Dynamic Mode und Presets schließen sich faktisch aus:

- **Profil-/Preset-Modus** (Normalfall): Auto-Scaling wählt eine Stufe; das **aktive Preset**
  mappt jede Stufe auf konkrete MHz-Werte. → Preset bestimmt die Steuerung.
- **Dynamic Mode** (`manager.py:549-551`: `if self._dynamic_mode_enabled: return`):
  Die Stufen-Auswahl ist eingefroren; der **Kernel-Governor** (z.B. `schedutil`/`ondemand`/`powersave`)
  regelt die Frequenz direkt innerhalb der Dynamic-Min/Max-Grenzen. Das Preset wird **nicht**
  angewendet; `current_profile`/`active_preset` bleiben stale. → Governor bestimmt die Steuerung.

`get_power_status()` (`manager.py:1074-1173`) liefert alle nötigen Felder:
`dynamic_mode_enabled: bool`, `dynamic_mode_config.governor`, `current_profile: PowerProfile`,
`active_preset: Optional[PowerPresetSummary]` (mit `.name`).

## Lösung

Drei Pille-Zustände, abgeleitet aus dem Leitprinzip:

| Situation | Steuert tatsächlich | Pille (`label`) |
|---|---|---|
| Dynamic Mode aktiv | Kernel-Governor | `Dynamisch · schedutil` |
| Profil-Modus + aktives Preset | Preset (Stufe → MHz) | `Balanced · Surge` |
| Profil-Modus, kein Preset | Default-Mapping der Stufe | `Surge` |

Darstellung: alles im `label` mit `·`-Trenner, kein `value`-Feld. Icon bleibt `Zap`, Tone bleibt `info`.

## Architektur

**Einziger geänderter Code:** `collect_power` in `backend/app/services/status_bar/collectors.py`.
Reine Backend-Änderung — die generische `Pill`-Komponente (`client/src/components/ui/Pill.tsx`)
und der `PillRenderer` (`client/src/components/topbar/pillRenderers.tsx`) bleiben unverändert,
da sie `label` bereits rendern.

```python
@_safe()
async def collect_power(db, role):
    status = await get_power_manager().get_power_status()

    # Dynamic Mode: Kernel-Governor regelt direkt — Preset/Stufe sind eingefroren
    # und spiegeln nicht die Realität, daher Modus + Governor zeigen.
    if getattr(status, "dynamic_mode_enabled", False):
        gov = getattr(getattr(status, "dynamic_mode_config", None), "governor", None)
        label = f"Dynamisch · {gov}" if gov else "Dynamisch"
        return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}

    profile = getattr(status, "current_profile", None)
    if not profile:
        return None
    level = str(getattr(profile, "value", profile)).replace("_", " ").title()  # "Surge"

    preset = getattr(status, "active_preset", None)
    preset_name = getattr(preset, "name", None) if preset else None
    label = f"{preset_name} · {level}" if preset_name else level
    return {"kind": "state", "tone": "info", "label": label, "icon": "Zap"}
```

Der `@_safe()`-Dekorator bleibt: jeder Fehler im Collector → `None` (Pille verschwindet, kein 5xx).

## i18n

Die Stufe wird wie bisher roh englisch title-case dargestellt (`Surge`/`Idle`/...), unverändert
zum heutigen Verhalten. Das deutsche Literal `"Dynamisch"` ist konsistent mit anderen Collectorn
in derselben Datei (`"läuft"`, `"fehlgeschlagen"`, `"verbunden"`). Der Governor-Name (`schedutil`)
ist ein technischer Bezeichner und bleibt unverändert. Keine neuen i18n-Keys nötig.

## Edge Cases

| Fall | Verhalten |
|---|---|
| `dynamic_mode_enabled=True`, aber `dynamic_mode_config=None` | `label = "Dynamisch"` (ohne Governor) |
| `active_preset=None` (kein Preset aktiv) | Fallback: nur Stufe, z.B. `Surge` (heutiges Verhalten) |
| `current_profile=None` (kein Status) | `None` → Pille verschwindet (wie heute) |
| Langer eigener Preset-Name | Pille wird breiter; Topbar hat Platz (akzeptiert) |
| `get_power_status()` wirft | `@_safe()` fängt ab → `None`, kein 5xx |
| Follower-Worker (nicht primary) | `get_power_status()` hydratisiert aus SHM/DB — gleiche Felder verfügbar |

## Security

Keine neue Datenexposition: `active_preset.name`, `current_profile` und Governor-Name sind keine
sensiblen Daten (kein Pfad, keine Seriennummer, kein Geheimnis). Die `power`-Pille ist im Katalog
nicht `visibility_locked` und darf laut bestehendem Design für „All Users" freigeschaltet werden —
der Preset-Name ändert daran nichts. Auth/Rate-Limiting des `/state`-Endpoints bleiben unberührt.

## Tests

Ergänzung in `backend/tests/services/test_status_bar_collectors.py` (bestehende Collector-Test-Datei;
es existiert noch **kein** `collect_power`-Test). Es gibt keinen Power-Eintrag dort, der angepasst werden müsste.

| Test | Verifiziert |
|---|---|
| `test_power_pill_preset_and_level` | `active_preset.name="Balanced"`, `current_profile.value="surge"`, dynamic aus → `label == "Balanced · Surge"`, kein `value` |
| `test_power_pill_no_preset_fallback` | `active_preset=None`, `current_profile.value="surge"`, dynamic aus → `label == "Surge"` |
| `test_power_pill_dynamic_mode_with_governor` | `dynamic_mode_enabled=True`, `dynamic_mode_config.governor="schedutil"` → `label == "Dynamisch · schedutil"` |
| `test_power_pill_dynamic_mode_no_config` | `dynamic_mode_enabled=True`, `dynamic_mode_config=None` → `label == "Dynamisch"` |
| `test_power_pill_silent_without_profile` | `current_profile=None`, dynamic aus → `None` (Pille verschwindet) |

**Mock-Strategie** (analog zu den bestehenden Tests in der Datei, `unittest.mock` + `AsyncMock`):
`collect_power` importiert `get_power_manager` lokal aus `app.services.power.manager`, daher dort patchen.
`get_power_status` ist `async` → `AsyncMock`. Beispielmuster:

```python
@pytest.mark.asyncio
async def test_power_pill_preset_and_level():
    from app.services.status_bar import collectors
    preset = MagicMock()
    preset.name = "Balanced"            # WICHTIG: nicht MagicMock(name="Balanced") —
                                        # `name` ist ein reserviertes MagicMock-Kwarg!
    status = MagicMock(
        dynamic_mode_enabled=False,
        current_profile=MagicMock(value="surge"),
        active_preset=preset,
    )
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label"] == "Balanced · Surge"
    assert "value" not in result
```

Für den Fallback-Test `current_profile=MagicMock(value="surge")`, `active_preset=None`.
Für `silent_without_profile` muss `current_profile=None` **und** `active_profile`/`profile` fehlen
(im MagicMock explizit auf `None` setzen, da `getattr` sonst neue Mock-Attribute liefert):
`status = MagicMock(dynamic_mode_enabled=False, current_profile=None, active_profile=None, profile=None)`.

## Out of Scope

- Lokalisierung der Stufen-Namen (idle/low/medium/surge) — bleibt wie heute englisch
- Dedizierter Frontend-`PowerPill.tsx`-Renderer (nicht nötig, generische Pille genügt)
- Anzeige der Live-Frequenz/MHz in der Pille (eigener Click-Through zum Energy-Tab genügt)
- Tooltip mit Preset-Details (browser-natives `title` aus `label` reicht)

## Build Order

1. `collect_power` in `collectors.py` auf Drei-Zustands-Logik umstellen
2. 5 Tests in `backend/tests/services/test_status_bar_collectors.py` ergänzen
3. `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -v` — grün
4. Manueller Smoketest: Energy-Tab Preset wechseln → Pille zeigt neuen Namen; Dynamic Mode an/aus → Pille wechselt zu `Dynamisch · <governor>` und zurück

## References

- `backend/app/services/status_bar/collectors.py:30-46` — zu ändernder Collector
- `backend/app/services/power/manager.py:1074-1173` — `get_power_status()`, befüllt `active_preset` + Dynamic-Felder
- `backend/app/services/power/manager.py:549-551` — Dynamic Mode deaktiviert Auto-Scaling (Beleg für „schließt sich aus")
- `backend/app/schemas/power.py:111-130` — `PowerStatusResponse` (Felder), `PowerPresetSummary`
- `client/src/components/ui/Pill.tsx` — generische Pille (`label`/`value`-Rendering, unverändert)
- `docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md` — Basis-Design der Statusleiste
