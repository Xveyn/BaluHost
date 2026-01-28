# Frontend Refactoring Plan - BaluHost

> **Status**: Production/Preproduction - Vorsichtiges, inkrementelles Vorgehen erforderlich
> **Erstellt**: 2026-01-27

---

## Executive Summary

**Gesamtbewertung: 6.5/10** - Solide Basis mit klaren Verbesserungsmöglichkeiten

| Bereich | Bewertung | Status |
|---------|-----------|--------|
| Struktur | 7/10 | Gut organisiert, aber inkonsistent |
| Code-Qualität | 7/10 | Sauberes TypeScript, aber Duplikation |
| API Layer | 7/10 | Feature-basiert, aber uneinheitlich |
| Testing | 2/10 | **Kritisch** - nur 1 Test für 95 Dateien |
| Wartbarkeit | 6/10 | Verbesserungsbedürftig |

---

## Identifizierte Probleme

### 🔴 Kritisch (Hohe Priorität)

#### 1. Fehlende Tests
- **Nur 1 Test** (`csv.test.ts`) für 95 TypeScript-Dateien
- Keine Component-Tests, keine Hook-Tests, keine E2E-Tests
- Playwright konfiguriert aber nicht genutzt

#### 2. Code-Duplikation in Modals
6 Modal-Komponenten mit identischer Struktur:
- `CreateShareLinkModal`, `EditShareLinkModal`
- `CreateFileShareModal`, `EditFileShareModal`
- `UploadProgressModal`, `VersionHistoryModal`

Dupliziert sind:
- Modal Header/Close Button Pattern
- Form Submission Pattern (`loading`, `try/finally`)
- Styling/Layout Struktur

#### 3. HTTP-Client Inkonsistenz
- **axios (apiClient)**: monitoring.ts, power.ts, fan-control.ts, backup.ts, shares.ts
- **fetch()**: raid.ts, smart.ts, devices.ts, logging.ts, sync-schedules.ts
- Token-Management in 5+ Dateien manuell dupliziert

### 🟡 Mittel (Sollte behoben werden)

#### 4. Unorganisierte Root-Components
17 Komponenten im Root vermischt:
- 5 Modals
- 2 Wizards (RaidSetupWizard, MockDiskWizard)
- 4 Settings (AppearanceSettings, BackupSettings, etc.)
- 3 Power-Widgets
- Sollten in Unterordner gruppiert werden

#### 5. Type-Duplikation
```typescript
// logging.ts
interface DiskIOSample { readMbps: number; writeMbps: number; }

// monitoring.ts
interface DiskIoSample { read_mbps: number; write_mbps: number; }
```
- Gleicher Typ, unterschiedliche Namen/Casing
- Keine zentrale Types-Definition

#### 6. Hook Polling-Logic Wiederholt
Identisches Pattern in allen Monitoring-Hooks:
```typescript
useEffect(() => {
  fetchData();
  const interval = setInterval(fetchData, pollInterval);
  return () => clearInterval(interval);
}, [...]);
```

### 🟢 Niedrig (Nice-to-have)

- Seiten-Naming inkonsistent (mit/ohne "Page" Suffix)
- Keine Path-Aliases (`@/components` statt `../../../`)
- `vcl/` fehlt index.ts
- Backup-Datei `SyncPrototype.tsx.backup` sollte entfernt werden
- Hardcodierte Refresh-Intervalle

---

## Stärken (Beibehalten)

✅ **Feature-basierte API-Organisation** - 15 Module klar nach Feature getrennt
✅ **Konsistente Hook-Naming** - Alle `use[Feature]` Pattern
✅ **Gute TypeScript-Nutzung** - 95%+ Type Coverage
✅ **Barrel-Exports** - Subdirectories haben index.ts
✅ **Moderne Stack** - React 18, Vite, Tailwind, Recharts

---

## Refactoring-Empfehlung

### Ist Refactoring sinnvoll?

**Ja, aber priorisiert:**

| Phase | Aufwand | Impact | Empfehlung |
|-------|---------|--------|------------|
| Testing hinzufügen | Hoch | Sehr hoch | ⭐ Priorität 1 |
| Modal-Abstraktion | Mittel | Hoch | ⭐ Priorität 2 |
| HTTP-Client vereinheitlichen | Mittel | Hoch | ⭐ Priorität 2 |
| Ordner-Struktur | Niedrig | Mittel | Kann warten |
| Path-Aliases | Niedrig | Niedrig | Optional |

### Vorgeschlagene Refactoring-Schritte

#### Phase 1: Grundlagen (Kritisch)
1. **Shared Modal-Komponente erstellen**
   - `<Modal>`, `<ModalHeader>`, `<ModalBody>`, `<ModalFooter>`
   - Reduziert ~300 Zeilen duplizierter Code

