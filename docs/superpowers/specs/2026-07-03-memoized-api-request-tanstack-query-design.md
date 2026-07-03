# Design: `memoizedApiRequest` ablösen → TanStack Query

**Datum:** 2026-07-03
**Issue:** #299 (F1, Bullet „memoizedApiRequest ablösen") — schließt #309 (F6)
**Vorgänger:** #364 (Fundament), #365 (Telemetry), #366 (Dashboard-Caches/Persister)

---

## 1. Ziel & Scope

Der In-Memory-`Map`-Cache (`apiCache` + `memoizedApiRequest`) in `client/src/lib/api.ts:82-97`
ist einer der drei konkurrierenden Cache-Ansätze aus Finding F1. Er wird **ersatzlos
entfernt**; seine drei echten Konsumenten werden auf TanStack Query migriert (idiomatisch:
`useQuery` für Reads, `useMutation` + `invalidateQueries` für Writes).

Damit ist F6/#309 **vollständig** erledigt:
- Der Map-Cache-ohne-Invalidierung fällt weg (diese PR).
- Das `Dashboard.tsx`-`sessionStorage`-Parsing-pro-Render wurde bereits durch **#366**
  entfernt (Dashboard nutzt jetzt `useSystemTelemetry`/`useRaidStatus`, verifiziert).

