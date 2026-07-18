# Layout Decomposition + Layout Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Layout.tsx` (585 Zeilen) nach dem F2-Muster in `components/layout/*` + Hooks zerlegen und die ~18-fache `<Layout>`-Wrappung in `App.tsx` durch eine Layout-Route (`<Outlet/>`) ersetzen — mit Charakterisierungs-Tests vor dem Umbau.

**Architecture:** Layout behält sein `{ children }`-Interface und wird dünner Orchestrator über `DesktopSidebar`/`MobileSidebar`/`LayoutHeader`/`PendingPowerOverlay` + `useLayoutNav`/`usePowerActions`. App.tsx bekommt eine pathless Eltern-Route mit `AppLayout` (= `<Layout><Suspense><Outlet/></Suspense></Layout>`). Spec: `docs/superpowers/specs/2026-07-18-layout-decomposition-design.md`.

**Tech Stack:** React 18, react-router-dom v7, Tailwind, Vitest 4 + Testing Library, i18next (`common`-Namespace).

## Global Constraints

- **Null visuelle Änderung:** Alle Tailwind-Klassenstrings werden **verbatim** aus dem Ist-`Layout.tsx` übernommen (Quell-Zeilennummern stehen an jedem Task). Kein Redesign, keine Klassen-"Aufräumarbeiten".
- `Layout.tsx` bleibt an seinem Pfad, Default-Export, Prop `{ children: ReactNode }` — die Task-1-Tests laufen nach Task 5 **unverändert**.
- Erhaltene Sonderfälle: `/admin-db` → `max-w-none` statt `max-w-7xl`; Impersonation-Offsets `top-10`/`h-[calc(100vh-2.5rem)]`/`mt-[112px]`; Pi-Mode (Brand "BaluPi", nur `/` + `/system`, kein NotificationCenter/UploadBar, Logout-Button statt PowerMenu).
- UploadBar-Gate-Effect wird auf `location.pathname` gekeyt (Spec-Delta Nr. 2) — **kein** Fetch-once-Verhalten einführen.
- Schwere Kinder in Tests **per Modulpfad** mocken (Mocks überleben den Refactor). jsdom: beide Sidebars sind im DOM (`lg:hidden` wirkt nicht) → `getAllBy…`/Klassen-Assertions.
- **`@testing-library/user-event` ist NICHT installiert** (in Task 1 festgestellt). Für Klicks `fireEvent` aus `@testing-library/react` verwenden — keine neue Dependency hinzufügen. Die Testcode-Blöcke unten, die noch `userEvent` zeigen, sind entsprechend zu übersetzen: `await user.click(el)` → `fireEvent.click(el)`, und Zustandswechsel, die von einem async Effect abhängen, vorher per `await waitFor(...)` abwarten (vermeidet `act()`-Warnungen).
- Gates vor dem PR: `npx eslint .` (0 Errors), `npm run build`, `npx vitest run` — alle aus `client/`.
- Commits auf Branch `refactor/f2-layout-decomposition` (existiert bereits, enthält den Spec). Commit-Messages enden mit `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Alle Pfade unten relativ zum Repo-Root `D:\Programme (x86)\Baluhost`. Testläufe: `cd client` vorausgesetzt.

---

### Task 1: Charakterisierungs-Tests für das Ist-Layout

**Files:**
- Create: `client/src/__tests__/components/Layout.test.tsx`
- Referenz (nur lesen): `client/src/components/Layout.tsx`

**Interfaces:**
- Consumes: Ist-`Layout.tsx` (Default-Export, `{ children }`).
- Produces: Die Testdatei, die nach Task 5 unverändert grün bleiben muss. Spätere Tasks dürfen sie NICHT editieren.

- [ ] **Step 1: Testdatei schreiben**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../../components/Layout';

// ---- Mutable Mock-Zustände (vor den vi.mock-Hoists) ----
const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'admin', role: 'admin' } as { id: number; username: string; role: string } | null,
  isAdmin: true,
  isImpersonating: false,
  logout: vi.fn(),
}));
const featureState = vi.hoisted(() => ({ isPi: false }));
const pluginState = vi.hoisted(() => ({ pluginNavItems: [] as Array<{ path: string; label: string; admin_only: boolean }> }));
const getStatusBarStateMock = vi.hoisted(() =>
  vi.fn(async () => ({ pills: [], show_bottom_upload: true })),
);

// ---- Kontext-Mocks ----
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => authState }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => pluginState }));
vi.mock('../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));
vi.mock('../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../lib/pluginI18n', () => ({
  resolvePluginString: (_t: unknown, _k: string, fallback: string) => fallback,
}));
vi.mock('../../api/statusBar', () => ({ getStatusBarState: getStatusBarStateMock }));
vi.mock('../../lib/localApi', () => ({
  localApi: { shutdown: vi.fn(), restart: vi.fn(), isAvailable: vi.fn() },
}));

// ---- Schwere Kinder per Modulpfad mocken (überleben den Refactor) ----
vi.mock('../../components/NotificationCenter', () => ({
  default: () => <div data-testid="notification-center" />,
}));
vi.mock('../../components/PowerMenu', () => ({
  default: () => <div data-testid="power-menu" />,
}));
vi.mock('../../components/UserMenu', () => ({
  default: () => <div data-testid="user-menu" />,
}));
vi.mock('../../components/UploadProgressBar', () => ({
  UploadProgressBar: () => <div data-testid="upload-progress-bar" />,
}));
vi.mock('../../components/topbar/TopbarStatusStrip', () => ({
  TopbarStatusStrip: () => <div data-testid="topbar-status-strip" />,
}));
vi.mock('../../components/ImpersonationBanner', () => ({ default: () => null }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string | Record<string, unknown>) =>
      typeof defaultValue === 'string' ? key : key,
  }),
}));

function renderLayout(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <div data-testid="page-content" />
      </Layout>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  authState.user = { id: 1, username: 'admin', role: 'admin' };
  authState.isAdmin = true;
  authState.isImpersonating = false;
  featureState.isPi = false;
  pluginState.pluginNavItems = [];
  getStatusBarStateMock.mockClear();
  getStatusBarStateMock.mockResolvedValue({ pills: [], show_bottom_upload: true });
});

describe('Layout (Charakterisierung)', () => {
  it('rendert children und beide Sidebars mit Brand', () => {
    renderLayout();
    expect(screen.getByTestId('page-content')).toBeInTheDocument();
    // Desktop-Sidebar + Mobile-Sidebar + Mobile-Header-Brand = 3x "BaluHost"
    expect(screen.getAllByText('BaluHost').length).toBeGreaterThanOrEqual(2);
  });

  it('Admin sieht Admin-Items und Admin-Trenner in beiden Sidebars', () => {
    renderLayout();
    expect(screen.getAllByText('navigation.users')).toHaveLength(2);
    expect(screen.getAllByText('navigation.updates')).toHaveLength(2);
    expect(screen.getAllByText('navigation.admin')).toHaveLength(2);
  });

  it('Nicht-Admin sieht weder Admin-Items noch Trenner', () => {
    authState.isAdmin = false;
    authState.user = { id: 2, username: 'user', role: 'user' };
    renderLayout();
    expect(screen.queryAllByText('navigation.users')).toHaveLength(0);
    expect(screen.queryAllByText('navigation.admin')).toHaveLength(0);
    expect(screen.getAllByText('navigation.dashboard')).toHaveLength(2);
  });

  it('Pi-Mode: nur Dashboard+System, Brand BaluPi, kein NotificationCenter, keine UploadBar', async () => {
    featureState.isPi = true;
    renderLayout();
    expect(screen.getAllByText('navigation.dashboard')).toHaveLength(2);
    expect(screen.getAllByText('navigation.system')).toHaveLength(2);
    expect(screen.queryAllByText('navigation.files')).toHaveLength(0);
    expect(screen.getAllByText('BaluPi').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByTestId('notification-center')).not.toBeInTheDocument();
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    expect(screen.queryByTestId('upload-progress-bar')).not.toBeInTheDocument();
  });

  it('Plugin-Nav-Items erscheinen; admin_only-Plugins sind für Nicht-Admins gefiltert', () => {
    pluginState.pluginNavItems = [
      { path: 'demo', label: 'DemoPlugin', admin_only: false },
      { path: 'secret', label: 'SecretPlugin', admin_only: true },
    ];
    authState.isAdmin = false;
    renderLayout();
    expect(screen.getAllByText('DemoPlugin')).toHaveLength(2);
    expect(screen.queryAllByText('SecretPlugin')).toHaveLength(0);
  });

  it('/admin-db bekommt volle Breite, andere Routen max-w-7xl', () => {
    const { container, unmount } = renderLayout('/admin-db');
    expect(container.querySelector('main > div')!.className).toContain('max-w-none');
    unmount();
    const { container: c2 } = renderLayout('/');
    expect(c2.querySelector('main > div')!.className).toContain('max-w-7xl');
  });

  it('Impersonation verschiebt Header und Main', () => {
    authState.isImpersonating = true;
    const { container, unmount } = renderLayout();
    expect(container.querySelector('header')!.className).toContain('top-10');
    expect(container.querySelector('main')!.className).toContain('mt-[112px]');
    unmount();
    authState.isImpersonating = false;
    const { container: c2 } = renderLayout();
    expect(c2.querySelector('header')!.className).toContain('top-0');
    expect(c2.querySelector('main')!.className).toContain('mt-[72px]');
  });

  it('Mobile-Menü öffnet per Hamburger und schließt per Overlay-Klick', async () => {
    const user = userEvent.setup();
    const { container } = renderLayout();
    const mobileAside = () =>
      Array.from(container.querySelectorAll('aside')).find((a) => a.className.includes('z-50'))!;
    expect(mobileAside().className).toContain('-translate-x-full');
    // Hamburger = erster Button im Header
    await user.click(container.querySelector('header button')!);
    expect(mobileAside().className).toContain('translate-x-0');
    // Overlay = fixed inset-0 z-40 div
    const overlay = container.querySelector('div.fixed.inset-0.z-40')!;
    await user.click(overlay);
    expect(mobileAside().className).toContain('-translate-x-full');
  });

  it('UploadBar-Gate: show_bottom_upload=false versteckt die Bar', async () => {
    getStatusBarStateMock.mockResolvedValue({ pills: [], show_bottom_upload: false });
    renderLayout();
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByTestId('upload-progress-bar')).not.toBeInTheDocument(),
    );
  });

  it('UploadBar-Gate: Fetch-Fehler lässt die Bar sichtbar (Default true)', async () => {
    getStatusBarStateMock.mockRejectedValue(new Error('boom'));
    renderLayout();
    await waitFor(() => expect(getStatusBarStateMock).toHaveBeenCalled());
    expect(screen.getByTestId('upload-progress-bar')).toBeInTheDocument();
  });

  it('Standard-Mode: PowerMenu, UserMenu, NotificationCenter, StatusStrip im Header', () => {
    renderLayout();
    expect(screen.getByTestId('power-menu')).toBeInTheDocument();
    expect(screen.getByTestId('user-menu')).toBeInTheDocument();
    expect(screen.getByTestId('notification-center')).toBeInTheDocument();
    expect(screen.getByTestId('topbar-status-strip')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — sie müssen gegen den IST-Stand grün sein**

Run: `cd client; npx vitest run src/__tests__/components/Layout.test.tsx`
Expected: alle Tests PASS. (Das ist Charakterisierung — rot heißt: Test falsch, nicht Code falsch. Assertions dann an den Ist-Stand anpassen, z. B. exakte Anzahl der Brand-Texte.)

- [ ] **Step 3: Commit**

```bash
git add client/src/__tests__/components/Layout.test.tsx
git commit -m "test(layout): characterization tests for current Layout behavior (#301)"
```

---

### Task 2: `layoutNavConfig` + `useLayoutNav` + Tests

**Files:**
- Create: `client/src/components/layout/layoutNavConfig.tsx`
- Create: `client/src/hooks/useLayoutNav.ts`
- Test: `client/src/__tests__/hooks/useLayoutNav.test.tsx`
- Quelle für Verbatim-Kopien: `client/src/components/Layout.tsx:36-116` (navIcon-Map) und `:138-175` (die 5 Body-Icons)

**Interfaces:**
- Produces:
  - `layoutNavConfig.tsx`: `export interface LayoutNavItem { path: string; label: string; description: string; icon: React.ReactNode; adminOnly?: boolean; isPlugin?: boolean }`; `export const navIcon: Record<string, JSX.Element>` (16 Keys: `dashboard, files, system, logging, users, raid, docs, shares, settings, sync, mobile, scheduler, database, updates, systemControl, devices`); `export const PI_NAV_PATHS: ReadonlySet<string>`; `export function buildNavItems(t: TFunction): LayoutNavItem[]`
  - `useLayoutNav.ts`: `export function useLayoutNav(): { allNavItems: LayoutNavItem[]; adminStartIndex: number }`

- [ ] **Step 1: Failing Test schreiben**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useLayoutNav } from '../../hooks/useLayoutNav';

const authState = vi.hoisted(() => ({ isAdmin: true }));
const featureState = vi.hoisted(() => ({ isPi: false }));
const pluginState = vi.hoisted(() => ({
  pluginNavItems: [] as Array<{ path: string; label: string; admin_only: boolean }>,
}));

vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => authState }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => pluginState }));
vi.mock('../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../lib/pluginI18n', () => ({
  resolvePluginString: (_t: unknown, _k: string, fallback: string) => fallback,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeEach(() => {
  authState.isAdmin = true;
  featureState.isPi = false;
  pluginState.pluginNavItems = [];
});

describe('useLayoutNav', () => {
  it('Admin: 16 Items, adminStartIndex zeigt aufs erste Admin-Item', () => {
    const { result } = renderHook(() => useLayoutNav());
    expect(result.current.allNavItems).toHaveLength(16);
    // 9 Nicht-Admin-Items vorweg: dashboard, files, shares, system, devices,
    // smart-devices, settings, manual, cloud-import
    expect(result.current.adminStartIndex).toBe(9);
    expect(result.current.allNavItems[9].path).toBe('/admin/system-control');
    expect(result.current.allNavItems[9].adminOnly).toBe(true);
  });

  it('User: nur die 9 Nicht-Admin-Items, adminStartIndex -1', () => {
    authState.isAdmin = false;
    const { result } = renderHook(() => useLayoutNav());
    expect(result.current.allNavItems).toHaveLength(9);
    expect(result.current.allNavItems.every((i) => !i.adminOnly)).toBe(true);
    expect(result.current.adminStartIndex).toBe(-1);
  });

  it('Pi: nur / und /system, keine Plugins, adminStartIndex -1', () => {
    featureState.isPi = true;
    pluginState.pluginNavItems = [{ path: 'x', label: 'X', admin_only: false }];
    const { result } = renderHook(() => useLayoutNav());
    expect(result.current.allNavItems.map((i) => i.path)).toEqual(['/', '/system']);
    expect(result.current.adminStartIndex).toBe(-1);
  });

  it('Plugin-Items werden angehängt; admin_only für User gefiltert', () => {
    authState.isAdmin = false;
    pluginState.pluginNavItems = [
      { path: 'demo', label: 'Demo', admin_only: false },
      { path: 'secret', label: 'Secret', admin_only: true },
    ];
    const { result } = renderHook(() => useLayoutNav());
    const last = result.current.allNavItems[result.current.allNavItems.length - 1];
    expect(last).toMatchObject({ path: '/plugins/demo', label: 'Demo', isPlugin: true });
    expect(result.current.allNavItems.some((i) => i.label === 'Secret')).toBe(false);
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss failen**

Run: `cd client; npx vitest run src/__tests__/hooks/useLayoutNav.test.tsx`
Expected: FAIL — `Cannot find module '../../hooks/useLayoutNav'`

- [ ] **Step 3: `layoutNavConfig.tsx` implementieren**

```tsx
import type { TFunction } from 'i18next';
import { Plug, CloudDownload, Shield, Zap } from 'lucide-react';

