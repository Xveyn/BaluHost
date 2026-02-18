# Feature: File Ownership Transfer & User-Directory Enforcement

## Status: Planned (2026-02-18)

---

## 1. Ist-Zustand

### 1.1 Ownership-Modell (Dual-Layer, DB-Primary)

**Primary: DB-backed Metadata** (`backend/app/services/files/metadata_db.py`)
- `FileMetadata` model (`backend/app/models/file_metadata.py`) speichert `owner_id` (integer FK zu `users.id`, NOT NULL, ON DELETE CASCADE)
- Jede Datei/Verzeichnis hat einen Eintrag mit `path`, `name`, `owner_id`, `size_bytes`, `is_directory`, `parent_path`, `checksum`
- `get_owner_id()` (line 278) und `set_owner_id()` (line 293) fuer direkte Owner-Manipulation
- `ensure_metadata()` (line 365) erstellt automatisch Metadata fuer ungetrackted Dateien via `_infer_owner_id()` (prueft erstes Pfad-Segment gegen Usernamen)

**Legacy: JSON-based Metadata** (`backend/app/services/files/metadata.py`)
- `.metadata.json` im Storage-Root, mapping path -> `{"ownerId": "..."}`
- Noch importiert, aber DB-Funktionen sind die aktiv genutzten

### 1.2 User-Verzeichnis-Struktur

```
<nas_storage_path>/
  Shared/              -- Community Shared-Verzeichnis, Admin-owned
  <username_A>/        -- User A Home-Verzeichnis
  <username_B>/        -- User B Home-Verzeichnis
  .system/             -- System Metadata, Avatare, Thumbnails
  lost+found/          -- Filesystem Recovery
  .Trash-*/            -- Trash-Verzeichnisse
```

**Home-Directory Lifecycle** (`backend/app/services/users.py`):
- **Erstellung**: `_create_home_directory()` (line 32) erstellt `<storage_root>/<username>/` + `FileMetadata`-Eintrag
- Wird bei User-Erstellung aufgerufen (line 224) fuer Non-Admin Users
- Wird lazy beim Root-Listing aufgerufen (files route line 392)
- **Umbenennung**: `_rename_home_directory()` (line 94) verschiebt Verzeichnis + aktualisiert alle Child-Pfade in DB
- **Loeschung**: `delete_user()` (line 279) loescht via `shutil.rmtree()`, FileMetadata cascade-deleted via FK
- **Startup**: `ensure_user_home_directories()` (line 56) stellt sicher, dass alle Non-Admin Users Home-Dirs haben

### 1.3 Path Security (`_jail_path`)

`backend/app/api/routes/files.py` line 38:
- **Admin**: Pfad wird unveraendert durchgereicht
- **Normal User**: nur `Shared/...`, `<eigener_username>/...`, `Shared with me`, oder explizit geteilte Pfade via `FileShare`
- `..` wird abgelehnt
- **Kritisch**: Jedes Ownership-Feature MUSS `_jail_path` respektieren

### 1.4 Bestehende Owner-Aenderung (LATENTER BUG)

`PUT /api/files/permissions` (files.py line 178) akzeptiert `owner_id` in `FilePermissionsRequest` und ruft `set_owner_id()` auf (line 197). Probleme:
- Aendert NUR DB-Metadata, verschiebt Datei NICHT auf Disk
- Aktualisiert NICHT Child-Pfade bei Verzeichnissen
- Keine Share/Link-Kaskadierung
- **Muss refactored werden** um Residency-Invariante nicht zu verletzen

---

## 2. Architektur-Entscheidung

### Gewaehlter Ansatz: "Transfer = Metadata + Physical Move + Cascade"

Bei Ownership-Transfer von User_A zu User_B:
1. `owner_id` in `file_metadata` aendern
2. Datei/Verzeichnis **physisch verschieben** von User_A-Dir nach User_B-Dir
3. Alle Kinder rekursiv kaskadieren (bei Verzeichnissen)
4. FileShares und ShareLinks kaskadieren oder invalidieren
5. Audit-Log schreiben

### Begruendung

Nur Metadata aendern ohne Move wuerde `_jail_path`-Security brechen:
- Datei `alex/report.pdf` mit Owner `maria` -> Maria kann nicht zugreifen (jail_path laesst nur `maria/...` durch), Alex kann noch zugreifen obwohl nicht mehr Owner
- Die Invariante "Dateien eines Users liegen in seinem Verzeichnis" ist eine **Security-Anforderung**

### Ausnahme: `Shared/`-Verzeichnis

Dateien in `Shared/` sind fuer alle authentifizierten User zugaenglich. Ownership-Transfer dort aendert nur `owner_id` in Metadata, KEINE physische Verschiebung.

