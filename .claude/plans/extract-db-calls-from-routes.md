# Plan: DB-Calls aus Route-Dateien in Service-Klassen extrahieren

**Status**: In Arbeit (Phase 1.1-1.4 erledigt)
**Branch**: `development`
**Umfang**: ~234 direkte DB-Calls in 29 Route-Dateien

---

## Ziel

Alle direkten Datenbankzugriffe (`db.query`, `db.add`, `db.commit`, `db.delete`, `db.merge`, `db.refresh`, `db.scalar`, `db.execute`, `db.flush`, `db.rollback`) aus Route-Dateien in Service-Klassen verschieben. Routes sollen nur noch Service-Methoden aufrufen — keine ORM-Logik.

---

## Phasen

### Phase 1: Neue Service-Klassen erstellen (kein Service vorhanden)

Diese Route-Dateien haben **kein** zugehöriges Service-Modul — alles ist direkt im Route-Handler.

| # | Route-Datei | DB-Calls | Neues Service-Modul | Scope |
|---|-------------|----------|---------------------|-------|
| 1.1 | `server_profiles.py` | 18 | `services/server_profile_service.py` | CRUD: create, list, get, update, delete ServerProfile |
| 1.2 | `vpn_profiles.py` | 15 | `services/vpn/profile_service.py` | CRUD: create, list, get, update, delete VPNProfile |
| 1.3 | `plugins.py` | 14 | `services/plugin_service.py` | enable, disable, config, delete InstalledPlugin |
| 1.4 | `tapo.py` | 12 | `services/tapo_service.py` | CRUD: create, list, get, update, delete TapoDevice |
| 1.5 | `pihole.py` | 12 | Erweitern: `services/pihole/service.py` | DNS-Query-Analytics (get_queries, blocked, clients, hourly) |
| 1.6 | `firebase_config.py` | 2 | `services/notifications/firebase_config.py` | update_firebase_devices |

**Vorgehen pro Datei:**
1. Route-Datei lesen, alle `db.*`-Aufrufe identifizieren
2. Service-Klasse/Funktionen erstellen mit identischer Logik
3. Route-Handler auf Service-Aufrufe umschreiben
4. Tests anpassen/erstellen

---

### Phase 2: Bestehende Services erweitern (Service existiert, aber Route hat noch DB-Calls)

| # | Route-Datei | DB-Calls | Bestehendes Service-Modul | Scope |
|---|-------------|----------|---------------------------|-------|
| 2.1 | `vcl.py` | 49 | `services/versioning/vcl.py` | Größter Brocken — Admin-Endpoints, Version-Queries, Settings |
| 2.2 | `files.py` | 18 | `services/files/*.py` | Share-Bulk, Public-Share, Delete mit Ownership-Checks |
| 2.3 | `sync.py` | 12 | `services/sync/*.py` | Mobile-Device-Register, Init-Sync, File-Versions |
| 2.4 | `shares.py` | 10 | `services/shares.py` | list_shareable_users, create/update/delete FileShare |
| 2.5 | `ssd_file_cache.py` | 10 | `services/cache/ssd_file_cache.py` | clear, cache_file, exclude_file |
| 2.6 | `users.py` | 8 | `services/users.py` | list_users Aggregation (query + scalar), toggle_active |
| 2.7 | `devices.py` | 8 | `services/mobile.py` | list_mobile/sync_devices, update_device_name |
| 2.8 | `mobile.py` | 7 | `services/mobile.py` | delete_device, send_push, upload_queue |
| 2.9 | `samba.py` | 5 | `services/samba_service.py` | list/toggle samba users |
| 2.10 | `monitoring.py` | 5 | `services/monitoring/*` | CPU/Memory/Network/DiskIO Stats |

---

### Phase 3: Kleinere Aufräumarbeiten (1-4 DB-Calls)

| # | Route-Datei | DB-Calls | Service-Modul | Scope |
|---|-------------|----------|---------------|-------|
| 3.1 | `auth.py` | 4 | `services/auth.py` | User-Record-Lookups in change_password, 2FA |
| 3.2 | `sync_advanced.py` | 4 | `services/sync/*.py` | selective_sync config |
| 3.3 | `vpn.py` | 4 | `services/vpn/*.py` | get_available_types, server_config |
| 3.4 | `system.py` | 3 | `services/system.py` | Sample-Cleanup in get_system_info |
| 3.5 | `metrics.py` | 2 | `services/telemetry.py` | admin_count, user_count |
| 3.6 | `energy.py` | 2 | `services/power/*.py` | power_consumption queries |
| 3.7 | `updates.py` | 2 | `services/update/*.py` | version_history queries |
| 3.8 | `chunked_upload.py` | 3 | `services/files/chunked_upload.py` | FileMetadata lookups |
| 3.9 | `api_keys.py` | 1 | `services/api_key_service.py` | list_api_keys |
| 3.10 | `benchmark.py` | 1 | `services/benchmark/*` | commit nach operation |
| 3.11 | `webdav.py` | 1 | `services/webdav_service.py` | user query |
| 3.12 | `activity.py` | 1 | `services/file_activity.py` | commit |
| 3.13 | `sync_compat.py` | 1 | `services/sync/*.py` | legacy device list |