2. **HTTP-Client konsolidieren**
   - Alle `fetch()` durch `apiClient` ersetzen
   - Token-Handling zentralisieren
   - Error-Interceptor hinzufügen

3. **Zentrale Types erstellen**
   - `src/types/api.ts` für `ApiError`, `PaginatedResponse<T>`
   - Duplikate wie `DiskIOSample` konsolidieren

#### Phase 2: Struktur
4. **Components reorganisieren**
   ```
   components/
   ├── modals/          (alle Modal-Komponenten)
   ├── wizards/         (RaidSetupWizard, MockDiskWizard)
   ├── settings/        (alle *Settings.tsx)
   ├── widgets/         (Power*, Energy*)
   └── shared/          (Layout, AdminDataTable)
   ```

5. **Polling-Hook extrahieren**
   ```typescript
   usePolling<T>(fetchFn, interval, enabled)
   ```

#### Phase 3: Testing (Parallel zu Phase 1-2)
6. **Test-Infrastruktur**
   - Component-Tests mit Vitest + React Testing Library
   - Hook-Tests
   - E2E-Tests mit Playwright

---

## Risikobewertung

| Aktion | Risiko | Begründung |
|--------|--------|------------|
| Modal-Refactoring | Niedrig | Isolierte Änderungen |
| HTTP-Client Wechsel | Mittel | API-Response-Handling prüfen |
| Ordner-Umstrukturierung | Niedrig | Nur Import-Pfade ändern |
| Type-Konsolidierung | Niedrig-Mittel | Mögliche Breaking Changes |

---

## Fazit

Das Frontend hat eine **solide Grundstruktur**, leidet aber unter:
1. **Fehlender Test-Coverage** (kritisch für Production)
2. **Signifikanter Code-Duplikation** (Wartbarkeit)
3. **Inkonsistenter API-Layer** (fetch vs axios)

**Empfehlung**: Gezieltes Refactoring in Phasen, beginnend mit Modal-Abstraktion und HTTP-Client-Vereinheitlichung. Tests parallel aufbauen.

**Geschätzter Nutzen**:
- ~30% weniger duplizierter Code
- Bessere Wartbarkeit
- Einheitliches Error-Handling
- Grundlage für Production-Deployment

---

## Detaillierter Refactoring-Plan (Production-Safe)

### Phase 0: Vorbereitung (Keine Code-Änderungen)

#### 0.1 Plan-Verzeichnis erstellen
```
/home/sven/projects/BaluHost/plans/
├── README.md                    # Übersicht aller Pläne
├── frontend-refactoring.md      # Dieser Plan
├── completed/                   # Abgeschlossene Pläne
└── archive/                     # Ältere Pläne
```

#### 0.2 Bestehende Plan-Dateien identifizieren
Gefundene Pläne im Projekt:
- `PHASE1_ACTION_PLAN.md`
- `baludesk/FEATURE_PLAN.md`
- `baludesk/PRODUCTION_RELEASE_PLAN.md`
- `baludesk/INTEGRATION_TEST_PLAN.md`
- `docs/Mobile_App_Plan_1.md`
- `android-app/IMPLEMENTIERUNGS_PLAN.md`

---

### Phase 1: Shared Modal Komponente (Niedrigstes Risiko)

**Ziel**: Neue Komponente erstellen, ohne bestehenden Code zu ändern

#### Schritt 1.1: Modal-Basiskomponente erstellen
```
client/src/components/ui/
├── Modal.tsx           # Container mit Backdrop
├── ModalHeader.tsx     # Titel + Close Button
├── ModalBody.tsx       # Content wrapper
├── ModalFooter.tsx     # Action buttons
└── index.ts            # Barrel export
```

**Dateien zu erstellen**:
- `client/src/components/ui/Modal.tsx`
- `client/src/components/ui/ModalHeader.tsx`
- `client/src/components/ui/ModalBody.tsx`
- `client/src/components/ui/ModalFooter.tsx`
- `client/src/components/ui/index.ts`

#### Schritt 1.2: Eine Modal migrieren (Test)
- `CreateShareLinkModal.tsx` auf neue Komponente umstellen
- Testen
- Bei Erfolg: weitere Modals migrieren

#### Schritt 1.3: Verbleibende Modals migrieren
- `EditShareLinkModal.tsx`
- `CreateFileShareModal.tsx`
- `EditFileShareModal.tsx`
- `UploadProgressModal.tsx`
- `VersionHistoryModal.tsx`

**Verifikation**:
```bash
npm run dev   # Frontend starten
# Manuell alle Modals testen:
# - Share erstellen/bearbeiten
# - File Share erstellen/bearbeiten
# - Upload testen
```

---

### Phase 2: HTTP-Client Konsolidierung

**Ziel**: fetch() durch apiClient ersetzen

#### Schritt 2.1: apiClient Error-Interceptor hinzufügen
**Datei**: `client/src/lib/api.ts`