export interface LayoutNavItem {
  path: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
  isPlugin?: boolean;
}

// Pi mode: only show Dashboard + System
export const PI_NAV_PATHS: ReadonlySet<string> = new Set(['/', '/system']);

export const navIcon = {
  // dashboard, files, system, logging, users, raid, docs, shares, settings,
  // sync, mobile: VERBATIM aus Layout.tsx:36-116 übernehmen (identische Keys).
  // scheduler, database, updates, systemControl, devices: die 5 Icons aus dem
  // Komponenten-Body Layout.tsx:138-175 hierher verschieben (Konstanten-Suffix
  // "Icon" entfällt, sie werden Map-Einträge). Beispiel für die Ziel-Form:
  dashboard: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
      <rect x="3" y="3" width="8" height="8" rx="1.6" stroke="currentColor" />
      <rect x="13" y="3" width="8" height="5" rx="1.6" stroke="currentColor" />
      <rect x="13" y="10" width="8" height="11" rx="1.6" stroke="currentColor" />
      <rect x="3" y="13" width="8" height="8" rx="1.6" stroke="currentColor" />
    </svg>
  ),
  // ... (alle übrigen 15 verbatim; KEINE Pfad-Daten verändern)
} as const;

export function buildNavItems(t: TFunction): LayoutNavItem[] {
  return [
    { path: '/', label: t('navigation.dashboard'), description: t('navigation.dashboardDesc'), icon: navIcon.dashboard },
    { path: '/files', label: t('navigation.files'), description: t('navigation.filesDesc'), icon: navIcon.files },
    { path: '/shares', label: t('navigation.shares'), description: t('navigation.sharesDesc'), icon: navIcon.shares },
    { path: '/system', label: t('navigation.system'), description: t('navigation.systemDesc'), icon: navIcon.system },
    { path: '/devices', label: t('navigation.devices'), description: t('navigation.devicesDesc'), icon: navIcon.devices },
    { path: '/smart-devices', label: t('navigation.smartDevices', 'Smart Devices'), description: t('navigation.smartDevicesDesc', 'IoT device control'), icon: <Zap className="h-5 w-5" /> },
    { path: '/settings', label: t('navigation.settings'), description: t('navigation.settingsDesc'), icon: navIcon.settings },
    { path: '/manual', label: t('navigation.userManual'), description: t('navigation.userManualDesc'), icon: navIcon.docs },
    { path: '/cloud-import', label: t('navigation.cloudImport'), description: t('navigation.cloudImportDesc'), icon: <CloudDownload className="h-5 w-5" /> },
    { path: '/admin/system-control', label: t('navigation.systemControl'), description: t('navigation.systemControlDesc'), icon: navIcon.systemControl, adminOnly: true },
    { path: '/schedulers', label: t('navigation.scheduler'), description: t('navigation.schedulerDesc'), icon: navIcon.scheduler, adminOnly: true },
    { path: '/admin-db', label: t('navigation.database'), description: t('navigation.databaseDesc'), icon: navIcon.database, adminOnly: true },
    { path: '/users', label: t('navigation.users'), description: t('navigation.usersDesc'), icon: navIcon.users, adminOnly: true },
    { path: '/pihole', label: 'Pi-hole DNS', description: 'DNS Filtering', icon: <Shield className="h-5 w-5" />, adminOnly: true },
    { path: '/plugins', label: t('navigation.plugins'), description: t('navigation.pluginsDesc'), icon: <Plug className="h-5 w-5" />, adminOnly: true },
    { path: '/updates', label: t('navigation.updates'), description: t('navigation.updatesDesc'), icon: navIcon.updates, adminOnly: true },
  ];
}
```

(Reihenfolge und alle `t`-Keys exakt wie in `Layout.tsx:178-284` — nicht umsortieren, `Plug` wird zusätzlich in `useLayoutNav` für Plugin-Items gebraucht.)

- [ ] **Step 4: `useLayoutNav.ts` implementieren**

```tsx
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { usePlugins } from '../contexts/PluginContext';
import { isPi } from '../lib/features';
import { resolvePluginString } from '../lib/pluginI18n';
import { buildNavItems, PI_NAV_PATHS, pluginNavIcon, type LayoutNavItem } from '../components/layout/layoutNavConfig';