---

## Reihenfolge & Commits

Jede Route-Datei = 1 Commit. Empfohlene Reihenfolge:

**Batch A — Neue Services (Phase 1):** unabhängig voneinander, gut parallelisierbar
```
refactor(server-profiles): extract DB calls into server_profile_service
refactor(vpn-profiles): extract DB calls into vpn profile_service
refactor(plugins): extract DB calls into plugin_service
refactor(tapo): extract DB calls into tapo_service
refactor(pihole): move DNS query analytics into pihole service
refactor(firebase): extract device update into firebase config service
```

**Batch B — Große Service-Erweiterungen (Phase 2 Top 3):**
```
refactor(vcl): migrate remaining 49 DB calls to VCL service
refactor(files): migrate remaining DB calls to file services
refactor(sync): migrate remaining DB calls to sync services
```

**Batch C — Mittlere Erweiterungen (Phase 2 Rest):**
```
refactor(shares): migrate DB calls to shares service
refactor(ssd-cache): migrate DB calls to cache service
refactor(users): migrate DB calls to users service
refactor(devices): migrate DB calls to mobile service
refactor(mobile): migrate DB calls to mobile service
refactor(samba): migrate DB calls to samba service
refactor(monitoring): migrate DB calls to monitoring services
```

**Batch D — Cleanup (Phase 3):** klein, schnell
```
refactor(routes): migrate remaining small DB calls to services
```

---

## Muster für die Extraktion

### Vorher (in Route):
```python
@router.get("/profiles")
async def list_profiles(db: Session = Depends(get_db), ...):
    profiles = db.query(ServerProfile).filter(...).all()
    total = db.query(func.count(ServerProfile.id)).scalar()
    return {"profiles": profiles, "total": total}
```

### Nachher (Service + Route):
```python
# services/server_profile_service.py
def list_profiles(db: Session, user_id: int) -> tuple[list[ServerProfile], int]:
    profiles = db.query(ServerProfile).filter(...).all()
    total = db.query(func.count(ServerProfile.id)).scalar()
    return profiles, total

# routes/server_profiles.py
@router.get("/profiles")
async def list_profiles(db: Session = Depends(get_db), ...):
    profiles, total = server_profile_service.list_profiles(db, current_user.id)
    return {"profiles": profiles, "total": total}
```

---

## Regeln

1. **Keine Verhaltensänderung** — rein strukturelles Refactoring
2. **db-Parameter** bleibt in Service-Funktionen (kein eigenes Session-Management)
3. **HTTPException** bleibt in Routes — Services werfen ValueError/eigene Exceptions
4. **Bestehende Tests** müssen weiterhin grün sein
5. **Keine neuen Features** — nur Verschiebung der DB-Logik
6. **Ein Commit pro Route-Datei** für saubere Git-History

---

## Risiken

- **vcl.py (49 Calls)**: Größtes Risiko — viele verschachtelte Queries, Admin-vs-User-Logik
- **files.py**: Ownership-Checks eng mit DB verwoben, _jail_path() Interaktion beachten
- **Test-Coverage**: Einige extrahierte Funktionen haben evtl. keine direkten Tests

---

## Fortschritt

- [x] Phase 1.1: server_profiles.py (18 DB-Calls) — `server_profile_service.py` + SSH key update bug fix
- [x] Phase 1.2: vpn_profiles.py (15 DB-Calls) — `vpn/profile_crud.py`
- [x] Phase 1.3: plugins.py (14 DB-Calls) — `plugin_service.py`
- [x] Phase 1.4: tapo.py (12 DB-Calls) — `tapo_service.py`
- [ ] Phase 1.5: pihole.py (12 DB-Calls)
- [ ] Phase 1.6: firebase_config.py (2 DB-Calls)
- [ ] Phase 2.1: vcl.py (49 DB-Calls)
- [ ] Phase 2.2: files.py (18 DB-Calls)
- [ ] Phase 2.3: sync.py (12 DB-Calls)
- [ ] Phase 2.4: shares.py (10 DB-Calls)
- [ ] Phase 2.5: ssd_file_cache.py (10 DB-Calls)
- [ ] Phase 2.6: users.py (8 DB-Calls)
- [ ] Phase 2.7: devices.py (8 DB-Calls)
- [ ] Phase 2.8: mobile.py (7 DB-Calls)
- [ ] Phase 2.9: samba.py (5 DB-Calls)
- [ ] Phase 2.10: monitoring.py (5 DB-Calls)
- [ ] Phase 3: Restliche 13 Dateien (1-4 DB-Calls je)