```typescript
// Hinzufügen: Zentrales Error-Handling
apiClient.interceptors.response.use(
  response => response,
  error => {
    const message = error.response?.data?.detail
      || error.response?.data?.message
      || error.message;
    // Optional: Toast notification
    return Promise.reject(new Error(message));
  }
);
```

#### Schritt 2.2: API-Module einzeln migrieren
Reihenfolge (nach Nutzungshäufigkeit):
1. `raid.ts` - fetch() → apiClient
2. `smart.ts` - fetch() → apiClient
3. `devices.ts` - fetch() → apiClient
4. `logging.ts` - fetch() → apiClient
5. `sync-schedules.ts` - fetch() → apiClient

**Für jede Datei**:
1. Import ändern: `import { apiClient } from '../lib/api'`
2. fetch() durch apiClient.get/post/put/delete ersetzen
3. getToken() Funktion entfernen (apiClient hat Interceptor)
4. Testen

#### Schritt 2.3: Token-Management aufräumen
- Duplizierte `getToken()` Funktionen entfernen
- Einheitlich über apiClient-Interceptor

**Verifikation**:
```bash
npm run dev
# Testen:
# - RAID-Seite laden
# - SMART-Daten anzeigen
# - Geräte-Liste laden
# - Logs abrufen
```

---

### Phase 3: Type-Konsolidierung

**Ziel**: Duplizierte Types zusammenführen

#### Schritt 3.1: Shared Types Datei erstellen
**Datei**: `client/src/types/api.ts`

```typescript
// Gemeinsame API-Types
export interface ApiError {
  detail: string;
  status: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

// Konsolidierte Domain-Types
export interface DiskIoSample {
  readMbps: number;
  writeMbps: number;
  timestamp: string;
}

export type PowerProfile = 'idle' | 'low' | 'medium' | 'surge';
```

#### Schritt 3.2: Types in API-Modulen importieren
- `logging.ts`: DiskIOSample → import from types/api
- `monitoring.ts`: DiskIoSample → import from types/api
- Re-export für Rückwärtskompatibilität

---

### Phase 4: Ordnerstruktur (Optional)

**Ziel**: Root-Components organisieren

#### Schritt 4.1: Unterordner erstellen
```
client/src/components/
├── ui/                 # Phase 1 (Modal)
├── modals/             # Alle Modal-Komponenten
├── wizards/            # RaidSetupWizard, MockDiskWizard
├── settings/           # *Settings.tsx Komponenten
├── widgets/            # Power*, Energy*
├── monitoring/         # (existiert bereits)
├── fan-control/        # (existiert bereits)
├── services/           # (existiert bereits)
├── RemoteServers/      # (existiert bereits)
└── vcl/                # (existiert bereits)
```

#### Schritt 4.2: Dateien verschieben
Für jede Datei:
1. In neuen Ordner verschieben
2. Import-Pfade aktualisieren
3. index.ts mit Exports erstellen
4. Testen

---

## Rollback-Strategie

Bei Problemen:
1. Git: `git checkout -- <datei>` für einzelne Dateien
2. Vollständig: `git reset --hard HEAD~1` (letzten Commit rückgängig)
3. Branching: Refactoring auf eigenem Branch durchführen

**Empfehlung**: Jede Phase als eigenen Commit/PR

---

## Verifikation nach jeder Phase

```bash
# Frontend Build testen
cd client && npm run build

# Type-Checking
npx tsc --noEmit

# Dev-Server starten
npm run dev

# Manuell kritische Flows testen:
# - Login/Logout
# - File-Manager Navigation
# - RAID-Status anzeigen
# - Share erstellen/bearbeiten
```

---

## Betroffene Dateien (Übersicht)

### Phase 1 (Modal)
**Neu erstellen**:
- `src/components/ui/Modal.tsx`
- `src/components/ui/ModalHeader.tsx`
- `src/components/ui/ModalBody.tsx`
- `src/components/ui/ModalFooter.tsx`
- `src/components/ui/index.ts`

**Zu ändern**:
- `src/components/CreateShareLinkModal.tsx`
- `src/components/EditShareLinkModal.tsx`
- `src/components/CreateFileShareModal.tsx`
- `src/components/EditFileShareModal.tsx`
- `src/components/UploadProgressModal.tsx`
- `src/components/vcl/VersionHistoryModal.tsx`

### Phase 2 (HTTP-Client)
**Zu ändern**:
- `src/lib/api.ts` (Error-Interceptor)
- `src/api/raid.ts`
- `src/api/smart.ts`
- `src/api/devices.ts`
- `src/api/logging.ts`
- `src/api/sync-schedules.ts`

### Phase 3 (Types)
**Neu erstellen**:
- `src/types/api.ts`

**Zu ändern**:
- `src/api/logging.ts`
- `src/api/monitoring.ts`