export function useLayoutNav(): { allNavItems: LayoutNavItem[]; adminStartIndex: number } {
  const { t } = useTranslation('common');
  const { isAdmin } = useAuth();
  const { pluginNavItems } = usePlugins();

  const navItems = buildNavItems(t);

  const pluginItems: LayoutNavItem[] = isPi ? [] : pluginNavItems
    .filter((item) => !item.admin_only || isAdmin)
    .map((item) => ({
      path: `/plugins/${item.path}`,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      label: resolvePluginString((item as any)._translations, `nav.${item.label}`, item.label),
      description: 'Plugin',
      icon: pluginNavIcon,
      adminOnly: item.admin_only,
      isPlugin: true,
    }));

  const filteredNavItems = navItems
    .filter((item) => (isPi ? PI_NAV_PATHS.has(item.path) : !item.adminOnly || isAdmin));

  const adminStartIndex = isPi ? -1 : filteredNavItems.findIndex((item) => item.adminOnly);

  return { allNavItems: [...filteredNavItems, ...pluginItems], adminStartIndex };
}
```

**Entschieden (Controller, Pre-Flight):** Das Repo hat **null** `.tsx`-Hooks — alle 66 Dateien in `client/src/hooks/` sind `.ts`. Damit `useLayoutNav.ts` dieser Konvention folgen kann, darf der Hook **kein JSX enthalten**. Deshalb wandert das Plugin-Icon als fertiges Element nach `layoutNavConfig.tsx`:

```tsx
// in layoutNavConfig.tsx, zusätzlich exportieren:
export const pluginNavIcon = <Plug className="h-5 w-5" />;
```

und `useLayoutNav.ts` importiert `pluginNavIcon` statt `Plug` und setzt `icon: pluginNavIcon`. Der Hook bleibt so JSX-frei und `.ts`.

- [ ] **Step 5: Test laufen lassen — muss passen**

Run: `cd client; npx vitest run src/__tests__/hooks/useLayoutNav.test.tsx`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add client/src/components/layout/layoutNavConfig.tsx client/src/hooks/useLayoutNav.* client/src/__tests__/hooks/useLayoutNav.test.tsx
git commit -m "feat(layout): extract layoutNavConfig + useLayoutNav hook (#301)"
```

---

### Task 3: `SidebarBrand` + `SidebarNav` + `DesktopSidebar` + `MobileSidebar` + Tests

**Files:**
- Create: `client/src/components/layout/SidebarBrand.tsx`
- Create: `client/src/components/layout/SidebarNav.tsx`
- Create: `client/src/components/layout/DesktopSidebar.tsx`
- Create: `client/src/components/layout/MobileSidebar.tsx`
- Test: `client/src/__tests__/components/layout/SidebarNav.test.tsx`
- Test: `client/src/__tests__/components/layout/MobileSidebar.test.tsx`
- Quelle für Verbatim-Klassen: `Layout.tsx:317-333` (Desktop-Rahmen+Brand), `:335-380` (Desktop-Nav), `:386-484` (Mobile), `:506-525` (Header-Brand kompakt)

**Interfaces:**
- Consumes: `LayoutNavItem` aus Task 2.
- Produces:
  - `SidebarBrand`: `({ variant }: { variant: 'desktop' | 'mobile' | 'compact' })` — nutzt intern `useFormattedVersion('')`, `isPi`, `__BUILD_TYPE__`/`__GIT_COMMIT__`, `DeveloperBadge` (nicht bei `compact`).
  - `SidebarNav`: `({ items, adminStartIndex, variant, onNavigate }: { items: LayoutNavItem[]; adminStartIndex: number; variant: 'desktop' | 'mobile'; onNavigate?: () => void })`
  - `DesktopSidebar`: `({ isImpersonating, items, adminStartIndex })`
  - `MobileSidebar`: `({ open, onClose, isImpersonating, items, adminStartIndex, username, isAdmin }: { open: boolean; onClose: () => void; isImpersonating: boolean; items: LayoutNavItem[]; adminStartIndex: number; username?: string; isAdmin: boolean })` — schließt zusätzlich bei `location.pathname`-Wechsel.

- [ ] **Step 1: Failing Tests schreiben**

`SidebarNav.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SidebarNav } from '../../../components/layout/SidebarNav';
import type { LayoutNavItem } from '../../../components/layout/layoutNavConfig';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const items: LayoutNavItem[] = [
  { path: '/', label: 'Dash', description: 'd', icon: <span /> },
  { path: '/files', label: 'Files', description: 'f', icon: <span /> },
  { path: '/users', label: 'Users', description: 'u', icon: <span />, adminOnly: true },
  { path: '/plugins/demo', label: 'Demo', description: 'Plugin', icon: <span />, isPlugin: true },
];

function renderNav(props: Partial<React.ComponentProps<typeof SidebarNav>> = {}, path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarNav items={items} adminStartIndex={2} variant="desktop" {...props} />
    </MemoryRouter>,
  );
}

describe('SidebarNav', () => {
  it('rendert alle Items als Links', () => {
    renderNav();
    expect(screen.getAllByRole('link')).toHaveLength(4);
  });

  it('zeigt den Admin-Trenner genau vor dem ersten Admin-Item', () => {
    renderNav();
    expect(screen.getAllByText('navigation.admin')).toHaveLength(1);
  });

  it('adminStartIndex -1 → kein Trenner', () => {
    renderNav({ adminStartIndex: -1 });
    expect(screen.queryByText('navigation.admin')).not.toBeInTheDocument();
  });

  it('aktiver Link bekommt die Active-Klassen', () => {
    renderNav({}, '/files');
    const active = screen.getByText('Files').closest('a')!;
    expect(active.className).toContain('border-sky-500');
  });

  it('onNavigate feuert bei Klick auf einen Link', () => {
    const onNavigate = vi.fn();
    renderNav({ onNavigate });
    fireEvent.click(screen.getByText('Files'));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
```