---

## 3. Komponenten-Design

### 3.1 Neuer Backend Service: `ownership.py`

**Datei**: `backend/app/services/files/ownership.py`

**Funktionen**:
- `transfer_ownership(path, new_owner_id, requesting_user, db)` — Haupteinstiegspunkt
- `enforce_residency(path, db)` — Scan und Fix von fehlplatzierten Dateien (Reconciliation)
- `_move_to_owner_directory(old_path, new_owner_username, db)` — physischer Move + Metadata-Update
- `_cascade_children_ownership(directory_path, new_owner_id, db)` — rekursives Child-Update
- `_handle_shares_on_transfer(file_metadata_id, old_owner_id, new_owner_id, db)` — Share-Kaskade
- `_check_name_conflict(target_dir, filename)` — Konflikt-Erkennung und -Aufloesung

**Dependencies**:
- `app.services.files.metadata_db`
- `app.services.files.operations`
- `app.services.permissions`
- `app.services.users`
- `app.models.file_share.FileShare`
- `app.models.share_link.ShareLink`
- `app.services.audit.logger_db`

### 3.2 Neuer API-Endpoint

**Datei**: `backend/app/api/routes/files.py` (erweitern)

**Endpoint**: `POST /api/files/transfer-ownership`

```python
# Request
class OwnershipTransferRequest(BaseModel):
    path: str
    new_owner_id: int = Field(..., gt=0)
    recursive: bool = True
    conflict_strategy: Literal["rename", "skip", "overwrite"] = "rename"

# Response
class OwnershipTransferResponse(BaseModel):
    message: str
    transferred_count: int
    skipped_count: int
    new_path: str
    conflicts: list[ConflictInfo]
```

**Security**: `Depends(deps.get_current_user)` + `ensure_owner_or_privileged` + Rate-Limiting + Audit-Log

### 3.3 Reconciliation-Endpoint (Admin-Only)

**Endpoint**: `POST /api/files/enforce-residency`

```python
# Request
class EnforceResidencyRequest(BaseModel):
    dry_run: bool = True
    scope: str = "all"  # "all" oder spezifischer Username

# Response
class EnforceResidencyResponse(BaseModel):
    violations: list[ResidencyViolation]
    fixed_count: int
```

**Security**: `Depends(deps.get_current_admin)` + Rate-Limiting + Audit-Log

### 3.4 Neue Pydantic Schemas

**Datei**: `backend/app/schemas/files.py` (erweitern)

```python
class ConflictInfo(BaseModel):
    original_path: str
    resolved_path: str | None
    action: str  # "renamed", "skipped", "overwritten"

class ResidencyViolation(BaseModel):
    path: str
    current_owner_id: int
    current_owner_username: str
    expected_directory: str
    actual_directory: str
```

### 3.5 DB-Migration

Keine neuen Tabellen noetig. Empfohlen:
- Composite Index `(parent_path, owner_id)` auf `file_metadata` fuer effiziente Residency-Scans

### 3.6 Frontend

**Neue Datei**: `client/src/components/file-manager/OwnershipTransferModal.tsx`
- User-Selector Dropdown (bestehende `allUsers`-Daten wiederverwenden)
- Recursive-Toggle fuer Verzeichnisse
- Conflict-Strategy-Selector
- Dry-Run Preview
- Bestaetigungsschritt

**Modifiziert**: `client/src/pages/FileManager.tsx`
- "Ownership uebertragen"-Button im Aktions-Bereich

**Modifiziert**: `client/src/lib/api.ts`
- `transferOwnership()` und `enforceResidency()` API-Client-Funktionen

---

## 4. Detail-Logik

### 4.1 Transfer-Flow