**Bewusst NICHT in Scope** (bleibt der späteren „restliche Daten-Hooks bereichsweise"-PR):
- Cloud-Export-Reads in `SharesPage` (eigene Domain `cloud-export.ts`, nie memoized).
- Sonstige nicht-memoized `useState`/`useEffect`-Fetches.

---

## 2. Ist-Zustand (vollständige Oberfläche)

**Der Cache** (`lib/api.ts:82-97`): `apiCache = new Map<string, {data, expires}>()`,
`memoizedApiRequest(url, params?, ttl=60s)`, **keine Invalidierung außer TTL**.

**4 Producer-Funktionen:**

| Funktion | Endpoint | Konsument | Status |
|----------|----------|-----------|--------|
| `listBackups()` `backup.ts:66` | `GET /api/backups/` | `BackupSettings.tsx:39` (useEffect, 1×/Mount) | invalidiert via `apiCache.clear()` |
| `getBackup(id)` `backup.ts:74` | `GET /api/backups/{id}/` | **niemand** | **toter Code** |
| `getFilePermissions(path)` `files.ts:31` | `GET /api/files/permissions` | `FileManager.tsx:570` (Click-Handler, on-demand) | TTL → potenziell veraltete Rechte |
| `listFileShares()` `shares.ts:99` | `GET /api/shares/user-shares` | `SharesPage.tsx:72` (in `loadData` Promise.all) | invalidiert via `apiCache.delete()` |

**2 Invalidierungs-Muster:**
- `shares.ts:93/117/123` → `apiCache.delete(SHARES_CACHE_KEY)` nach create/update/delete.
- `BackupSettings.tsx:65/82` → `apiCache.clear()` — **löscht den gesamten Cache** (globaler
  Holzhammer, nicht nur Backups).

**Etablierte Konventionen (aus #364/#365/#366):**
- `lib/queryClient.ts`: App-weiter `QueryClient` (`staleTime 0`, `retry 1`,
  `refetchOnWindowFocus false`, `gcTime 24h`).
- `lib/queryPersister.ts`: spiegelt den **gesamten** Query-Cache nach `sessionStorage`
  (`baluhost-query-cache`, 24h `maxAge`, `API_VERSION` buster).
- `lib/queryKeys.ts`: zentrale Key-Factory `queryKeys.<domain>.<entity>()`.
- Referenz-Read-Hook: `hooks/useRaidStatus.ts` (`useQuery`, Rückgabe
  `{ data, loading, error, refetch }`).
- **`useMutation` existiert im Frontend noch NICHT** — diese PR etabliert es erstmalig.

---

## 3. Architektur der Änderung

### 3.1 `lib/queryKeys.ts` — neue Domains

```ts
backups: {
  list: () => ['backups', 'list'] as const,
},
shares: {
  all:          () => ['shares'] as const,   // Prefix für domain-weite Invalidierung
  userShares:   () => ['shares', 'user-shares'] as const,
  sharedWithMe: () => ['shares', 'shared-with-me'] as const,
  statistics:   () => ['shares', 'statistics'] as const,
},
```

Keine `files`-Domain: File-Permissions bleiben ein imperativer Plain-Read ohne
Query-Beteiligung (siehe §3.5).

### 3.2 `lib/api.ts` — Cleanup

`CacheEntry`, `apiCache`, `DEFAULT_TTL`, `memoizedApiRequest` **löschen**. Rest unverändert
(`apiClient`, Interceptors, `buildApiUrl`, `extractErrorMessage`, `fireAuthExpired`).

### 3.3 Backups-Domain

**`api/backup.ts`:**
- `listBackups()` → plain `apiClient.get('/api/backups/')`.
- `getBackup(id)` → **löschen** (toter Code).

**Neuer Hook `hooks/useBackups.ts`** (Muster: `useRaidStatus`):
```ts
export function useBackups() {
  const query = useQuery({
    queryKey: queryKeys.backups.list(),
    queryFn: listBackups,   // kein refetchInterval — Admin-Daten, manueller Refresh
  });
  return { backups: query.data?.backups ?? [], loading: query.isLoading,
           error: query.isError ? getApiErrorMessage(query.error, ...) : null,
           refetch: query.refetch };
}
```

**`BackupSettings.tsx`** (Mutations-Muster **1 — `useMutation`**):
- `useState<Backup[]>` + `useEffect(loadBackups)` → `useBackups()`.
- `totalSizeBytes` aus `backups` ableiten (`useMemo` oder inline reduce).
- `createBackup`/`deleteBackup` → je ein `useMutation` mit
  `onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.backups.list() })`
  und `onError` → `setError(getApiErrorMessage(...))`.
- Lokale Booleans `creating`/`deleting` → `mutation.isPending`.
- `apiCache.clear()`-Zeilen + der `apiCache`-Import **entfernen**.
- `restoreBackup` bleibt plain Call (lädt via `window.location.reload()` die Seite neu →
  keine Query-Invalidierung nötig). `restoring`-Boolean darf bleiben oder ebenfalls
  `useMutation.isPending` werden (Implementierungsdetail).

### 3.4 Shares-Domain (SharesPage — **Breite A: 3 Reads**)

**`api/shares.ts`:**
- `listFileShares()` → plain `apiClient.get('/api/shares/user-shares')`.
- `SHARES_CACHE_KEY` + alle `apiCache.delete(...)`-Zeilen (create/update/delete) + der
  `apiCache`/`memoizedApiRequest`-Import **entfernen**.

**Neuer Hook `hooks/useFileShares.ts`** (3× `useQuery`):
```ts
export function useFileShares() {
  const userShares   = useQuery({ queryKey: queryKeys.shares.userShares(),   queryFn: listFileShares });
  const sharedWithMe = useQuery({ queryKey: queryKeys.shares.sharedWithMe(), queryFn: listFilesSharedWithMe });
  const statistics   = useQuery({ queryKey: queryKeys.shares.statistics(),   queryFn: getShareStatistics });
  return {
    fileShares:   userShares.data ?? [],
    sharedWithMe: sharedWithMe.data ?? [],
    statistics:   statistics.data ?? null,
    loading: userShares.isLoading || sharedWithMe.isLoading || statistics.isLoading,
    // SharesPage schluckt Ladefehler heute (Empty-State); erster fehlgeschlagener
    // Query liefert die Message für optionale Anzeige:
    error: [userShares, sharedWithMe, statistics].find(q => q.isError)?.error ?? null,
    refetch: () => Promise.all([userShares.refetch(), sharedWithMe.refetch(), statistics.refetch()]),
  };
}
```

**Invalidierung lebt in den Modals (zentrale Semantik erhalten):** Der alte
`apiCache.delete(SHARES_CACHE_KEY)` saß *in* `createFileShare`/`updateFileShare`/
`deleteFileShare` — damit invalidierte **jede** Mutation-Site automatisch, egal wo gemountet.
Wichtig, denn es gibt eine Mutation-Site **außerhalb** der SharesPage: `ShareFileModal`
(gemountet in `FileManager.tsx:900`) ruft ebenfalls `createFileShare`. Diese zentrale
Semantik bleibt erhalten, indem die Invalidierung in die Modals wandert:
- `CreateFileShareModal`, `EditFileShareModal`, `ShareFileModal` rufen nach erfolgreicher
  Mutation selbst `queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() })`
  (Prefix `['shares']` → alle 3 Reads).
- Die `onSuccess`-Parent-Callbacks bleiben rein UI (Modal schließen, Toast) — das bisherige
  `loadData()` darin entfällt für die Shares-Hälfte.

**`SharesPage.tsx`:**
- Die 3 Shares-Reads aus `loadData()` entfernen → `useFileShares()`.
- **Cloud-Exports bleiben** (`listCloudExports`/`getCloudExportStatistics`) — in eine kleine
  `loadCloudExports()`-Funktion + eigenen `useEffect` extrahieren (eigener `'cloud-exports'`-Tab,
  eigenes lokales Loading). Nicht Teil dieser PR.
- `deleteFileShare` → `useMutation` mit `onSuccess: invalidateQueries(shares.all)`
  (Löschen ändert userShares **und** statistics; Prefix-Invalidierung ist simpler und korrekt).

### 3.5 File-Permissions (FileManager — plain Call, KEINE Query-Beteiligung)

`getFilePermissions` läuft **on-demand im Click-Handler** (`handleEditPermissionsClick`,
`FileManager.tsx:570`), ist also keine Render-Query — und auch `fetchQuery` wäre hier
**überengineert**:
- Der app-weite `gcTime` von 24h (Persister-Anforderung) würde user-scoped Rechte-Daten
  **pro je geöffnetem Datei-Pfad** 24h in den sessionStorage-Persister spiegeln — Bloat
  ohne Nutzen.
- Der Dedup-Gewinn ist ~null (niemand öffnet denselben Permissions-Dialog mehrfach pro
  Minute mit Performance-Not).

**Entscheidung:** `api/files.ts` → `getFilePermissions(path)` wird plain
`apiClient.get('/api/files/permissions', { params: { path } })`; der Call-Site in
`FileManager.tsx` bleibt unverändert (`await getFilePermissions(file.path)`). Kein
Query-Cache, keine Invalidierung, keine `queryKeys.files`-Domain.

**Verhaltensänderung (gewollt):** Der Dialog zeigt jetzt **immer frische** Rechte. Der alte
TTL-Cache lieferte bis zu 60s veraltete Rechte — nach eigenem PUT *und* bei
Fremd-Änderungen. Beides ist damit behoben (die `fetchQuery`-Alternative mit
`staleTime 60s` hätte die Fremd-Änderungs-Staleness behalten).

### 3.6 ⚠️ Cache-Leerung bei JEDEM Identitätswechsel (der #299-Hinweis wird hier real)

`listFileShares` ist **user-scoped** (per `current_user`), und der globale Persister spiegelt
es nach `sessionStorage`. Heute leert **nur `logout()`** den Query-Cache
(`queryClient.clear(); void queryPersister.removeClient();`, `AuthContext.tsx:112-113`).
Sobald user-scoped Queries existieren, muss aber **jeder** Identitätswechsel leeren, sonst
sieht der neue User kurz die Daten des alten (Instant-Paint aus dem Persister!), bis der
Refetch greift — ein Korrektheits-/Sicherheitsproblem. Betroffen sind **fünf** Pfade, von
denen heute keiner leert:

1. `impersonate()` — nach erfolgreichem `apiImpersonateUser` + Token-Swap.
2. `endImpersonation()` — nach dem Restore auf den Origin-Token.
3. Impersonation-Zweig des `auth:expired`-Handlers (`AuthContext.tsx:158-174`) — swappt
   ebenfalls den Token.
4. **`login()`** (`AuthContext.tsx:96-100`) — deckt den Leak über den Ablauf-Pfad ab:
   Token läuft ab → `auth:expired` (Plain-Zweig) setzt nur `token/user = null`, Cache +
   Persister behalten die Daten → ein *anderer* User loggt sich auf demselben Tab ein →
   sähe ohne Leerung kurz die Shares des Vorgängers. `login()` ist der Single Choke Point
   für jede neue Session.
5. Plain-Zweig des `auth:expired`-Handlers (`AuthContext.tsx:175-178`) — Defense in Depth:
   räumt den Persister schon beim Sessionende auf, statt die Daten bis zum nächsten
   `login()` im sessionStorage liegen zu lassen.

**Fix in `AuthContext.tsx`:** die vorhandene Cache-Leerung in einen kleinen internen Helfer
ziehen …
```ts
const clearQueryCache = () => { queryClient.clear(); void queryPersister.removeClient(); };
```
… und in allen fünf Pfaden + `logout()` aufrufen (`logout()` = Refactor ohne
Verhaltensänderung). Reihenfolge bei den Swap-Pfaden: **erst Token swappen, dann leeren**,
damit die von `clear()` ausgelösten Refetches bereits den neuen Token tragen.

**Bekannter Trade-off (akzeptiert):** Bei `logout()` unmountet danach ohnehin alles Richtung
Login-Screen. Bei `impersonate()`/`endImpersonation()` bleibt die App gemountet —
`queryClient.clear()` reißt allen aktiven Queries (Monitoring-Polls etc.) die Daten weg →
kurzer app-weiter Loading-Flash beim Identitätswechsel. Korrektheit > Kosmetik; eine
selektive Invalidierung nur user-scoped Domains wäre fehleranfällig (jede neue user-scoped
Domain müsste registriert werden) und lohnt bei der Seltenheit von Impersonation nicht.

---

## 4. Tests

- **`__tests__/api/files.test.ts`:** `getFilePermissions`-Test auf
  `apiClient.get('/api/files/permissions', { params: { path } })` umstellen; `memoizedApiRequest`
  aus der `vi.mock('../../lib/api', …)`-Factory entfernen; `apiClient.get` zur Mock-Factory
  hinzufügen.
- **`__tests__/api/shares.test.ts`:** `apiCache.delete`-Assertions entfernen; die create/update/
  delete-Tests auf `apiClient.post/patch/delete` prüfen; `apiCache` aus der Mock-Factory raus.
- **`__tests__/api/plugins.scopeCatalog.test.ts:7`:** `memoizedApiRequest`-Leiche aus der
  Mock-Factory entfernen (harmlos, aber sauber).
- **Neu `__tests__/hooks/useBackups.test.ts`** + **`useFileShares.test.ts`** (Vorlage:
  `__tests__/hooks/useActivityFeed.test.ts`) — `QueryClientProvider`-Wrapper, gemockte
  api-Funktion, `loading`/`data`/`error` prüfen.
- **`__tests__/contexts/AuthContext.impersonation.test.tsx`** (existiert): Assertions
  ergänzen, dass `impersonate`/`endImpersonation` **und** `login()` den Query-Cache leeren
  (z. B. `queryClient.clear` gespäht wird) — deckt alle fünf §3.6-Pfade soweit testbar ab.

**Pre-PR-Gates** (aus Memory): `cd client; npx vitest run` (echte Suite),
`npx eslint .` (0-Error-Gate), `npm run build` (tsc -b über app/node/TEST).

---

## 5. Docs & Issue-Tracking

- **`lib/CLAUDE.md`:** `memoizedApiRequest`-Zeile in der Files-Tabelle + im „Key Patterns"-Block
  entfernen.
- **`api/CLAUDE.md`:** `memoizedApiRequest` aus „Base Client" + „Conventions" entfernen.
- **`hooks/CLAUDE.md`:** `useBackups`, `useFileShares` in die Data-Fetching-Tabelle aufnehmen;
  ggf. Hinweis auf das neue `useMutation`+`invalidateQueries`-Muster in „Conventions".
- **`contexts/CLAUDE.md`:** `logout()`/Impersonation-Zeile um „leert Query-Cache" ergänzen.
- **#299:** Checkbox „memoizedApiRequest ablösen" abhaken; Hinweis, dass die Impersonation-
  Absicherung nun umgesetzt ist.
- **#309:** schließen (beide F6-Hälften erledigt).

---

## 6. Blast-Radius & Risiken

**Berührte Dateien (Kern):** `lib/api.ts`, `lib/queryKeys.ts`, `api/backup.ts`, `api/shares.ts`,
`api/files.ts`, `hooks/useBackups.ts` (neu), `hooks/useFileShares.ts` (neu),
`components/BackupSettings.tsx`, `pages/SharesPage.tsx`,
`components/CreateFileShareModal.tsx` + `EditFileShareModal.tsx` + `ShareFileModal.tsx`
(Invalidierung nach Mutation, §3.4), `contexts/AuthContext.tsx` + 4 CLAUDE.md + 3–5 Tests.
`pages/FileManager.tsx` bleibt unberührt (nur `api/files.ts` intern geändert, §3.5).

**Risiken:**
- *Verlust des 60s-TTL-Dedup:* vernachlässigbar — alle Konsumenten laden 1×/Mount oder on-demand;
  bei `getFilePermissions` ist Frische sogar korrekter (§3.5).
- *Erstes `useMutation`:* neues Muster, muss beim Review sitzen — dafür ersetzt `isPending`/`onError`
  echten Boilerplate (nicht nur Zeremonie).
- *Persister spiegelt jetzt Backups/Shares:* gewollt (F5-Instant-Paint); dafür muss die
  Cache-Leerung bei **jedem** Identitätswechsel sitzen — §3.6 zählt alle fünf Pfade auf.
  Permissions landen bewusst NICHT im Persister (§3.5).
- *Loading-Flash bei Impersonation durch `queryClient.clear()`:* akzeptiert, siehe §3.6.
- *`BackupSettings` ist **zweimal** gemountet* — `BackupPage.tsx` (`/backups`) **und**
  `SystemControlPage.tsx:197` (Backup-Tab). Mit `useQuery` unproblematisch, sogar ein
  Vorteil: beide Mounts teilen den Query-Cache (Dedup statt Doppel-Fetch). Verifiziert:
  `listBackups` wird nur von `BackupSettings.tsx` aufgerufen.

---

## 7. Nordstern-Bezug

Entfernt Cache-Ansatz #3 von 3 (nach memoized-Map ← diese PR; sessionStorage ← #366).
Etabliert das `useMutation`-Muster für alle späteren mutation-lastigen Domain-PRs
(„restliche Daten-Hooks bereichsweise": users, schedulers, devices, …).
`useAsyncData.ts`-Aufräumen bleibt der finalen „Aufräumen"-PR vorbehalten.