`MobileSidebar.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MobileSidebar } from '../../../components/layout/MobileSidebar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));

function renderSidebar(open: boolean, onClose = vi.fn()) {
  render(
    <MemoryRouter>
      <MobileSidebar
        open={open}
        onClose={onClose}
        isImpersonating={false}
        items={[{ path: '/', label: 'Dash', description: 'd', icon: <span /> }]}
        adminStartIndex={-1}
        username="alice"
        isAdmin={false}
      />
    </MemoryRouter>,
  );
  return onClose;
}

describe('MobileSidebar', () => {
  it('geschlossen: -translate-x-full, kein Overlay', () => {
    renderSidebar(false);
    expect(document.body.querySelector('aside')!.className).toContain('-translate-x-full');
    expect(document.body.querySelector('div.fixed.inset-0.z-40')).toBeNull();
  });

  it('offen: translate-x-0, Overlay-Klick ruft onClose', () => {
    const onClose = renderSidebar(true);
    onClose.mockClear(); // Mount-Effekt (pathname) ruft onClose initial
    expect(document.body.querySelector('aside')!.className).toContain('translate-x-0');
    fireEvent.click(document.body.querySelector('div.fixed.inset-0.z-40')!);
    expect(onClose).toHaveBeenCalled();
  });

  it('zeigt User-Card mit Username und Rolle', () => {
    renderSidebar(true);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('User')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen failen (Module fehlen)**

Run: `cd client; npx vitest run src/__tests__/components/layout/`
Expected: FAIL — Module nicht gefunden

- [ ] **Step 3: `SidebarBrand.tsx` implementieren**

```tsx
import logoMark from '../../assets/baluhost-logo.png';
import { useFormattedVersion } from '../../contexts/VersionContext';
import { DeveloperBadge } from '../ui/DeveloperBadge';
import { isPi } from '../../lib/features';

const SIZES = {
  desktop: { box: 'h-12 w-12 p-[3px]', pi: 'text-sm', title: 'text-lg', version: 'text-xs uppercase tracking-[0.35em] text-slate-100-tertiary' },
  mobile: { box: 'h-10 w-10 p-[3px]', pi: 'text-xs', title: 'text-base', version: 'text-[10px] uppercase tracking-[0.3em] text-slate-100-tertiary' },
  compact: { box: 'h-8 w-8 p-[2px]', pi: 'text-[10px]', title: 'text-sm', version: '' },
} as const;

export function SidebarBrand({ variant }: { variant: keyof typeof SIZES }) {
  const formattedVersion = useFormattedVersion('');
  const s = SIZES[variant];
  const gap = variant === 'compact' ? 'gap-2' : 'gap-3';
  return (
    <div className={`flex items-center ${gap}`}>
      <div className={`relative flex ${s.box} items-center justify-center rounded-full bg-slate-950-tertiary`}>
        {isPi ? (
          <div className={`flex h-full w-full items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-indigo-600 ${s.pi} font-bold text-white`}>BP</div>
        ) : (
          <img src={logoMark} alt={variant === 'compact' ? 'BaluHost' : 'BaluHost logo'} className="h-full w-full rounded-full" />
        )}
      </div>
      {variant === 'compact' ? (
        <span className={`${s.title} font-semibold`}>{isPi ? 'BaluPi' : 'BaluHost'}</span>
      ) : (
        <div>
          <p className={`${s.title} font-semibold tracking-wide`}>{isPi ? 'BaluPi' : 'BaluHost'}</p>
          <p className={s.version}>{formattedVersion}{__BUILD_TYPE__ === 'dev' && <span className="font-mono"> · {__GIT_COMMIT__}</span>}</p>
          <DeveloperBadge />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: `SidebarNav.tsx` implementieren**

Die Link-JSX 1:1 aus `Layout.tsx:337-378` (Desktop-Zweig). Einziger Variant-Unterschied (aus `:440-444`): mobile Inactive-Links tragen zusätzlich `hover:border-slate-800`.

```tsx
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AdminBadge } from '../ui/AdminBadge';
import { PluginBadge } from '../ui/PluginBadge';
import type { LayoutNavItem } from './layoutNavConfig';

interface SidebarNavProps {
  items: LayoutNavItem[];
  adminStartIndex: number;
  variant: 'desktop' | 'mobile';
  onNavigate?: () => void;
}

export function SidebarNav({ items, adminStartIndex, variant, onNavigate }: SidebarNavProps) {
  const location = useLocation();
  const { t } = useTranslation('common');
  const inactiveClass = variant === 'mobile'
    ? 'border-transparent text-slate-300 hover:border-slate-800'
    : 'border-transparent text-slate-300';

  return (
    <div className="space-y-1">
      {items.map((item, index) => {
        const active = location.pathname === item.path;
        const isFirstAdminItem = adminStartIndex >= 0 && index === adminStartIndex;
        return (
          <div key={item.path}>
            {isFirstAdminItem && (
              <div className="my-3 border-t border-slate-800/50 pt-3">
                <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                  {t('navigation.admin')}
                </div>
              </div>
            )}
            <Link
              to={item.path}
              onClick={onNavigate}
              className={`group flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
                active ? 'border-sky-500 bg-slate-900-hover text-sky-400' : inactiveClass
              }`}
            >
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-xl border text-base transition-colors duration-200 ${
                  active
                    ? 'border-sky-500/40 bg-slate-950-secondary text-sky-400'
                    : 'border-slate-800 bg-slate-950 text-slate-100-tertiary group-hover:border-sky-500/30 group-hover:text-sky-400'
                }`}
              >
                {item.icon}
              </span>
              <div className="flex flex-col">
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.adminOnly && <AdminBadge />}
                  {item.isPlugin && <PluginBadge />}
                </span>
                <span className="text-xs text-slate-100-tertiary">{item.description}</span>
              </div>
            </Link>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: `DesktopSidebar.tsx` implementieren**

```tsx
import { SidebarBrand } from './SidebarBrand';
import { SidebarNav } from './SidebarNav';
import type { LayoutNavItem } from './layoutNavConfig';

interface DesktopSidebarProps {
  isImpersonating: boolean;
  items: LayoutNavItem[];
  adminStartIndex: number;
}

export function DesktopSidebar({ isImpersonating, items, adminStartIndex }: DesktopSidebarProps) {
  return (
    <aside className={`fixed left-0 hidden lg:flex w-72 flex-col border-r border-white/10 bg-white/5 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.1)] ${isImpersonating ? 'top-10 h-[calc(100vh-2.5rem)]' : 'top-0 h-screen'}`}>
      <div className="px-6 pt-10 pb-8">
        <SidebarBrand variant="desktop" />
      </div>
      <nav className="flex-1 px-4 overflow-y-auto scrollbar-thin pb-4">
        <SidebarNav items={items} adminStartIndex={adminStartIndex} variant="desktop" />
      </nav>
    </aside>
  );
}
```

- [ ] **Step 6: `MobileSidebar.tsx` implementieren**

Rahmen/Overlay/Close-Button/User-Card verbatim aus `Layout.tsx:386-484`; neu ist nur der `pathname`-Effect.

```tsx
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { SidebarBrand } from './SidebarBrand';
import { SidebarNav } from './SidebarNav';
import type { LayoutNavItem } from './layoutNavConfig';

interface MobileSidebarProps {
  open: boolean;
  onClose: () => void;
  isImpersonating: boolean;
  items: LayoutNavItem[];
  adminStartIndex: number;
  username?: string;
  isAdmin: boolean;
}

export function MobileSidebar({ open, onClose, isImpersonating, items, adminStartIndex, username, isAdmin }: MobileSidebarProps) {
  const location = useLocation();

  // Vor der Layout-Route schloss der Remount das Menü bei Navigation implizit —
  // jetzt muss das explizit passieren (Spec-Delta Nr. 4).
  useEffect(() => {
    onClose();
  }, [location.pathname, onClose]);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}
      <aside className={`fixed left-0 z-50 w-72 flex flex-col border-r border-white/10 bg-slate-900/95 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] transition-transform duration-300 lg:hidden ${
        open ? 'translate-x-0' : '-translate-x-full'
      } ${isImpersonating ? 'top-10 h-[calc(100vh-2.5rem)]' : 'top-0 h-screen'}`}>
        <div className="flex items-center justify-between px-6 pt-6 pb-4">
          <SidebarBrand variant="mobile" />
          <button
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
          >
            <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-5 w-5">
              <path stroke="currentColor" strokeLinecap="round" d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 px-4 overflow-y-auto scrollbar-thin pb-4">
          <SidebarNav items={items} adminStartIndex={adminStartIndex} variant="mobile" onNavigate={onClose} />
        </nav>

        <div className="px-4 pb-6">
          <div className="glass-accent border-slate-800 bg-slate-900/55">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400">Logged in as</p>
                <p className="text-sm font-semibold text-slate-100">{username}</p>
                <p className="text-xs text-slate-100-tertiary">{isAdmin ? 'Administrator' : 'User'}</p>
              </div>
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-lg font-semibold text-sky-400">
                {username?.charAt(0).toUpperCase()}
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
```

