# Layout-Dekomposition + Layout-Route (F2, #301)

**Datum:** 2026-07-18
**Issue:** #301 ([F2] Komponenten über 500 Zeilen) — letzter verbleibender Kandidat
**Betroffen:** `client/src/components/Layout.tsx` (585 Zeilen), `client/src/App.tsx`

## Ziel

1. `Layout.tsx` nach dem etablierten F2-Muster in fokussierte Einheiten zerlegen
   (Orchestrator < 500 Zeilen, Ziel ~120).
2. Die ~18-fache Einzel-Wrappung `<Layout>…</Layout>` in `App.tsx` durch **eine**
   Layout-Route (react-router v7, `<Outlet/>`) ersetzen, sodass Layout über
   Navigationen hinweg gemountet bleibt.
3. Die bisher **nicht vorhandene** Testabdeckung für Layout mitziehen:
   Charakterisierungs-Tests vor dem Umbau, Unit-Tests pro Extraktion,
   Routing-Tests für die neue Mount-Semantik.

Nicht-Ziel: visuelle Änderungen. Alle Tailwind-Klassen werden verbatim übernommen.

## Ist-Zustand (Kurzfassung)

- `Layout.tsx`: 585 Zeilen, Default-Export, einziges Prop `children`.
- Einziger Importeur: `App.tsx`, dort pro Route einzeln gewickelt
  (`App.tsx:184–224`) → Layout wird bei jedem Routenwechsel neu gemountet
  (StatusBar-Fetch pro Navigation, Sidebar-Scroll geht verloren).
- Inhalt: 11 SVG-Icons auf Modulebene + 5 weitere **im Render-Body** (werden pro
  Render neu erzeugt); `navItems` (16 Einträge, i18n, `adminOnly`); Pi-Mode-,
  Admin- und Plugin-Filterung; Desktop- und Mobile-Sidebar mit nahezu
  identisch dupliziertem Nav-Rendering; Shutdown/Restart-Overlay + ~60 Zeilen
  Handler-Logik (Restart-Polling via `localApi.isAvailable()` alle 2 s,
  60 s-Timeout); Header mit `TopbarStatusStrip`, `NotificationCenter`,
  `UserMenu`, `PowerMenu` bzw. Pi-Logout.
- Sonderfälle: `/admin-db` → `max-w-none` statt `max-w-7xl`;
  Impersonation-Offsets (`top-10`, `h-[calc(100vh-2.5rem)]`, `mt-[112px]`) an
  drei Stellen; Pi-Mode ändert Logo/Brand, versteckt Notifications/UploadBar,
  ersetzt PowerMenu durch Logout-Button; UploadBar-Gate via
  `getStatusBarState().show_bottom_upload`.
- Abhängigkeiten: `AuthContext` (`user`, `logout`, `isAdmin`,
  `isImpersonating`), `PluginContext` (`pluginNavItems`), `VersionContext`,
  `isPi` (`lib/features`), `localApi`, `getStatusBarState`, i18n-Namespace
  `common`, Build-Globals `__BUILD_TYPE__`/`__GIT_COMMIT__`.
- Testabdeckung: **null** — kein Test referenziert Layout.

## Architektur (Variante A, beschlossen)

### Neue Einheiten

Unter `client/src/components/layout/` (+ Hooks in `client/src/hooks/`):

