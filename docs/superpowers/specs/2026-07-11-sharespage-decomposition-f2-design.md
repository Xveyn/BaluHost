# SharesPage-Zerlegung (F2) + Tests — Design

> Stand: 2026-07-11. Basis `main` (nach #398). Adressiert Assessment-Finding **F2**
> (`SharesPage.tsx` = 898 Zeilen, zweitgrößte Nicht-Test-Komponente) und **T3**
> (`SharesPage` als ungetestete Security-Oberfläche). Folgt dem #301-Muster
> (`components/power/` komponiert extrahierte Subkomponenten).

## Ziel

`client/src/pages/SharesPage.tsx` von 898 Zeilen auf **< 250 Zeilen** reduzieren,
indem die drei Tab-Inhalte (~490 Zeilen, 55 % der Datei) und die wiederholten
Präsentationsbausteine in fokussierte, testbare Komponenten unter
`components/shares/` ausgelagert werden. Gleichzeitig die dabei entstehenden
Komponenten mit Vitest abdecken (breit, jede Komponente).

**Nicht** Ziel dieses PRs: Verhaltensänderung an der Sharing-Logik, neue Endpoints,
TanStack-Migration, visuelles Redesign.

## Ausgangslage (Struktur-Breakdown der aktuellen Datei)

| Block | Zeilen (ca.) |
|---|---|
| Imports + State (13× `useState`) | 1–50 |
| Cloud-Daten laden + Handler (`loadCloudExports`, revoke, retry, copy) | 52–125 |
| Präsentations-Helper (`getProviderLabel`, `getStatusBadge`, `formatDate`, `formatFileSize`) | 127–168 |
| Filter + 3× `useSortableTable` | 170–231 |
| Header + Stat-Cards + Tab-Bar + Such-/Filterleiste | 239–367 |
| Tab „My Shares" (Empty + Desktop-Table + Mobile-Cards) | 380–546 |
| Tab „Shared with me" (Empty + Desktop-Table + Mobile-Cards) | 549–681 |
| Tab „Cloud Exports" (Empty + Desktop-Table + Mobile-Cards) | 684–874 |
| Modals | 880–897 |

Auffällige Duplizierung über die drei Tabs:
- **File-Name-Zelle** (Folder/File-Icon + Name + Größe): 6× (je Tab desktop + mobile)
- **Permission-Badges** (read/write/delete): 4× (Shares + Shared, je desktop + mobile)
- **Empty-State** (Icon + Titel + Desc): 3×
- Desktop-Table ↔ Mobile-Card vollständig gespiegelt in jedem Tab

## Architektur / Dateilayout

```
hooks/useCloudExports.ts          # Cloud-Daten + revoke/retry — useState+useEffect (KEIN TanStack)
components/shares/
  index.ts                        # Barrel re-export
  sharesFormat.ts                 # formatDate, formatFileSize, getProviderLabel (pure)
  PermissionBadges.tsx            # read/write/delete Pills            (dedup 4×→1)
  FileNameCell.tsx                # Folder/File-Icon + Name + Größe     (dedup 6×→1)
  CloudStatusBadge.tsx            # Status-Pill (aus getStatusBadge)
  SharesToolbar.tsx               # Suche + Statusfilter + Create-Button
  SharesTabBar.tsx                # Tab-Umschalter (3 Tabs)
  SharesStatCards.tsx             # die 2 Stat-Card-Varianten (shares vs. cloud)
  MySharesTable.tsx               # My-Shares  Desktop + Mobile + Empty
  SharedWithMeTable.tsx           # Shared-with-me  Desktop + Mobile + Empty
  CloudExportsTable.tsx           # Cloud  Desktop + Mobile + Empty
__tests__/components/shares/      # Vitest, gespiegelte Struktur
```

## Datenfluss

`SharesPage.tsx` bleibt schlanker Orchestrator:

- **UI-State (bleibt in der Page):** `activeTab`, `searchQuery`, `statusFilter`,
  `showFilters`, `showCreateShareModal`, `editingShare`.
- **Daten:**
  - `useFileShares()` — existiert, unverändert (liefert `fileShares`, `sharedWithMe`, `statistics`, `loading`).
  - `useCloudExports()` — **neu**, kapselt `cloudExports`, `cloudStats`, `loading`,
    `reload()`, `revoke(jobId)`, `retry(jobId)`. Intern `useState` + `useEffect` +
    `Promise.all` wie bisher; die Handler toasten wie bisher und rufen `reload()`.
  - `users` — für das Create-Modal; bleibt als kleiner `useState`+`useEffect` in der
    Page (oder wandert optional mit in einen Hook — nicht erforderlich).
- **Filtern/Sortieren:** `filteredFileShares` / `filteredSharedWithMe` +
  die 3× `useSortableTable` bleiben in der Page. Die Tabellen erhalten **fertige,
  sortierte Arrays** plus die Sort-Header-Props (`sortKey`, `sortDirection`, `onSort`).
- **Tabellen sind reine Präsentation:** Daten rein, Callbacks rein
  (`onEdit`, `onDelete`, `onCopyLink`, `onRevoke`, `onRetry`). Kein eigener State,
  keine API-Aufrufe.

## Komponenten-Verträge (Kurzform)

| Komponente | Props (Kern) | Zweck |
|---|---|---|
| `sharesFormat.ts` | — | `formatDate(s\|null)`, `formatFileSize(bytes\|null)`, `getProviderLabel(job)` |
| `PermissionBadges` | `{ canRead, canWrite, canDelete, size?: 'sm'\|'md' }` | read/write/delete Pills |
| `FileNameCell` | `{ isDirectory, name, size?, folderLabel }` | Icon + Name + Größe/Ordner-Label |
| `CloudStatusBadge` | `{ job }` | Status-Pill inkl. Upload-Progress-% |
| `SharesToolbar` | `{ searchQuery, onSearch, statusFilter, onStatusFilter, showFilters, onToggleFilters, showCreateButton, onCreate }` | Such-/Filterleiste + Create |
| `SharesTabBar` | `{ activeTab, onChange }` | 3-Tab-Umschalter |
| `SharesStatCards` | `{ variant: 'shares'\|'cloud', statistics? , cloudStats? }` | 2 Stat-Card-Varianten |
| `MySharesTable` | `{ shares, allCount, sort props, onEdit, onDelete }` | Desktop-Table + Mobile-Cards + Empty |
| `SharedWithMeTable` | `{ items, allCount, sort props }` | Desktop-Table + Mobile-Cards + Empty |
| `CloudExportsTable` | `{ jobs, sort props, onCopyLink, onRevoke, onRetry }` | Desktop-Table + Mobile-Cards + Empty |

`allCount` (Gesamtzahl vor Filterung) wird benötigt, um die Empty-State-Botschaft
zu unterscheiden („keine Shares" vs. „keine Treffer für Filter").

## Empty-States

Wiederverwendung von **`ui/EmptyState`** (`{ icon, title, description?, action? }`).
Bewusst akzeptiert: minimale optische Normalisierung (System-Komponente nutzt
`gray-*` + Kreis-Hintergrund statt der bisherigen `slate-*` + `opacity-50`-Icons).
Gewinn: Dedup der 3 Kopien + Konsistenz mit dem restlichen UI.

## Tests (breit, jede Komponente)

- Ablage: `__tests__/components/shares/`, gespiegelte Struktur.
- **Konvention (Assessment T7): keine Assertions auf Tailwind-Klassen.** Stattdessen
  `getByRole` / `getByText` / `getByTitle` / optional `data-testid`.
- Abdeckung:
  - `PermissionBadges`: jede Kombination read/write/delete (an/aus).
  - `FileNameCell`: Folder vs. File, Größen-/Ordner-Label.
  - `CloudStatusBadge`: alle Status (`ready`, `uploading` inkl. %-Berechnung,
    `creating_link`, `pending`, `failed`, `revoked`, default).
  - `sharesFormat`: `never`-Fallback, Byte-Formatierung, Provider-Erkennung
    (Google Drive / OneDrive / Cloud).
  - `MySharesTable` / `SharedWithMeTable` / `CloudExportsTable`: Empty-State-Rendering,
    Zeilen-Rendering, **Action-Sichtbarkeit** (Cloud: Copy nur mit `share_link`,
    Revoke nur bei `status === 'ready'`, Retry nur bei `status === 'failed'`; Shares:
    Edit + Delete immer) + Callback-Auslösung via `user-event`/`fireEvent`.

## Nicht-Ziele (bewusst ausgeschlossen)

- **Kein TanStack** für Cloud-Exports: selten-ändernde, nutzer-getriggerte Daten
  (revoke/retry), kein Polling-Kandidat wie Telemetrie/CPU/RAM. Bleibt
  `useState`+`useEffect`. (Auch nicht als Folge-PR vorgesehen.)
- Keine Änderung an Sharing-/Backend-Logik, keine neuen Endpoints.
- Kein visuelles Redesign außer der EmptyState-Normalisierung.
- `useSortableTable`-Verdrahtung unverändert.
- Kein Umzug der Share-Modals (`CreateFileShareModal`, `EditFileShareModal`) — bleiben
  wie sie sind, nur aus der schlankeren Page heraus gerendert.

## Verifikation

- `SharesPage.tsx` < 250 Zeilen; keine Datei in `components/shares/` > ~200 Zeilen.
- `npx vitest run` grün (neue Tests + Bestand).
- `eslint .` 0 Fehler, `npm run build` (tsc -b) grün.
- Manuelle Sichtprüfung der drei Tabs (Desktop + Mobile-Breakpoint) inkl.
  Filter/Suche, Create/Edit/Revoke-Share, Cloud Copy/Revoke/Retry.
- Pages-/Components-CLAUDE.md um den neuen `shares/`-Eintrag ergänzen (analog `power/`).