Hinweis: Im Ist-Code fehlt die Brand-Wrapper-Struktur nicht — `SidebarBrand variant="mobile"` ersetzt `Layout.tsx:398-411` exakt (gleiches Markup, nur zentralisiert).

- [ ] **Step 7: Tests laufen lassen — müssen passen**

Run: `cd client; npx vitest run src/__tests__/components/layout/`
Expected: 8 PASS

- [ ] **Step 8: Commit**

```bash
git add client/src/components/layout/ client/src/__tests__/components/layout/
git commit -m "feat(layout): SidebarBrand/SidebarNav/DesktopSidebar/MobileSidebar (#301)"
```

---

### Task 4: `usePowerActions` + `PendingPowerOverlay` + `LayoutHeader` + Tests

**Files:**
- Create: `client/src/hooks/usePowerActions.ts`
- Create: `client/src/components/layout/PendingPowerOverlay.tsx`
- Create: `client/src/components/layout/LayoutHeader.tsx`
- Test: `client/src/__tests__/hooks/usePowerActions.test.tsx`
- Test: `client/src/__tests__/components/layout/LayoutHeader.test.tsx`
- Quelle für Verbatim-Kopien: `Layout.tsx:487-501` (Overlay), `:503-607` (Header), `:546-604` (Power-Handler)

**Interfaces:**
- Produces:
  - `usePowerActions.ts`: `export type PendingPowerAction = 'shutdown' | 'restart' | null;` `export function usePowerActions(logout: () => void): { pendingAction: PendingPowerAction; pendingMessage: string | null; onShutdown: () => Promise<void>; onRestart: () => Promise<void> }`
  - `PendingPowerOverlay`: `({ action, message }: { action: PendingPowerAction; message: string | null })` — rendert `null` wenn `action === null`.
  - `LayoutHeader`: `({ isImpersonating, isAdmin, onOpenMobileMenu, onShutdown, onRestart, onLogout })`

- [ ] **Step 1: Failing Test für `usePowerActions` schreiben**

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePowerActions } from '../../hooks/usePowerActions';