| Einheit | Verantwortung | Interface |
|---|---|---|
| `layoutNavConfig.tsx` | Alle 16 Icons (auch die 5 bisherigen Body-Icons → Modulebene) + `buildNavItems(t)`-Factory + `NavItem`-Typ | pure, keine Hooks |
| `hooks/useLayoutNav.ts` | Filterung: Pi-Mode (`piNavPaths`: `/`, `/system`), Admin-Filter, Plugin-Items via `resolvePluginString`, `adminStartIndex` | `{ allNavItems, adminStartIndex }` |
| `SidebarNav.tsx` | Die eine gemeinsame Nav-Liste (ersetzt Desktop/Mobile-Duplikat) inkl. Admin-Trenner, `AdminBadge`/`PluginBadge`, Active-State | `{ items, adminStartIndex, onNavigate? }` |
| `SidebarBrand.tsx` | Logo bzw. BaluPi-„BP"-Kreis + Brand-Text + Version (+ `__BUILD_TYPE__`-Commit-Suffix) + `DeveloperBadge` (heute 3× kopiert) | `{ size }` |
| `DesktopSidebar.tsx` | Fester Rahmen links, Impersonation-Offset | Props, keine eigenen Fetches |
| `MobileSidebar.tsx` | Overlay + Slide-in, Close-Button, User-Card unten; schließt bei Nav-Klick **und** bei `location.pathname`-Wechsel (neu nötig, s. Verhaltensdeltas) | `{ open, onClose, … }` |
| `LayoutHeader.tsx` | Hamburger, Mobile-Brand, `TopbarStatusStrip` (Desktop, nicht-Pi), `NotificationCenter` (nicht-Pi), `UserMenu`, `PowerMenu` bzw. Pi-Logout | `{ onOpenMobileMenu, onShutdown, onRestart, … }` |
| `PendingPowerOverlay.tsx` | Shutdown/Restart-Spinner-Overlay | `{ action, message }` |
| `hooks/usePowerActions.ts` | Shutdown/Restart-Handler inkl. Restart-Polling (2 s-Intervall, 60 s-Timeout) und ETA-Handling. **Fix im Zuge der Extraktion:** Der Ist-Code (Layout.tsx:579–594) räumt Intervall/Timeouts bei Unmount nicht auf (setState nach Unmount, `reload()` feuert nach Unmount trotzdem) — der Hook bekommt explizites Cleanup; Fake-Timer-Tests decken es ab | `{ pendingAction, pendingMessage, onShutdown, onRestart }` |
| `Layout.tsx` | Bleibt am selben Pfad; dünner Orchestrator (~120 Zeilen); **behält `{ children }`** | nach außen unverändert |

Barrel `components/layout/index.ts` analog zu den anderen F2-Verzeichnissen.

Erhalten bleiben explizit: `/admin-db`-Breiten-Sonderfall (im Orchestrator),
Impersonation-Offsets (in den jeweiligen Komponenten), UploadBar-Gate
(Effect im Orchestrator).

### Routing-Änderung (App.tsx)

Eine Eltern-Route ersetzt die Einzel-Wrappings:

```tsx
<Route element={user ? <AppLayout /> : <Navigate to="/login" replace />}>
  <Route path="/" element={PiDashboard ? <PiDashboard/> : <Dashboard/>} />
  <Route path="/users" element={isAdmin ? <UserManagement/> : <Navigate to="/"/>} />
  {/* … alle Seiten-Routen als Kinder … */}
</Route>
```

- `AppLayout` = `<Layout><Suspense fallback={<LoadingFallback/>}><Outlet/></Suspense></Layout>`.
  Der innere Suspense hält die Sidebar sichtbar, während ein Seiten-Chunk lädt.
- Admin-Guards bleiben pro Route (`isAdmin ? … : <Navigate to="/"/>`).
- Redirect-Only-Routen (`/raid`, `/health`, `/docs`, `/settings/notifications`, …)
  bleiben außerhalb der Layout-Route.
- `/login` bleibt außerhalb.

### Bewusste Verhaltensdeltas (gewollt, dokumentiert)

1. Layout persistiert über Navigationen → Sidebar-Scrollposition bleibt
   erhalten; ein laufendes Shutdown/Restart-Overlay überlebt Routenwechsel.
2. **Kein** Delta beim UploadBar-Gate: Der `getStatusBarState`-Effect wird auf
   `location.pathname` gekeyt und refetcht damit — wie heute durch den Remount —
   bei jeder Navigation. Sonst würde `show_bottom_upload` nach einer
   Einstellungsänderung bis zum Full-Reload stale bleiben.
3. Ausgeloggt auf Admin-Route: bisher zwei Hops (`/users` → `/` → `/login`),
   neu direkt `/login`. Gleiches Endziel.
4. Mobile-Menü: bisher schloss der Remount es implizit; neu schließt es ein
   `useEffect` auf `location.pathname` (zusätzlich zum bestehenden
   Klick-Handler).
5. Offene Dropdowns (`NotificationCenter`, `UserMenu`) persistieren künftig
   über Navigationen — vorher schloss der Remount sie implizit. Akzeptiert;
   beide schließen weiterhin bei Klick außerhalb.

## Tests

Reihenfolge ist Teil des Designs:

1. **Charakterisierungs-Tests zuerst, gegen den Ist-Stand**
   (`__tests__/components/Layout.test.tsx`): Nav-Sichtbarkeit admin/user/Pi,
   Admin-Trenner, Plugin-Items, `/admin-db`-Breite, Impersonation-Offsets,
   Mobile-Menü öffnen/schließen, UploadBar-Gate. Diese Tests müssen nach dem
   Umbau **unverändert** grün bleiben (deshalb behält Layout `{ children }`).
   Mock-Strategie ist tragend dafür: schwere Kinder (`NotificationCenter`,
   `TopbarStatusStrip`, `UserMenu`, `PowerMenu`, `UploadProgressBar`) werden
   **per Modulpfad** gemockt — solche Mocks überleben den Refactor, weil sich
   nur der Importeur ändert, nicht der Modulspezifizierer.
2. **jsdom-Realität einplanen**: `lg:hidden` wirkt nicht — Desktop- und
   Mobile-Sidebar stehen beide im DOM, Nav-Labels existieren doppelt.
   Assertions über `getAllBy…` und Klassen (`-translate-x-full` vs.
   `translate-x-0`), nicht über Sichtbarkeit.
3. **Unit-Tests pro Extraktion**: `useLayoutNav` (Rollen/Pi/Plugin-Filter,
   `adminStartIndex`), `usePowerActions` (Fake-Timer: Shutdown-ETA,
   Restart-Poll Erfolg + 60 s-Timeout, Cleanup bei Unmount;
   `window.location.reload` stubben — jsdom implementiert es nicht),
   `SidebarNav`, `PendingPowerOverlay`, `LayoutHeader` (Pi vs. Standard).
4. **Routing-Tests** (App-Ebene, MemoryRouter): Navigation zwischen zwei Routen
   → Layout bleibt gemountet, belegt über Mount-Zähler in einem gemockten
   Layout-Kind (nicht über den `getStatusBarState`-Spy — der feuert wegen
   Delta Nr. 2 absichtlich pro Navigation); Admin-Guard-Redirects;
   ausgeloggt → `/login`.
5. Bekannte Fallen — **verifiziert entschärft**: `vite.config.ts` definiert
   `__BUILD_TYPE__`/`__GIT_COMMIT__` (gilt auch für Vitest), und
   `tsconfig.test.json` inkludiert `src/vite-env.d.ts` bereits.
   `isPi` als Modul-Konstante per `vi.mock('…/lib/features')`.
6. Gates vor PR: `eslint .` (0 Errors), `npm run build` (tsc -b),
   `npx vitest run` (komplette Suite).

## PR-Aufbau

Ein PR (Branch `refactor/f2-layout-decomposition`), gestaffelte Commits:

1. Charakterisierungs-Tests gegen Ist-Layout
2. `layoutNavConfig` + `useLayoutNav` + Tests
3. `SidebarNav` + `SidebarBrand` + `DesktopSidebar` + `MobileSidebar` + Tests
4. `usePowerActions` + `PendingPowerOverlay` + `LayoutHeader` + Tests
5. `Layout.tsx` → Orchestrator (Charakterisierungs-Tests bleiben grün)
6. App.tsx-Layout-Route + `AppLayout` + Routing-Tests
7. CLAUDE.md-Sync (`components/CLAUDE.md`, `hooks/CLAUDE.md`) + ggf. Issue #301
   schließen (via PR-Beschreibung `Closes #301`, sofern danach keine
   Komponente > 500 Zeilen verbleibt)

## Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Kein Sicherheitsnetz vor dem Umbau | Charakterisierungs-Tests als erster Commit |
| UploadBar-Gate wird durch Persistenz stale | Effect auf `location.pathname` keyen (Delta Nr. 2) |
| Restart-Polling leakt bei Unmount (Ist-Bug) | Cleanup in `usePowerActions` + Fake-Timer-Test |
| Mobile-Menü bleibt nach Navigation offen | expliziter `useEffect` auf `pathname` + Routing-Test |
| Suspense-Fallback ersetzt ganze Seite inkl. Sidebar | innerer Suspense in `AppLayout` um `<Outlet/>` |
| Visuelle Regression durch Klassen-Umbau | Klassen verbatim kopieren; kein Redesign |
| Charakterisierungs-Tests brechen beim Umbau, obwohl Verhalten gleich | Kinder per Modulpfad mocken; Assertions jsdom-fest (getAllBy, Klassen) |
| Build-Globals brechen Tests/tsc -b | verifiziert: `vite.config.ts`-`define` + `vite-env.d.ts` in `tsconfig.test.json` bereits vorhanden |