```
POST /api/files/transfer-ownership
  { path: "alex/Documents/report.pdf", new_owner_id: 3 }

1. VALIDIERUNG
   a. _jail_path(path, user, db) -- Security Check
   b. Datei/Dir existiert auf Disk
   c. new_owner existiert und ist aktiv
   d. Requester ist aktueller Owner ODER Admin
   e. Pfad in Shared/ -> nur Metadata, kein Move
   f. new_owner == current_owner -> no-op, return early

2. ZIEL-PFAD BESTIMMEN
   a. Username von new_owner nachschlagen (z.B. "maria")
   b. Ziel-Pfad: "<maria>/<original_filename>"
   c. Namenskonflikt behandeln:
      - "rename": "report (2).pdf", "report (3).pdf" etc. (max 100)
      - "skip": nicht verschieben, als skipped melden
      - "overwrite": bestehende loeschen, fortfahren (gefaehrlich)

3. LOCK AKQUIRIEREN
   - PostgreSQL Advisory Lock per Pfad-Hash
   - Verhindert gleichzeitige Operationen auf demselben Pfad

4. PHYSISCHER MOVE
   a. source = ROOT_DIR / old_path
   b. target = ROOT_DIR / new_path
   c. Ziel-Parent-Dir sicherstellen
   d. os.rename(source, target) -- atomar auf demselben Filesystem

5. METADATA AKTUALISIEREN
   a. FileMetadata: owner_id, path, parent_path, name aktualisieren
   b. Bei Verzeichnis + recursive:
      - Alle FileMetadata WHERE path LIKE '<old_path>/%' abfragen
      - Fuer jedes Kind: path-Praefix, parent_path, owner_id aktualisieren
   c. In einer einzigen Transaktion committen

6. SHARES KASKADIEREN
   a. FileShare WHERE file_id = <id> AND owner_id = old_owner:
      -> Ownership auf new_owner uebertragen
   b. ShareLink WHERE file_id = <id> AND owner_id = old_owner:
      -> Ownership auf new_owner uebertragen

7. AUDIT-LOG
   - log_file_action(action="ownership_transfer", ...)
   - old_owner, new_owner, old_path, new_path

8. RESPONSE
   - { transferred_count, skipped_count, new_path, conflicts }
```

### 4.2 Residency-Enforcement Flow

```
POST /api/files/enforce-residency
  { dry_run: true, scope: "all" }

1. SCAN
   Fuer jeden User (oder spezifischen wenn scope != "all"):
     a. FileMetadata WHERE owner_id = user.id abfragen
     b. Fuer jeden Eintrag:
        - Pfad beginnt mit "<username>/" -> OK
        - Pfad beginnt mit "Shared/" -> OK (Ausnahme)
        - Pfad beginnt mit "<anderer_username>/" -> VIOLATION
        - Pfad auf Root-Level ohne Slash -> VIOLATION

2. REPORT
   Alle Violations als ResidencyViolation-Objekte sammeln

3. FIX (wenn dry_run == False)
   Fuer jede Violation:
     a. Korrekten Pfad berechnen: "<owner_username>/<filename>"
     b. Namenskonflikte behandeln
     c. Physischer Move + Metadata-Update (wie Transfer Flow)

4. RESPONSE
   { violations, fixed_count }
```

---

## 5. Edge Cases und Fallstricke

### 5.1 Namenskonflikte
- **"rename"**: `report (2).pdf`, `report (3).pdf` etc., max 100 Versuche
- **"skip"**: Nicht verschieben, als skipped melden
- **"overwrite"**: Bestehende loeschen (Metadata, Versionen, Shares) — gefaehrlich, Bestaetigung erforderlich

### 5.2 Rekursiver Transfer mit Mixed Ownership
Verzeichnis `alex/Projects/` enthaelt:
- `alex/Projects/plan.docx` (Owner: alex) -> wird transferiert
- `alex/Projects/shared_notes.txt` (Owner: maria) -> ?

**Entscheidung**: Bei `recursive=True` werden ALLE Kinder transferiert, unabhaengig vom aktuellen Owner. Die Invariante ist "alles im Verzeichnis gehoert dem Verzeichnis-Owner". Dateien die beim alten Owner bleiben sollen, muessen vorher rausverschoben werden.

### 5.3 Aktive Zugriffe / Syncs
- **Aktive Uploads**: Pruefen ob Uploads zum Quell-Pfad laufen, Transfer ablehnen wenn ja
- **Aktive Syncs**: BaluDesk filtert nach `owner_id`, alter Owner sieht Dateien nicht mehr, neuer entdeckt sie beim naechsten Poll — korrekt aber ueberraschend fuer User
- **Offene FileViewer**: Frontend bekommt 404 bei naechstem Request — akzeptabel, wird bereits gehandled

### 5.4 Atomare Move-Garantien
- `os.rename()` ist atomar auf demselben Filesystem (POSIX) — alle User-Dirs sind auf demselben RAID/Storage
- Fuer Verzeichnisse verschiebt `os.rename()` den gesamten Baum atomar
- DB-Transaktion muss als Einheit behandelt werden: physischer Move zuerst, dann DB commit. Bei DB-Fehler: physischen Move rueckgaengig machen

### 5.5 VCL (Version History)
- `FileVersion` referenziert `file_id` (FK zu `file_metadata.id`)
- Da `FileMetadata.id` sich nicht aendert (nur `path` und `owner_id`), bleibt Versionshistorie intakt
- `user_id` auf Versionen ist historisch (wer hat diese Version erstellt) und aendert sich NICHT