const localApiMock = vi.hoisted(() => ({
  shutdown: vi.fn(),
  restart: vi.fn(),
  isAvailable: vi.fn(),
}));
vi.mock('../../lib/localApi', () => ({ localApi: localApiMock }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const reloadMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  localApiMock.shutdown.mockReset();
  localApiMock.restart.mockReset();
  localApiMock.isAvailable.mockReset();
  reloadMock.mockReset();
  // jsdom implementiert reload nicht — ersetzen
  Object.defineProperty(window, 'location', {
    value: { ...window.location, reload: reloadMock },
    writable: true,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('usePowerActions', () => {
  it('shutdown: pending → nach (eta+1)s logout und pending zurückgesetzt', async () => {
    localApiMock.shutdown.mockResolvedValue({ eta_seconds: 3 });
    const logout = vi.fn();
    const { result } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onShutdown());
    expect(result.current.pendingAction).toBe('shutdown');
    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(result.current.pendingAction).toBeNull();
  });

  it('shutdown-Fehler: Fallback-Timeout 2s → logout', async () => {
    localApiMock.shutdown.mockRejectedValue(new Error('nope'));
    const logout = vi.fn();
    const { result } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onShutdown());
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('restart: pollt bis Server verfügbar, dann reload', async () => {
    localApiMock.restart.mockResolvedValue(undefined);
    localApiMock.isAvailable.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { result } = renderHook(() => usePowerActions(vi.fn()));
    await act(() => result.current.onRestart());
    expect(result.current.pendingAction).toBe('restart');
    await act(() => vi.advanceTimersByTimeAsync(2000)); // Poll 1: false
    expect(reloadMock).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(2000)); // Poll 2: true
    expect(reloadMock).toHaveBeenCalledTimes(1);
    expect(result.current.pendingAction).toBeNull();
  });

  it('restart: nach 60s ohne Server → logout', async () => {
    localApiMock.restart.mockResolvedValue(undefined);
    localApiMock.isAvailable.mockResolvedValue(false);
    const logout = vi.fn();
    const { result } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onRestart());
    await act(() => vi.advanceTimersByTimeAsync(62000));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('Cleanup: Unmount während des Pollings stoppt Intervall und Timeouts', async () => {
    localApiMock.restart.mockResolvedValue(undefined);
    localApiMock.isAvailable.mockResolvedValue(false);
    const logout = vi.fn();
    const { result, unmount } = renderHook(() => usePowerActions(logout));
    await act(() => result.current.onRestart());
    await act(() => vi.advanceTimersByTimeAsync(2000));
    const callsBefore = localApiMock.isAvailable.mock.calls.length;
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(localApiMock.isAvailable.mock.calls.length).toBe(callsBefore);
    expect(logout).not.toHaveBeenCalled();
    expect(reloadMock).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss failen**

Run: `cd client; npx vitest run src/__tests__/hooks/usePowerActions.test.tsx`
Expected: FAIL — Modul nicht gefunden

- [ ] **Step 3: `usePowerActions.ts` implementieren**

Logik 1:1 aus `Layout.tsx:548-602`, plus Cleanup (Spec: „Fix im Zuge der Extraktion").

```tsx
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { localApi } from '../lib/localApi';

export type PendingPowerAction = 'shutdown' | 'restart' | null;

export function usePowerActions(logout: () => void) {
  const { t } = useTranslation('common');
  const [pendingAction, setPendingAction] = useState<PendingPowerAction>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const timeoutsRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup bei Unmount: Ist-Code leakte Intervall/Timeouts (Layout.tsx:579-594)
  useEffect(() => () => {
    timeoutsRef.current.forEach(clearTimeout);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  const later = (fn: () => void, ms: number) => {
    timeoutsRef.current.push(setTimeout(fn, ms));
  };

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const onShutdown = async () => {
    setPendingAction('shutdown');
    setPendingMessage(t('powerMenu.shutdownStarted', 'Shutdown initiated...'));
    try {
      const res = await localApi.shutdown();
      const eta = (res && typeof res === 'object' && 'eta_seconds' in res ? (res as { eta_seconds: number }).eta_seconds : 1);
      setPendingMessage(t('powerMenu.shutdownEta', 'Shutdown scheduled — stopping in ~{{eta}}s', { eta }));
      later(() => {
        setPendingAction(null);
        logout();
      }, (eta + 1) * 1000);
    } catch {
      setPendingMessage(t('powerMenu.shuttingDown', 'Shutting down...'));
      later(() => {
        setPendingAction(null);
        logout();
      }, 2000);
    }
  };

  const onRestart = async () => {
    setPendingAction('restart');
    setPendingMessage(t('powerMenu.restartStarted', 'Restart initiated...'));
    try {
      await localApi.restart();
      setPendingMessage(t('powerMenu.restartingWait', 'Restarting — waiting for server...'));
      const startTime = Date.now();
      intervalRef.current = setInterval(async () => {
        const available = await localApi.isAvailable();
        if (available) {
          stopPolling();
          setPendingAction(null);
          window.location.reload();
        }
        if (Date.now() - startTime > 60000) {
          stopPolling();
          setPendingAction(null);
          setPendingMessage(null);
          logout();
        }
      }, 2000);
    } catch {
      setPendingMessage(t('powerMenu.restartingWait', 'Restarting — waiting for server...'));
      later(() => {
        setPendingAction(null);
        logout();
      }, 5000);
    }
  };

  return { pendingAction, pendingMessage, onShutdown, onRestart };
}
```

- [ ] **Step 4: Test laufen lassen — muss passen**

Run: `cd client; npx vitest run src/__tests__/hooks/usePowerActions.test.tsx`
Expected: 5 PASS

- [ ] **Step 5: `PendingPowerOverlay.tsx` implementieren** (JSX verbatim aus `Layout.tsx:487-501`)

```tsx
import { useTranslation } from 'react-i18next';
import type { PendingPowerAction } from '../../hooks/usePowerActions';

interface PendingPowerOverlayProps {
  action: PendingPowerAction;
  message: string | null;
}

export function PendingPowerOverlay({ action, message }: PendingPowerOverlayProps) {
  const { t } = useTranslation('common');
  if (!action) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4 rounded-2xl bg-slate-900/90 border border-slate-800 p-6">
        <div className={`h-12 w-12 flex items-center justify-center rounded-full ${action === 'restart' ? 'bg-amber-500/10 text-amber-400' : 'bg-rose-500/10 text-rose-400'}`}>
          <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none" strokeWidth={2}>
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M12 2v4M12 18v4M4.2 4.2l2.8 2.8M17 17l2.8 2.8M2 12h4M18 12h4M4.2 19.8l2.8-2.8M17 7l2.8-2.8" />
          </svg>
        </div>
        <div className="text-center">
          <p className="font-semibold">{action === 'restart' ? t('powerMenu.restarting', 'Restarting...') : t('powerMenu.shuttingDown', 'Shutting down...')}</p>
          <p className="text-sm text-slate-100-tertiary">{message}</p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: `LayoutHeader.tsx` implementieren** (JSX verbatim aus `Layout.tsx:503-607`; Mobile-Brand → `SidebarBrand variant="compact"`; die Inline-Power-Callbacks werden zu Props)

```tsx
import NotificationCenter from '../NotificationCenter';
import PowerMenu from '../PowerMenu';
import UserMenu from '../UserMenu';
import { TopbarStatusStrip } from '../topbar/TopbarStatusStrip';
import { isPi } from '../../lib/features';
import { SidebarBrand } from './SidebarBrand';

interface LayoutHeaderProps {
  isImpersonating: boolean;
  isAdmin: boolean;
  onOpenMobileMenu: () => void;
  onShutdown: () => void;
  onRestart: () => void;
  onLogout: () => void;
}

export function LayoutHeader({ isImpersonating, isAdmin, onOpenMobileMenu, onShutdown, onRestart, onLogout }: LayoutHeaderProps) {
  return (
    <header className={`fixed right-0 left-0 lg:left-72 z-30 border-b border-slate-800/50 bg-slate-900/20 px-4 py-4 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl sm:px-6 lg:px-10 ${isImpersonating ? 'top-10' : 'top-0'}`}>
      <div className="flex items-center justify-between">
        {/* Mobile Header Left */}
        <div className="flex items-center gap-3 lg:hidden">
          <button
            onClick={onOpenMobileMenu}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
          >
            <svg viewBox="0 0 24 24" fill="none" strokeWidth={2} className="h-5 w-5">
              <path stroke="currentColor" strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <SidebarBrand variant="compact" />
        </div>

        {/* Status strip (desktop only, hidden in Pi mode) */}
        <div className="hidden lg:flex flex-1 items-center justify-center px-6">
          {!isPi && <TopbarStatusStrip />}
        </div>

        {/* Header Right */}
        <div className="flex items-center gap-3">
          {!isPi && <NotificationCenter />}
          <UserMenu />
          {isPi ? (
            <button
              onClick={onLogout}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 hover:border-sky-500/50 hover:text-sky-400 transition"
              title="Logout"
            >
              <svg viewBox="0 0 24 24" fill="none" strokeWidth={1.6} className="h-5 w-5">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          ) : (
            <PowerMenu isAdmin={isAdmin} onShutdown={onShutdown} onRestart={onRestart} onLogout={onLogout} />
          )}
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 7: `LayoutHeader.test.tsx` schreiben und laufen lassen**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LayoutHeader } from '../../../components/layout/LayoutHeader';

const featureState = vi.hoisted(() => ({ isPi: false }));
vi.mock('../../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));
vi.mock('../../../components/NotificationCenter', () => ({ default: () => <div data-testid="notification-center" /> }));
vi.mock('../../../components/PowerMenu', () => ({ default: () => <div data-testid="power-menu" /> }));
vi.mock('../../../components/UserMenu', () => ({ default: () => <div data-testid="user-menu" /> }));
vi.mock('../../../components/topbar/TopbarStatusStrip', () => ({ TopbarStatusStrip: () => <div data-testid="topbar-status-strip" /> }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const props = {
  isImpersonating: false,
  isAdmin: true,
  onOpenMobileMenu: vi.fn(),
  onShutdown: vi.fn(),
  onRestart: vi.fn(),
  onLogout: vi.fn(),
};

beforeEach(() => { featureState.isPi = false; });

describe('LayoutHeader', () => {
  it('Standard: PowerMenu + NotificationCenter + StatusStrip, kein Pi-Logout-Button', () => {
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.getByTestId('power-menu')).toBeInTheDocument();
    expect(screen.getByTestId('notification-center')).toBeInTheDocument();
    expect(screen.getByTestId('topbar-status-strip')).toBeInTheDocument();
    expect(screen.queryByTitle('Logout')).not.toBeInTheDocument();
  });

  it('Pi: Logout-Button statt PowerMenu, kein NotificationCenter/StatusStrip', () => {
    featureState.isPi = true;
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    expect(screen.getByTitle('Logout')).toBeInTheDocument();
    expect(screen.queryByTestId('power-menu')).not.toBeInTheDocument();
    expect(screen.queryByTestId('notification-center')).not.toBeInTheDocument();
    expect(screen.queryByTestId('topbar-status-strip')).not.toBeInTheDocument();
  });

  it('Impersonation: header top-10', () => {
    const { container } = render(<MemoryRouter><LayoutHeader {...props} isImpersonating /></MemoryRouter>);
    expect(container.querySelector('header')!.className).toContain('top-10');
  });
});
```

Run: `cd client; npx vitest run src/__tests__/components/layout/LayoutHeader.test.tsx`
Expected: 3 PASS

- [ ] **Step 8: Commit**

```bash
git add client/src/hooks/usePowerActions.ts client/src/components/layout/PendingPowerOverlay.tsx client/src/components/layout/LayoutHeader.tsx client/src/__tests__/hooks/usePowerActions.test.tsx client/src/__tests__/components/layout/LayoutHeader.test.tsx
git commit -m "feat(layout): usePowerActions hook + PendingPowerOverlay + LayoutHeader (#301)"
```

---

### Task 5: `Layout.tsx` → dünner Orchestrator + Barrel

**Files:**
- Modify: `client/src/components/Layout.tsx` (kompletter Ersatz)
- Create: `client/src/components/layout/index.ts`
- Test (unverändert!): `client/src/__tests__/components/Layout.test.tsx`

**Interfaces:**
- Consumes: alles aus Tasks 2–4.
- Produces: `Layout` (Default-Export, `{ children }`) — identisches Außenverhalten.

- [ ] **Step 1: Barrel `client/src/components/layout/index.ts` schreiben**

```ts
export { DesktopSidebar } from './DesktopSidebar';
export { MobileSidebar } from './MobileSidebar';
export { LayoutHeader } from './LayoutHeader';
export { PendingPowerOverlay } from './PendingPowerOverlay';
export { SidebarBrand } from './SidebarBrand';
export { SidebarNav } from './SidebarNav';
export { buildNavItems, navIcon, PI_NAV_PATHS } from './layoutNavConfig';
export type { LayoutNavItem } from './layoutNavConfig';
```

- [ ] **Step 2: `Layout.tsx` komplett ersetzen**

```tsx
import { useLocation } from 'react-router-dom';
import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getStatusBarState } from '../api/statusBar';
import { isPi } from '../lib/features';
import { UploadProgressBar } from './UploadProgressBar';
import ImpersonationBanner from './ImpersonationBanner';
import { useLayoutNav } from '../hooks/useLayoutNav';
import { usePowerActions } from '../hooks/usePowerActions';
import { DesktopSidebar, MobileSidebar, LayoutHeader, PendingPowerOverlay } from './layout';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { user, logout, isAdmin, isImpersonating } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showUploadBar, setShowUploadBar] = useState(true);
  const { allNavItems, adminStartIndex } = useLayoutNav();
  const { pendingAction, pendingMessage, onShutdown, onRestart } = usePowerActions(logout);

  // Auf pathname gekeyt: refetcht wie vor der Layout-Route bei jeder Navigation,
  // sonst bliebe show_bottom_upload nach einer Einstellungsänderung stale
  // (Spec-Delta Nr. 2).
  useEffect(() => {
    let cancelled = false;
    getStatusBarState()
      .then((s) => { if (!cancelled) setShowUploadBar(s.show_bottom_upload); })
      .catch(() => { /* default to showing on error */ });
    return () => { cancelled = true; };
  }, [location.pathname]);

  const closeMobileMenu = useCallback(() => setMobileMenuOpen(false), []);

  return (
    <div className="relative min-h-screen overflow-x-hidden text-slate-100">
      <div className="relative z-10 flex min-h-screen">
        <DesktopSidebar isImpersonating={isImpersonating} items={allNavItems} adminStartIndex={adminStartIndex} />
        <MobileSidebar
          open={mobileMenuOpen}
          onClose={closeMobileMenu}
          isImpersonating={isImpersonating}
          items={allNavItems}
          adminStartIndex={adminStartIndex}
          username={user?.username}
          isAdmin={isAdmin}
        />
        <div className="flex flex-1 flex-col lg:pl-72 overflow-x-hidden">
          <PendingPowerOverlay action={pendingAction} message={pendingMessage} />
          <ImpersonationBanner />
          <LayoutHeader
            isImpersonating={isImpersonating}
            isAdmin={isAdmin}
            onOpenMobileMenu={() => setMobileMenuOpen(true)}
            onShutdown={onShutdown}
            onRestart={onRestart}
            onLogout={logout}
          />
          <main className={`flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-10 pb-[env(safe-area-inset-bottom)] ${isImpersonating ? 'mt-[112px]' : 'mt-[72px]'}`}>
            <div className={`${location.pathname === '/admin-db' ? 'w-full max-w-none mx-0' : 'mx-auto w-full max-w-7xl'} space-y-6 sm:space-y-8`}>
              {children}
            </div>
          </main>
          {!isPi && showUploadBar && <UploadProgressBar />}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Charakterisierungs-Tests laufen lassen — UNVERÄNDERT grün**

Run: `cd client; npx vitest run src/__tests__/components/Layout.test.tsx`
Expected: 11 PASS ohne jede Änderung an der Testdatei. Wenn ein Test rot ist: Implementierung fixen, NICHT den Test.

- [ ] **Step 4: Zeilenzahl prüfen**

Run (PowerShell): `(Get-Content client/src/components/Layout.tsx | Measure-Object -Line).Lines`
Expected: deutlich unter 500 (~100).

- [ ] **Step 5: Gesamte Layout-bezogene Suite + Commit**

Run: `cd client; npx vitest run src/__tests__/components/layout/ src/__tests__/components/Layout.test.tsx src/__tests__/hooks/useLayoutNav.test.tsx src/__tests__/hooks/usePowerActions.test.tsx`
Expected: alle PASS

```bash
git add client/src/components/Layout.tsx client/src/components/layout/index.ts
git commit -m "refactor(layout): Layout as thin orchestrator over layout/* (#301) [F2]"
```

---

### Task 6: App.tsx-Layout-Route + `AppLayout` + `LoadingFallback`-Extraktion + Routing-Tests

**Files:**
- Create: `client/src/components/ui/LoadingFallback.tsx`
- Create: `client/src/components/layout/AppLayout.tsx`
- Modify: `client/src/App.tsx` (Routes-Block `:173-237`, `LoadingFallback`-Definition `:61-70` entfernen, `AppRoutes` exportieren)
- Test: `client/src/__tests__/App.routing.test.tsx`

**Interfaces:**
- Consumes: `Layout` (Task 5).
- Produces: `AppLayout` (Default-los, named export), `LoadingFallback` (named export aus `ui/`), `export function AppRoutes()` in App.tsx (für den Test).

- [ ] **Step 1: `LoadingFallback` nach `client/src/components/ui/LoadingFallback.tsx` verschieben** (JSX verbatim aus `App.tsx:61-70`)

```tsx
export function LoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-sky-500" />
        <p className="text-sm text-slate-500">Loading...</p>
      </div>
    </div>
  );
}
```

In `App.tsx` die lokale Definition löschen und importieren: `import { LoadingFallback } from './components/ui/LoadingFallback';`

- [ ] **Step 2: `AppLayout.tsx` schreiben**

```tsx
import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import Layout from '../Layout';
import { LoadingFallback } from '../ui/LoadingFallback';

// Innerer Suspense: beim Lazy-Load eines Seiten-Chunks bleibt die Sidebar stehen.
export function AppLayout() {
  return (
    <Layout>
      <Suspense fallback={<LoadingFallback />}>
        <Outlet />
      </Suspense>
    </Layout>
  );
}
```

In den Barrel aufnehmen (`client/src/components/layout/index.ts`): `export { AppLayout } from './AppLayout';`

- [ ] **Step 3: App.tsx umbauen**

`function AppRoutes()` → `export function AppRoutes()`. Import `Layout` ersetzen durch `import { AppLayout } from './components/layout';`. Der Routes-Block (`App.tsx:173-237`) wird zu:

```tsx
<Routes>
  <Route
    path="/login"
    element={user ? <Navigate to="/" /> : <Login />}
  />

  <Route element={user ? <AppLayout /> : <Navigate to="/login" replace />}>
    <Route path="/" element={PiDashboard ? <PiDashboard /> : <Dashboard />} />
    <Route path="/system" element={<SystemMonitor />} />

    {/* Desktop-only routes (not bundled in Pi builds) */}
    {FileManager && <Route path="/files" element={<FileManager />} />}
    {UserManagement && <Route path="/users" element={isAdmin ? <UserManagement /> : <Navigate to="/" />} />}
    {AdminDatabase && <Route path="/admin-db" element={isAdmin ? <AdminDatabase /> : <Navigate to="/" />} />}
    {SchedulerDashboard && <Route path="/schedulers" element={isAdmin ? <SchedulerDashboard /> : <Navigate to="/" />} />}
    {SharesPage && <Route path="/shares" element={<SharesPage />} />}
    {SettingsPage && <Route path="/settings" element={<SettingsPage />} />}
    {DevicesPage && <Route path="/devices" element={<DevicesPage />} />}
    {SystemControlPage && <Route path="/admin/system-control" element={isAdmin ? <SystemControlPage /> : <Navigate to="/" />} />}
    {NotificationsArchivePage && <Route path="/notifications" element={<NotificationsArchivePage />} />}
    {UserManualPage && <Route path="/manual" element={<UserManualPage />} />}
    {PluginsPage && <Route path="/plugins" element={isAdmin ? <PluginsPage /> : <Navigate to="/" />} />}
    {PluginPage && <Route path="/plugins/:pluginName/*" element={<PluginPage />} />}
    {UpdatePage && <Route path="/updates" element={isAdmin ? <UpdatePage /> : <Navigate to="/" />} />}
    {CloudImportPage && <Route path="/cloud-import" element={<CloudImportPage />} />}
    {PiholePage && <Route path="/pihole" element={isAdmin ? <PiholePage /> : <Navigate to="/" />} />}
    {SmartDevicesPage && <Route path="/smart-devices" element={<SmartDevicesPage />} />}
  </Route>

  {/* Redirects bleiben unverändert außerhalb der Layout-Route */}
  {isDesktop && <Route path="/settings/notifications" element={<Navigate to="/settings?tab=notifications" replace />} />}
  {isDesktop && <Route path="/notifications/settings" element={<Navigate to="/settings?tab=notifications" replace />} />}
  {isDesktop && <Route path="/docs" element={<Navigate to="/manual" replace />} />}
  {isDesktop && <Route path="/raid" element={<Navigate to="/admin/system-control?tab=raid" replace />} />}
  {isDesktop && <Route path="/health" element={<Navigate to="/system?tab=health" replace />} />}
  {isDesktop && <Route path="/power" element={<Navigate to="/admin/system-control?tab=energy" replace />} />}
  {isDesktop && <Route path="/fan-control" element={<Navigate to="/admin/system-control?tab=fan" replace />} />}
  {isDesktop && <Route path="/logging" element={<Navigate to="/system?tab=logs" replace />} />}
  {isDesktop && <Route path="/sync-prototype" element={<Navigate to="/devices?tab=desktop" replace />} />}
  {isDesktop && <Route path="/mobile-devices" element={<Navigate to="/devices?tab=mobile" replace />} />}
  {isDesktop && <Route path="/admin/backup" element={<Navigate to="/admin/system-control?tab=backup" replace />} />}
  {isDesktop && <Route path="/admin/vpn" element={<Navigate to="/admin/system-control?tab=vpn" replace />} />}
  {isDesktop && <Route path="/backups" element={<Navigate to="/admin/system-control?tab=backup" replace />} />}
</Routes>
```

Wichtig: Die per-Route `user`-Checks entfallen (übernimmt die Eltern-Route); die `isAdmin`-Checks bleiben exakt erhalten.

- [ ] **Step 4: Routing-Test schreiben**

`client/src/__tests__/App.routing.test.tsx` — rendert `AppRoutes` (mit echtem `BrowserRouter` darin), navigiert per Sidebar-Link, prüft Layout-Persistenz per Mount-Zähler:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AppRoutes } from '../App';

const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'admin', role: 'admin' } as { id: number; username: string; role: string } | null,
  isAdmin: true,
  isImpersonating: false,
  loading: false,
  logout: vi.fn(),
}));
const mountCount = vi.hoisted(() => ({ current: 0 }));
const getStatusBarStateMock = vi.hoisted(() =>
  vi.fn(async () => ({ pills: [], show_bottom_upload: true })),
);

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/PluginContext', () => ({
  usePlugins: () => ({ pluginNavItems: [] }),
  PluginProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/VersionContext', () => ({
  useFormattedVersion: () => 'v1.38.0',
  VersionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/UploadContext', () => ({
  UploadProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../contexts/NotificationContext', () => ({
  NotificationProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../hooks/useIdleTimeout', () => ({
  useIdleTimeout: () => ({ warningVisible: false, secondsRemaining: 0, resetTimer: vi.fn() }),
}));
vi.mock('../hooks/usePresenceHeartbeat', () => ({ usePresenceHeartbeat: vi.fn() }));
vi.mock('../api/statusBar', () => ({ getStatusBarState: getStatusBarStateMock }));
vi.mock('../lib/localApi', () => ({
  localApi: { shutdown: vi.fn(), restart: vi.fn(), isAvailable: vi.fn() },
}));
vi.mock('../lib/pluginI18n', () => ({
  resolvePluginString: (_t: unknown, _k: string, f: string) => f,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Schwere Layout-Kinder
vi.mock('../components/NotificationCenter', () => ({ default: () => null }));
vi.mock('../components/PowerMenu', () => ({ default: () => null }));
vi.mock('../components/UploadProgressBar', () => ({ UploadProgressBar: () => null }));
vi.mock('../components/topbar/TopbarStatusStrip', () => ({ TopbarStatusStrip: () => null }));
vi.mock('../components/ImpersonationBanner', () => ({ default: () => null }));

// Mount-Zähler: UserMenu ist immer im Header — remountet Layout, zählt er hoch.
vi.mock('../components/UserMenu', async () => {
  const { useEffect } = await import('react');
  return {
    default: () => {
      useEffect(() => { mountCount.current += 1; }, []);
      return <div data-testid="user-menu" />;
    },
  };
});

// Seiten, die der Test besucht (lazy → Mock-Module lösen sofort auf)
vi.mock('../pages/Dashboard', () => ({ default: () => <div data-testid="dashboard-page" /> }));
vi.mock('../pages/SystemMonitor', () => ({ default: () => <div data-testid="system-page" /> }));
vi.mock('../pages/UserManagement', () => ({ default: () => <div data-testid="users-page" /> }));
vi.mock('../pages/Login', () => ({ default: () => <div data-testid="login-page" /> }));

beforeEach(() => {
  authState.user = { id: 1, username: 'admin', role: 'admin' };
  authState.isAdmin = true;
  mountCount.current = 0;
  getStatusBarStateMock.mockClear();
  window.history.pushState({}, '', '/');
});

describe('App routing mit Layout-Route', () => {
  it('Layout bleibt über Navigation gemountet; StatusBar refetcht pro Navigation', async () => {
    render(<AppRoutes />);
    await screen.findByTestId('dashboard-page');
    expect(mountCount.current).toBe(1);
    const fetchesBefore = getStatusBarStateMock.mock.calls.length;

    // Desktop-Sidebar-Link "System" klicken (erster von zwei)
    fireEvent.click(screen.getAllByText('navigation.system')[0]);
    await screen.findByTestId('system-page');

    expect(mountCount.current).toBe(1); // KEIN Remount
    expect(getStatusBarStateMock.mock.calls.length).toBeGreaterThan(fetchesBefore); // Delta Nr. 2
  });

  it('ausgeloggt → /login', async () => {
    authState.user = null;
    authState.isAdmin = false;
    render(<AppRoutes />);
    await screen.findByTestId('login-page');
    expect(window.location.pathname).toBe('/login');
  });

  it('Nicht-Admin auf /users → redirect auf Dashboard', async () => {
    authState.isAdmin = false;
    authState.user = { id: 2, username: 'user', role: 'user' };
    window.history.pushState({}, '', '/users');
    render(<AppRoutes />);
    await screen.findByTestId('dashboard-page');
    expect(screen.queryByTestId('users-page')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd client; npx vitest run src/__tests__/App.routing.test.tsx`
Expected: 3 PASS. (Falls `AppRoutes` weitere ungemockte Provider/Assets zieht: fehlende Module analog mocken — Muster oben.)

- [ ] **Step 6: Volle Gates**

Run: `cd client; npx eslint .` — Expected: 0 Errors
Run: `cd client; npm run build` — Expected: Erfolg (tsc -b + vite build)
Run: `cd client; npx vitest run` — Expected: komplette Suite grün

- [ ] **Step 7: Commit**

```bash
git add client/src/App.tsx client/src/components/layout/AppLayout.tsx client/src/components/layout/index.ts client/src/components/ui/LoadingFallback.tsx client/src/__tests__/App.routing.test.tsx
git commit -m "feat(app): single layout route via AppLayout/Outlet, Layout persists across navigation (#301)"
```

---

### Task 7: CLAUDE.md-Sync + PR

**Files:**
- Modify: `client/src/components/CLAUDE.md` (Layout-Eintrag + `layout/`-Zeile in der Feature-Tabelle)
- Modify: `client/src/hooks/CLAUDE.md` (neue Hooks eintragen, Format der Datei folgen)
- Modify (falls Layout/App dort beschrieben): `client/src/pages/CLAUDE.md`, `client/src/lib/CLAUDE.md` — nur prüfen, nur bei Treffern anpassen

**Interfaces:** keine Code-Änderungen mehr in diesem Task.

- [ ] **Step 1: `components/CLAUDE.md` aktualisieren**

Top-level-Eintrag ersetzen:

```markdown
- `Layout.tsx` — Thin orchestrator over `layout/*` (sidebar navigation, header, power overlay); mounted once via the `AppLayout` layout route (F2/#301)
```

In der Feature-Tabelle ergänzen (alphabetisch bei `l`):

```markdown
| `layout/` | App shell — `AppLayout` (layout route: `<Layout><Suspense><Outlet/></Suspense></Layout>`), `DesktopSidebar`/`MobileSidebar` (composing `SidebarBrand`+`SidebarNav`), `LayoutHeader`, `PendingPowerOverlay`, `layoutNavConfig` (icons + `buildNavItems`); nav filtering in `hooks/useLayoutNav`, shutdown/restart in `hooks/usePowerActions` (extracted F2/#301) |
```

- [ ] **Step 2: `hooks/CLAUDE.md` aktualisieren** — bestehendes Listenformat der Datei übernehmen und `useLayoutNav` (Nav-Filterung Pi/Admin/Plugins) + `usePowerActions` (Shutdown/Restart inkl. Poll-Cleanup) eintragen.

- [ ] **Step 3: Verbleibende Erwähnungen prüfen**

Run (PowerShell): `Get-ChildItem client/src -Recurse -Filter CLAUDE.md | Select-String -Pattern "Layout"`
Jeden Treffer prüfen; veraltete Aussagen (z. B. „Layout with sidebar navigation, header, power menu…") an den neuen Stand anpassen.

- [ ] **Step 4: Commit + Push + PR**

```bash
git add client/src/components/CLAUDE.md client/src/hooks/CLAUDE.md
git commit -m "docs(client): sync CLAUDE.md for layout/* decomposition (#301)"
git push -u origin refactor/f2-layout-decomposition
```

PR-Body mit dem Write-Tool nach `C:\Users\SvenB\AppData\Local\Temp\claude\...\scratchpad\pr-body.md` schreiben (Memory: keine Here-Strings für PR-Bodies), Inhalt:

```markdown
## Summary
- decompose `Layout.tsx` (585 lines) into `components/layout/*` + `useLayoutNav`/`usePowerActions` (F2 pattern); Layout keeps its `{ children }` API
- replace the ~18 per-route `<Layout>` wrappers in `App.tsx` with a single layout route (`AppLayout` + `<Outlet/>`) — Layout now persists across navigation
- add the previously missing test coverage: characterization tests (written against the old Layout, passing unchanged against the new one), unit tests per extracted piece, routing tests for the new mount semantics
- fix latent cleanup leak in the restart polling (interval/timeouts now cleared on unmount, covered by fake-timer tests)

Design: `docs/superpowers/specs/2026-07-18-layout-decomposition-design.md`

Closes #301

## Test plan
- [ ] `npx vitest run` (client, full suite)
- [ ] `npx eslint .` — 0 errors
- [ ] `npm run build`
- [ ] manual smoke: navigate Dashboard → System → Files; sidebar scroll persists; mobile menu closes on navigation; `/admin-db` full width; shutdown/restart overlay

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

```bash
gh pr create --title "refactor(layout): decompose Layout into layout/* + single layout route (#301) [F2]" --body-file <scratchpad>/pr-body.md
```

- [ ] **Step 5: Verifikation nach CI** — `gh pr checks --watch`; erst nach grünem CI als fertig melden.
