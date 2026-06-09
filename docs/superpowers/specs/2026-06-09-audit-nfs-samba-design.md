# Spec: Audit-Logging für NFS/Samba-Share-Mutationen (#195)

**Datum:** 2026-06-09
**Branch:** `fix/195-audit-nfs-samba` (von `origin/main`)
**Issue:** #195 — *audit: log NFS/Samba share mutations via `get_audit_logger_db()`*
**Tracking-Ursprung:** Finaler Review von PR #194 (NFS-Feature #183)

## Problem

Share-Mutationen für **NFS** und **Samba** werden nicht ins Audit-Log geschrieben.
Admin-Operationen, die Netzwerk-Exporte anlegen/ändern/löschen (Exposition von
Verzeichnissen ins Netz), hinterlassen damit keine nachvollziehbare Spur — entgegen
der Projektregel (`.claude/rules/security-agent.md` → ALWAYS: „Log security-relevant
actions … (login, password change, admin ops …)").

Betroffene Handler ohne Audit-Aufruf:
- `backend/app/api/routes/nfs.py` — `create_nfs_export`, `update_nfs_export`, `delete_nfs_export`
- `backend/app/api/routes/samba.py` — `toggle_smb_user`

Beide Endpoints sind admin-gated, rate-limited und validiert — **kein akutes Loch**,
sondern eine Lücke in der Audit-Nachvollziehbarkeit. Severity: niedrig–mittel.

## Ziel

Jede erfolgreiche **und** fehlgeschlagene Share-Mutation an NFS-Exports und SMB-User-Zugriff
erzeugt einen Audit-Log-Eintrag über `get_audit_logger_db().log_event(...)`.

## Nicht-Ziel (Out of Scope)

- Kein Redesign des bestehenden Fehlerverhaltens „DB committed, aber `apply_exports()`
  fehlgeschlagen → 500" (Inkonsistenz-Fenster). Der Audit-Eintrag spiegelt diesen Zustand
  nur wider; das Verhalten selbst bleibt unverändert. Falls relevant: eigenes Issue.
- Keine neuen Helper-Methoden in `AuditLoggerDB` (bewusste Entscheidung: `log_event` direkt).
- Keine Frontend-Änderungen.

## Designentscheidungen

1. **`log_event` direkt, `event_type="SYSTEM_CONFIG"`.** Kein neuer Code im Logger.
   `SYSTEM_CONFIG` ist bereits in `ADMIN_ONLY_EVENTS` (`logger_db.py:19`) → Einträge sind
   für Nicht-Admins in der Audit-Ansicht verborgen. Entspricht dem Issue-Vorschlag.
2. **Erfolg + Fehler loggen** (wie VPN-Routes in `vpn.py`):
   - Validierungs-Ablehnungen (404/409) → `success=False` vor dem `raise`.
   - Service-Fehler (`regenerate_*`/`apply_*`/`reload_*`) → `try/except Exception`,
     `success=False` + re-raise.
3. **Signatur-Anpassung:** Das verworfene `_admin=Depends(deps.get_current_admin)` wird in
   allen vier Handlern zu `current_admin: UserPublic = Depends(deps.get_current_admin)`,
   damit `current_admin.username` für `user=` verfügbar ist.
4. **Keine `ip_address`/`user_agent`** — konsistent mit `log_system_config_change` und den
   VPN-Aufrufen.
5. **Keine Secrets in `details`** — bei Samba nur boolean `password_synced`, nie das Passwort.

## Audit-Eintrag pro Handler

Alle Aufrufe: `event_type="SYSTEM_CONFIG"`, `user=current_admin.username`, `db=db`.

| Handler | action (Erfolg) | resource | details (secret-frei) |
|---|---|---|---|
| `create_nfs_export` | `nfs_export_created` | `payload.path` | `clients`, `read_only`, `root_squash`, `enabled` |
| `update_nfs_export` | `nfs_export_updated` | `exp.path` | `clients`, `read_only`, `root_squash`, `enabled` |
| `delete_nfs_export` | `nfs_export_deleted` | `exp.path` | `{"export_id": export_id}` |
| `toggle_smb_user` | `smb_access_enabled` / `smb_access_disabled` | `user.username` | `{"enabled": bool, "password_synced": bool}` |

**Fehler-Actions:** Bei Validierungs-Ablehnungen und Service-Exceptions wird dieselbe
`action` mit `success=False` und gesetztem `error_message` geloggt. Für die 404/409-Fälle,
in denen die Zielressource noch nicht aufgelöst ist:
- `create_nfs_export` 409 → action `nfs_export_created`, resource `payload.path`,
  `error_message="An export for this path already exists"`.
- `update_nfs_export` 404 → action `nfs_export_updated`, resource `str(export_id)`,
  `error_message="Export not found"`.
- `update_nfs_export` 409 → action `nfs_export_updated`, resource `payload.path`,
  `error_message="An export for this path already exists"`.
- `delete_nfs_export` 404 → action `nfs_export_deleted`, resource `str(export_id)`,
  `error_message="Export not found"`.
- `toggle_smb_user` 404 → action je nach `payload.enabled`, resource `str(user_id)`,
  `error_message="User not found"`.

## Kontroll-Fluss (Beispiel `delete_nfs_export`)

```python
audit = get_audit_logger_db()
exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
if not exp:
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_deleted", resource=str(export_id),
        success=False, error_message="Export not found", db=db,
    )
    raise HTTPException(status_code=404, detail="Export not found")

path = exp.path
try:
    db.delete(exp)
    db.commit()
    await nfs_service.regenerate_exports_config()
    await nfs_service.apply_exports()
except Exception as e:
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_deleted", resource=path,
        success=False, error_message=str(e), db=db,
    )
    raise

audit.log_event(
    event_type="SYSTEM_CONFIG", user=current_admin.username,
    action="nfs_export_deleted", resource=path,
    success=True, details={"export_id": export_id}, db=db,
)
return Response(status_code=204)
```

Die anderen Handler folgen demselben Muster (validate → log-fail-on-reject → try/mutate+apply →
log-fail-on-exception → log-success).

## Betroffene Dateien

- `backend/app/api/routes/nfs.py` — Import `get_audit_logger_db`, `UserPublic`; drei Handler.
- `backend/app/api/routes/samba.py` — Import `get_audit_logger_db`, `UserPublic`; `toggle_smb_user`.
- `backend/tests/api/test_nfs_routes.py` — Audit-Assertions erweitern.
- `backend/tests/api/test_samba_routes.py` — **neu**: Toggle-Audit-Tests (Samba-Service gemockt).

## Tests

Vorbild für AuditLog-Assertions: `tests/api/test_require_local_admin.py:63`
(`db_session.query(AuditLog).filter(AuditLog.action == ...)`).

**NFS (`test_nfs_routes.py`):**
- create → genau ein `AuditLog`-Row `action="nfs_export_created"`, `success=True`,
  `user == admin`, `resource == "Media"`.
- update → Row `nfs_export_updated`, `success=True`.
- delete → Row `nfs_export_deleted`, `success=True`.
- delete 404 → Row `nfs_export_deleted`, `success=False`.
- create 409 (Duplikat) → Row `nfs_export_created`, `success=False`.

**Samba (neu `test_samba_routes.py`):**
- Samba-Service-Calls mocken (`enable_smb_user`, `disable_smb_user`, `sync_smb_password`,
  `regenerate_shares_config`, `reload_samba`) — kein echtes `smbpasswd`.
- enable → Row `smb_access_enabled`, `success=True`, `resource == username`,
  `details.enabled is True`.
- disable → Row `smb_access_disabled`, `success=True`.
- toggle auf nicht-existenten User (404) → Row mit `success=False`.
- (Auth-Smoke: regulärer User → 403, wie in `test_nfs_routes.py`.)

## Verifikation

- `python -m pytest tests/api/test_nfs_routes.py tests/api/test_samba_routes.py -v`
- Sicherstellen, dass keine bestehenden NFS-Tests brechen (Signatur-/Verhaltensänderung).
- Sicherheits-Check: kein Passwort in irgendeinem `details`-Dict.