### 5.6 Home-Verzeichnis selbst
- Darf NICHT transferiert werden — wuerde User-Isolation brechen
- **Guard**: Transfer ablehnen wenn Pfad exakt `<username>` ist (Top-Level User-Dir)

### 5.7 Admin als Transfer-Ziel
- Admins haben standardmaessig kein Home-Dir (`users.py` line 223)
- **Empfehlung**: Home-Dir fuer Admin on-demand erstellen, oder Admin-Transfer ablehnen wenn kein Home-Dir existiert

### 5.8 Quota-Implikationen
- Aktuell globale Quota (kein Per-User), kein Impact
- Bei kuenftiger Per-User Quota: Ziel-User Quota pruefen vor Transfer

### 5.9 User-Loeschung
- Aktuell: `shutil.rmtree()` + Cascade-Delete — aggressiv
- **Ueberlegung**: Bei User-Loeschung Dateien erst zu Admin transferieren statt loeschen (separates Feature)

---

## 6. Security-Checkliste

| Anforderung | Umsetzung |
|---|---|
| Auth Dependency | `Depends(deps.get_current_user)` |
| Rate Limiting | `@limiter.limit(get_limit("file_write"))` |
| Pydantic Schema | `OwnershipTransferRequest` |
| Audit Logging | `get_audit_logger_db().log_file_action(action="ownership_transfer")` |
| Path Traversal | `_jail_path()` vor jeder Operation |
| `..` Rejection | Via `_jail_path()` |
| Ownership Check | `ensure_owner_or_privileged()` vor Transfer |
| Kein `shell=True` | `pathlib` / `os.rename()` |
| Kein Raw SQL | ORM-Queries |
| Response Scoping | Nur Pfad/Count-Info, keine sensitiven Daten |

**Zusaetzliche Concerns**:
1. **TOCTOU**: PostgreSQL Advisory Locks (`pg_advisory_xact_lock(hash)`) fuer Multi-Worker
2. **Privilege Escalation**: `ensure_owner_or_privileged` verhindert unberechtigte Transfers
3. **Self-Transfer Loop**: Ablehnen wenn `new_owner_id == current_owner_id`
4. **DoS via Mass-Transfer**: Rate-Limiting, ggf. async Processing fuer grosse Verzeichnisse

---

## 7. Bestehenden Code Refactoren

### `PUT /api/files/permissions` bereinigen
- `owner_id` aus `FilePermissionsRequest` entfernen
- ODER Ownership-Aenderungen ueber den neuen `transfer_ownership()`-Service leiten
- **Wichtig**: Zwei Code-Pfade fuer Ownership-Aenderung mit unterschiedlichem Verhalten vermeiden

---

## 8. Implementierungs-Reihenfolge

### Phase 1: Core Backend Service
- [ ] `backend/app/services/files/ownership.py` mit `transfer_ownership()` + Hilfsfunktionen
- [ ] Pydantic Schemas in `backend/app/schemas/files.py`
- [ ] Unit Tests

### Phase 2: API-Endpoint
- [ ] `POST /api/files/transfer-ownership` in `backend/app/api/routes/files.py`
- [ ] Security Checks (Auth, Rate-Limit, Audit, jail_path)
- [ ] Integration Tests

### Phase 3: Residency Enforcement
- [ ] `enforce_residency()` im Ownership Service
- [ ] `POST /api/files/enforce-residency` Admin-Endpoint
- [ ] Tests

### Phase 4: Share/Link Cascade
- [ ] `_handle_shares_on_transfer()` implementieren
- [ ] FileShare und ShareLink Ownership-Updates testen
- [ ] Expired/Revoked Shares aufraeumen

### Phase 5: Concurrency Safety
- [ ] PostgreSQL Advisory Lock Wrapper
- [ ] Active-Upload Check (Transfer ablehnen bei laufendem Upload)
- [ ] Concurrent Access Tests

### Phase 6: Frontend — Transfer Modal
- [ ] `OwnershipTransferModal.tsx`
- [ ] API-Client Funktionen
- [ ] "Ownership uebertragen"-Button im FileManager
- [ ] Confirmation + Dry-Run Preview UI

### Phase 7: Frontend — Admin Residency Panel
- [ ] Residency-Enforcement UI im Admin-Bereich
- [ ] Violations-Liste mit Fix/Preview Aktionen

### Phase 8: DB-Migration
- [ ] Composite Index `(parent_path, owner_id)` auf `file_metadata`

### Phase 9: Bestehenden Code Refactoren
- [ ] `PUT /api/files/permissions` — `owner_id` entfernen oder ueber neuen Service leiten

### Phase 10: Benachrichtigungen
- [ ] Notification an neuen Owner bei Transfer
- [ ] Notification an alten Owner als Bestaetigung
