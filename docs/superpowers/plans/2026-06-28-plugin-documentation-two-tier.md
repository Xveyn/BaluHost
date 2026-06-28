# Plugin Documentation — Two-Tier Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the admin-only plugin **Documentation** tab so it leads with the two trust tiers (bundled in-process vs external sandboxed), renders the live capability-scope catalog, fixes the inaccurate install text, and condenses the bundled author reference.

**Architecture:** Frontend-only. `PluginsPage` already holds `scopeCatalog` state (from `getScopeCatalog()`, added in #287); it passes that state down as a new prop to a rewritten `PluginDocumentation.tsx`. The component consumes the catalog directly (no new fetch), groups scopes by tier, and looks up scope labels with the separator-safe `returnObjects` pattern already used by the enable-time scope-picker. The old single-tier "drop folder in `installed/`" / 26-hook-grid content is removed; its now-unused i18n keys are deleted from both locale files.

**Tech Stack:** React 18 + TypeScript (strict, `verbatimModuleSyntax`), Tailwind CSS, `react-i18next`, `lucide-react`, Vitest + Testing Library.

## Global Constraints

- **Frontend only.** No backend changes. The catalog endpoint (`GET /api/plugins/scope-catalog`), `ScopeInfo`, `scopeDescriptions.*`, and `scopeTiers.*` already exist from #287 — do not add or modify them.
- **Both locales always.** Every i18n key added or removed must be applied to BOTH `client/src/i18n/locales/en/plugins.json` AND `client/src/i18n/locales/de/plugins.json`. Missing keys fall back to German.
- **Separator-safe scope lookup.** Scope keys contain `:` (i18next nsSeparator) and `.` (keySeparator). NEVER do `t('scopeDescriptions.' + key)`. Use `const scopeDescs = t('scopeDescriptions', { returnObjects: true }) as Record<string, { label: string; description: string }>;` then index `scopeDescs?.[scope.key]`. Tier headings use `t(\`scopeTiers.${tier}\`)` (the tier names `frontend`/`backend` contain no separators).
- **Type-only imports.** `verbatimModuleSyntax: true` is on — import types with `import type { ... }`.
- **Test convention.** Tests live in the centralized mirror tree `client/src/__tests__/<area>/` (NOT co-located). `react-i18next` is stubbed `t: (k) => k`, so assert on i18n KEYS and scope keys, never English copy. `toBeInTheDocument()` matchers are available globally (vitest setup) — do not import `@testing-library/jest-dom` per-file.
- **Pre-PR gates (run from `client/`):** `npx eslint .` (0 errors; warnings OK), `npm run build` (`tsc -b` over the app/node/test projects — exit 0, NOT `tsc --noEmit`), `npx vitest run`. The `tsconfig.test.json` already includes `src/vite-env.d.ts` (the `__DEVICE_MODE__` fix from #287) — do not remove it.
- **Line endings.** Repo is `core.autocrlf=true` on Windows; LF↔CRLF warnings on commit are expected and harmless.
- **Branch:** `feat/plugin-documentation-two-tier` (already created from `main` after #287 merge). The spec lives at `docs/superpowers/specs/2026-06-28-plugin-documentation-two-tier-design.md`.

---

## File Structure

- `client/src/i18n/locales/en/plugins.json` — add `tiers.*` block; reword three reused `docs.*` values; remove the stale `docs.*` / `hooks.*` / `hookCategories.*` keys.
- `client/src/i18n/locales/de/plugins.json` — same changes, German values.
- `client/src/components/plugins/PluginDocumentation.tsx` — full rewrite: new `scopeCatalog` prop, six sections (reframed banner, trust-tier cards, capability scopes, reframed install, condensed bundled permission grid, condensed hooks summary, version footer), hooks-grid machinery removed.
- `client/src/pages/PluginsPage.tsx` — pass `scopeCatalog={scopeCatalog}` to `<PluginDocumentation>` (one line).
- `client/src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx` — NEW vitest.

---

### Task 1: i18n additions (new `tiers.*` block + reworded reused values)

Add the new keys and reword the three reused strings, in both locale files. **No removals in this task** — the current component still references the stale keys until Task 2 rewrites it.

**Files:**
- Modify: `client/src/i18n/locales/en/plugins.json`
- Modify: `client/src/i18n/locales/de/plugins.json`

**Interfaces:**
- Consumes: nothing.
- Produces: i18n keys the Task 2 rewrite renders — `tiers.title`, `tiers.bundled.{label,description}`, `tiers.external.{label,description}`, `tiers.scopesTitle`, `tiers.scopesIntro`, `tiers.scopesUnavailable`, `tiers.installTitle`, `tiers.installExternal`, `tiers.installBundled`, `tiers.bundledOnlyPerms`; plus reworded values for the unchanged keys `docs.securityWarning`, `docs.securityWarningDescription`, `docs.permissionsDescription`.

- [ ] **Step 1: Read the German locale to learn its structure**

Run: Read `client/src/i18n/locales/de/plugins.json` in full. Note the order/placement of the `docs`, `scopeTiers`, `picker`, and `scopeDescriptions` blocks so the new `tiers` block is inserted consistently (place `tiers` adjacent to `scopeTiers`).

- [ ] **Step 2: Add the `tiers` block to the English locale**

In `client/src/i18n/locales/en/plugins.json`, add this top-level block (place it next to the existing `scopeTiers` block, with a comma to keep valid JSON):

```json
  "tiers": {
    "title": "Trust tiers",
    "bundled": {
      "label": "Bundled (in-process, trusted)",
      "description": "Ship with BaluHost and run as Python inside the server with full host access (the permission model below). Maintained in-repo."
    },
    "external": {
      "label": "External (sandboxed)",
      "description": "Marketplace plugins run in an isolated subprocess as a low-privilege user with no network, reaching the host only through the capability scopes you grant — no host code, database, filesystem, or shell access."
    },
    "scopesTitle": "Capability scopes",
    "scopesIntro": "When you enable an external plugin, you grant a subset of these scopes in the enable dialog. Each scope is enforced by the sandbox.",
    "scopesUnavailable": "The scope catalog is currently unavailable.",
    "installTitle": "Installing & enabling",
    "installExternal": "Install external plugins from the Marketplace tab (downloaded and checksum-verified). When you enable one, pick which of its requested capability scopes to grant.",
    "installBundled": "Bundled plugins ship with BaluHost; enabling one grants its declared permissions via the permission dialog.",
    "bundledOnlyPerms": "High-risk permissions (bundled plugins only)"
  },
```

- [ ] **Step 3: Reword the three reused English values**

In the same file's `docs` block, replace these three values (keys unchanged):

```json
    "securityWarning": "Heads Up — Plugins Run at Two Trust Levels",
    "securityWarningDescription": "Bundled plugins ship with BaluHost and run in-process with full host access. External marketplace plugins are sandboxed, but you still grant them capability scopes — only install and grant what you trust.",
```

and:

```json
    "permissionsDescription": "Bundled plugins declare which permissions they need. Dangerous permissions (marked in orange) give broad system access — only grant them to bundled plugins you trust.",
```

- [ ] **Step 4: Add the `tiers` block to the German locale**

In `client/src/i18n/locales/de/plugins.json`, add the mirrored block (placed next to `scopeTiers`):

```json
  "tiers": {
    "title": "Vertrauensstufen",
    "bundled": {
      "label": "Bundled (In-Process, vertraut)",
      "description": "Werden mit BaluHost ausgeliefert und laufen als Python im Server mit vollem Host-Zugriff (das Berechtigungsmodell unten). Werden im Repo gepflegt."
    },
    "external": {
      "label": "Extern (Sandbox)",
      "description": "Marketplace-Plugins laufen in einem isolierten Subprozess als Benutzer mit minimalen Rechten ohne Netzwerk und erreichen den Host nur über die Capability-Scopes, die du gewährst — kein Host-Code-, Datenbank-, Dateisystem- oder Shell-Zugriff."
    },
    "scopesTitle": "Capability-Scopes",
    "scopesIntro": "Wenn du ein externes Plugin aktivierst, gewährst du im Aktivierungsdialog eine Teilmenge dieser Scopes. Jeder Scope wird von der Sandbox erzwungen.",
    "scopesUnavailable": "Der Scope-Katalog ist derzeit nicht verfügbar.",
    "installTitle": "Installieren & Aktivieren",
    "installExternal": "Installiere externe Plugins über den Marketplace-Tab (heruntergeladen und per Prüfsumme verifiziert). Beim Aktivieren wählst du aus, welche der angeforderten Capability-Scopes du gewährst.",
    "installBundled": "Bundled-Plugins werden mit BaluHost ausgeliefert; beim Aktivieren werden ihre deklarierten Berechtigungen über den Berechtigungsdialog gewährt.",
    "bundledOnlyPerms": "Risikoreiche Berechtigungen (nur Bundled)"
  },
```

- [ ] **Step 5: Reword the three reused German values**

In the German `docs` block, replace:

```json
    "securityWarning": "Achtung — Plugins laufen auf zwei Vertrauensstufen",
    "securityWarningDescription": "Bundled-Plugins werden mit BaluHost ausgeliefert und laufen In-Process mit vollem Host-Zugriff. Externe Marketplace-Plugins laufen in einer Sandbox, aber du gewährst ihnen trotzdem Capability-Scopes — installiere und gewähre nur, was du vertraust.",
```

and:

```json
    "permissionsDescription": "Bundled-Plugins deklarieren, welche Berechtigungen sie benötigen. Gefährliche Berechtigungen (orange markiert) gewähren weitreichenden Systemzugriff — gewähre sie nur Bundled-Plugins, denen du vertraust.",
```

(Match the existing German key names exactly — if the German `permissionsDescription` value differs verbatim from the English placement, replace by key, not by matching the English text.)

- [ ] **Step 6: Verify both JSON files parse**

Run (from `client/`): `node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/plugins.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/plugins.json','utf8')); console.log('OK')"`
Expected: `OK` (no SyntaxError).

- [ ] **Step 7: Run the build and existing tests to confirm nothing broke**

Run (from `client/`): `npm run build`
Expected: exit 0 (the new keys are unused so far; that is fine — unused JSON keys do not fail the build).

Run (from `client/`): `npx vitest run src/__tests__/pages/PluginsPage.scopePicker.test.tsx`
Expected: PASS (rewording reused values does not change asserted keys).

- [ ] **Step 8: Commit**

```bash
git add client/src/i18n/locales/en/plugins.json client/src/i18n/locales/de/plugins.json
git commit -m "i18n(plugins): add tiers.* doc strings, reframe security/permissions copy (two-tier doc)"
```

---

### Task 2: Component rewrite + prop threading + new vitest (TDD)

Write the failing test first, then rewrite the component to satisfy it, thread the new prop through `PluginsPage`, and drop the hooks-grid machinery and now-unused icon imports.

**Files:**
- Create: `client/src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx`
- Modify (full rewrite): `client/src/components/plugins/PluginDocumentation.tsx`
- Modify: `client/src/pages/PluginsPage.tsx:253` (the `<PluginDocumentation permissions={allPermissions} />` render)

**Interfaces:**
- Consumes: `ScopeInfo` (`{ key: string; tier: 'frontend' | 'backend'; dangerous: boolean }`) and `PermissionInfo` from `client/src/api/plugins.ts`; the `tiers.*` keys from Task 1; the existing `scopeCatalog` state in `PluginsPage`.
- Produces: `PluginDocumentationProps { permissions: PermissionInfo[]; scopeCatalog: ScopeInfo[] }`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PluginDocumentation from '../../../components/plugins/PluginDocumentation';
import type { PermissionInfo, ScopeInfo } from '../../../api/plugins';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { returnObjects?: boolean }) =>
      opts?.returnObjects ? {} : key,
  }),
}));

vi.mock('../../../contexts/VersionContext', () => ({
  useFormattedVersion: () => 'BaluHost v1.37.0',
}));

const SCOPES: ScopeInfo[] = [
  { key: 'read:system-info', tier: 'frontend', dangerous: false },
  { key: 'read:storage', tier: 'frontend', dangerous: false },
  { key: 'read:power', tier: 'frontend', dangerous: false },
  { key: 'storage', tier: 'frontend', dangerous: false },
  { key: 'core.system_metrics', tier: 'backend', dangerous: false },
  { key: 'core.notify', tier: 'backend', dangerous: false },
];

const PERMISSIONS: PermissionInfo[] = [
  { name: 'file:read', value: 'file:read', dangerous: false, description: 'Read files' },
  { name: 'file:write', value: 'file:write', dangerous: true, description: 'Write files' },
];

describe('PluginDocumentation two-tier', () => {
  it('renders both trust-tier cards', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={SCOPES} />);
    expect(screen.getAllByText('tiers.bundled.label').length).toBeGreaterThan(0);
    expect(screen.getAllByText('tiers.external.label').length).toBeGreaterThan(0);
  });

  it('renders every catalog scope grouped under its tier heading', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={SCOPES} />);
    for (const scope of SCOPES) {
      expect(screen.getAllByText(scope.key).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('scopeTiers.frontend')).toBeInTheDocument();
    expect(screen.getByText('scopeTiers.backend')).toBeInTheDocument();
  });

  it('shows the unavailable note when the scope catalog is empty', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={[]} />);
    expect(screen.getByText('tiers.scopesUnavailable')).toBeInTheDocument();
    expect(screen.queryByText('scopeTiers.frontend')).not.toBeInTheDocument();
  });

  it('renders the condensed bundled permission reference', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={SCOPES} />);
    expect(screen.getByText('file:read')).toBeInTheDocument();
    expect(screen.getAllByText('file:write').length).toBeGreaterThan(0);
  });
});
```

> Note: `getAllByText` is used for `tiers.bundled.label` / `tiers.external.label` (each appears in both the tier card and the install section), for scope keys (under the `t: k=>k` stub the `<code>` and the label fallback both render the raw key), and for `file:write` (appears in both the security banner and the permission grid).

- [ ] **Step 2: Run the test to verify it fails**

Run (from `client/`): `npx vitest run src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx`
Expected: FAIL — the current component does not accept a `scopeCatalog` prop and renders neither the tier cards nor the scope catalog (likely a type error on the prop and/or missing-text assertion failures).

- [ ] **Step 3: Rewrite the component**

Replace the ENTIRE contents of `client/src/components/plugins/PluginDocumentation.tsx` with:

```tsx
/**
 * Plugin Documentation Component
 *
 * Operator-focused reference for the plugin system: the two trust tiers
 * (bundled in-process/trusted vs external sandboxed), the external
 * capability-scope model (rendered from the live catalog), and a condensed
 * bundled-plugin reference.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  FileText,
  Shield,
  ShieldCheck,
  Boxes,
  Zap,
  Users,
  Database,
  Network,
  Server,
  Plug,
  Info,
  Store,
} from 'lucide-react';
import type { PermissionInfo, ScopeInfo } from '../../api/plugins';
import { useFormattedVersion } from '../../contexts/VersionContext';

interface PluginDocumentationProps {
  permissions: PermissionInfo[];
  scopeCatalog: ScopeInfo[];
}

// Permission category keys and their permissions (bundled plugins only).
const PERMISSION_CATEGORY_KEYS = ['file', 'system', 'network', 'database', 'user', 'device', 'events'] as const;

const PERMISSION_CATEGORY_DATA: Record<string, { icon: React.ElementType; permissions: string[] }> = {
  file: { icon: FileText, permissions: ['file:read', 'file:write', 'file:delete'] },
  system: { icon: Server, permissions: ['system:info', 'system:execute'] },
  network: { icon: Network, permissions: ['network:outbound'] },
  database: { icon: Database, permissions: ['db:read', 'db:write'] },
  user: { icon: Users, permissions: ['user:read', 'user:write'] },
  device: { icon: Plug, permissions: ['device:control'] },
  events: { icon: Zap, permissions: ['notification:send', 'task:background', 'event:subscribe', 'event:emit'] },
};

export default function PluginDocumentation({ permissions, scopeCatalog }: PluginDocumentationProps) {
  const { t } = useTranslation('plugins');
  const permissionMap = new Map(permissions.map((p) => [p.value, p]));
  const formattedVersion = useFormattedVersion('BaluHost');

  // Separator-safe scope-description lookup (scope keys contain ':' and '.').
  const scopeDescs = t('scopeDescriptions', { returnObjects: true }) as Record<
    string,
    { label: string; description: string }
  >;

  const permissionCategories = useMemo(() => {
    return PERMISSION_CATEGORY_KEYS.map((key) => ({
      key,
      label: t(`categories.${key}`),
      icon: PERMISSION_CATEGORY_DATA[key].icon,
      permissions: PERMISSION_CATEGORY_DATA[key].permissions,
    }));
  }, [t]);

  return (
    <div className="space-y-6">
      {/* 1. Security banner (reframed, two-tier) */}
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-amber-200">{t('docs.securityWarning')}</h3>
            <p className="mt-1 text-sm text-amber-200/80">{t('docs.securityWarningDescription')}</p>
            <div className="mt-3">
              <p className="text-xs font-medium text-amber-300">{t('tiers.bundledOnlyPerms')}:</p>
              <ul className="mt-1 text-xs text-amber-200/70 space-y-1">
                <li>• <code className="text-amber-300">file:write</code> - {t('docs.permissionDescFileWrite')}</li>
                <li>• <code className="text-amber-300">file:delete</code> - {t('docs.permissionDescFileDelete')}</li>
                <li>• <code className="text-amber-300">system:execute</code> - {t('docs.permissionDescSystemExecute')}</li>
                <li>• <code className="text-amber-300">db:write</code> - {t('docs.permissionDescDbWrite')}</li>
                <li>• <code className="text-amber-300">user:write</code> - {t('docs.permissionDescUserWrite')}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Trust tiers (centerpiece) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('tiers.title')}</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
              <h3 className="text-sm font-medium text-white">{t('tiers.bundled.label')}</h3>
            </div>
            <p className="text-sm text-slate-400">{t('tiers.bundled.description')}</p>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Boxes className="h-5 w-5 text-sky-400" />
              <h3 className="text-sm font-medium text-white">{t('tiers.external.label')}</h3>
            </div>
            <p className="text-sm text-slate-400">{t('tiers.external.description')}</p>
          </div>
        </div>
      </div>

      {/* 3. Capability scopes (external, from live catalog) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Boxes className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('tiers.scopesTitle')}</h2>
        </div>
        <p className="text-sm text-slate-400 mb-4">{t('tiers.scopesIntro')}</p>
        {scopeCatalog.length === 0 ? (
          <p className="text-sm text-slate-500">{t('tiers.scopesUnavailable')}</p>
        ) : (
          <div className="space-y-4">
            {(['frontend', 'backend'] as const).map((tier) => {
              const scopes = scopeCatalog.filter((s) => s.tier === tier);
              if (scopes.length === 0) return null;
              return (
                <div key={tier} className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {t(`scopeTiers.${tier}`)}
                  </div>
                  <ul className="space-y-2">
                    {scopes.map((scope) => {
                      const meta = scopeDescs?.[scope.key];
                      return (
                        <li key={scope.key} className="rounded-lg border border-slate-700 bg-slate-800/30 p-3">
                          <div className="flex items-center gap-2">
                            <code className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">{scope.key}</code>
                            <span className="text-sm font-medium text-white">{meta?.label ?? scope.key}</span>
                            {scope.dangerous && <AlertTriangle className="h-3 w-3 text-amber-400" />}
                          </div>
                          {meta?.description && <p className="text-xs text-slate-500 mt-1">{meta.description}</p>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. Installing & enabling (reframed) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Info className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('tiers.installTitle')}</h2>
        </div>
        <div className="space-y-4 text-sm text-slate-300">
          <div>
            <h3 className="font-medium text-white mb-1">{t('tiers.external.label')}</h3>
            <p className="text-slate-400">{t('tiers.installExternal')}</p>
          </div>
          <div>
            <h3 className="font-medium text-white mb-1">{t('tiers.bundled.label')}</h3>
            <p className="text-slate-400">{t('tiers.installBundled')}</p>
          </div>
          <div className="flex items-start gap-2 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
            <Store className="h-4 w-4 text-sky-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-sky-200/90">{t('docs.marketplaceHint')}</p>
          </div>
        </div>
      </div>

      {/* 5a. Bundled reference — permission categories (condensed) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.permissions')}</h2>
          <span className="text-xs text-slate-500">({permissions.length} {t('docs.available')})</span>
        </div>
        <p className="text-sm text-slate-400 mb-4">{t('docs.permissionsDescription')}</p>
        <div className="grid gap-4 md:grid-cols-2">
          {permissionCategories.map((category) => {
            const CategoryIcon = category.icon;
            const categoryPerms = category.permissions
              .map((p) => permissionMap.get(p))
              .filter((p): p is PermissionInfo => p !== undefined);

            if (categoryPerms.length === 0) return null;

            return (
              <div key={category.key} className="rounded-lg border border-slate-700 bg-slate-800/30 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CategoryIcon className="h-4 w-4 text-slate-400" />
                  <h3 className="text-sm font-medium text-white">{category.label}</h3>
                </div>
                <ul className="space-y-2">
                  {categoryPerms.map((perm) => (
                    <li key={perm.value} className="text-sm">
                      <div className="flex items-center gap-2">
                        <code
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            perm.dangerous
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : 'bg-slate-700 text-slate-300'
                          }`}
                        >
                          {perm.value}
                        </code>
                        {perm.dangerous && <AlertTriangle className="h-3 w-3 text-amber-400" />}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {t(`permissionDescriptions.${perm.value}`, { defaultValue: perm.description })}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      {/* 5b. Bundled reference — event hooks (summary + GitHub link) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center gap-2 mb-2">
          <Zap className="h-5 w-5 text-sky-400" />
          <h2 className="text-lg font-medium text-white">{t('docs.eventHooks')}</h2>
        </div>
        <p className="text-sm text-slate-400">
          {t('docs.eventHooksDescription')}{' '}
          <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-400 text-xs">event:subscribe</code>{' '}
          {t('docs.required')}.{' '}
          <a
            href="https://github.com/Xveyn/BaluHost"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-400 hover:underline"
          >
            {t('docs.documentationOnGitHub')}
          </a>
        </p>
      </div>

      {/* 6. Version footer (unchanged) */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-4 text-slate-400">
            <span>{formattedVersion}</span>
            <span className="text-slate-600">|</span>
            <span>Plugin API v1.0</span>
          </div>
          <a
            href="https://github.com/Xveyn/BaluHost"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-400 hover:underline text-xs"
          >
            {t('docs.documentationOnGitHub')}
          </a>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Thread the prop through `PluginsPage`**

In `client/src/pages/PluginsPage.tsx`, change the documentation-tab render (around line 253):

```tsx
      {/* Documentation Tab */}
      {activeTab === 'documentation' && (
        <PluginDocumentation permissions={allPermissions} scopeCatalog={scopeCatalog} />
      )}
```

(`scopeCatalog` state already exists on the page — no new state or fetch.)

- [ ] **Step 5: Run the new test to verify it passes**

Run (from `client/`): `npx vitest run src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 6: Run eslint on the changed files**

Run (from `client/`): `npx eslint src/components/plugins/PluginDocumentation.tsx src/pages/PluginsPage.tsx src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx`
Expected: 0 errors. (Confirms no leftover unused imports — `Folder`, `Bell`, `HardDrive`, `Activity`, `Smartphone`, `Key` must be gone; `useMemo` is still used by `permissionCategories`.)

- [ ] **Step 7: Run the build**

Run (from `client/`): `npm run build`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add client/src/components/plugins/PluginDocumentation.tsx client/src/pages/PluginsPage.tsx client/src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx
git commit -m "feat(plugins): rewrite Documentation tab tier-first with live scope catalog"
```

---

### Task 3: Remove now-unused i18n keys + final pre-PR gates

The rewrite dropped the old install/lifecycle/structure prose and the 26-hook grid, so those keys are now unused. Verify, then remove from both locales, and run the full gate suite.

**Files:**
- Modify: `client/src/i18n/locales/en/plugins.json`
- Modify: `client/src/i18n/locales/de/plugins.json`

**Interfaces:**
- Consumes: the rewritten component from Task 2 (which no longer references the removal-list keys).
- Produces: nothing downstream.

- [ ] **Step 1: Confirm the removal-list keys are unused by every `plugins`-namespace consumer**

The `plugins` namespace is consumed by exactly these components (verify by reading each — `grep`/`rg` are blocked by a repo hook): `client/src/pages/PluginsPage.tsx`, `client/src/components/plugins/PluginDocumentation.tsx`, `client/src/components/plugins/MarketplaceTab.tsx`, `client/src/components/plugins/PluginSettingsSection.tsx`. Read each and confirm NONE reference any of these keys:

```
docs.installation        docs.installationDesc
docs.systemOverview      docs.lifecycle
docs.discovery           docs.discoveryDesc
docs.registration        docs.registrationDesc
docs.permissionCheck     docs.permissionCheckDesc
docs.activation          docs.activationDesc
docs.pluginStructure     docs.pluginStructureManifest
docs.pluginStructureEntry docs.pluginStructureRoutes
docs.pluginStructureUI   docs.hooks
(entire blocks) hooks.*  hookCategories.*
```

If any key above IS still referenced anywhere, KEEP it and note the exception in the commit message. (Expected: all are unused — `PluginsPage` uses `tabs/marketplace/buttons/status/details/permissions/empty/modal/errors/dashboardPanel/confirm/ui/scopeTiers/scopeDescriptions/picker`; `MarketplaceTab` and `PluginSettingsSection` use `marketplace.*` / `settings.*`.) Do NOT remove keys the rewrite still uses: `docs.eventHooks`, `docs.eventHooksDescription`, `docs.required`, `docs.marketplaceHint`, `docs.permissions`, `docs.available`, `docs.permissionsDescription`, `docs.securityWarning(+Description)`, `docs.dangerousPermissions`, `docs.permissionDesc*`, `docs.documentationOnGitHub`, `categories.*`, `permissionDescriptions.*`, `scopeTiers.*`, `scopeDescriptions.*`.

- [ ] **Step 2: Remove the stale keys from the English locale**

In `client/src/i18n/locales/en/plugins.json`, delete from the `docs` block: `installation`, `installationDesc`, `systemOverview`, `lifecycle`, `discovery`, `discoveryDesc`, `registration`, `registrationDesc`, `permissionCheck`, `permissionCheckDesc`, `activation`, `activationDesc`, `pluginStructure`, `pluginStructureManifest`, `pluginStructureEntry`, `pluginStructureRoutes`, `pluginStructureUI`, `hooks`. Then delete the entire top-level `hooks` block and the entire top-level `hookCategories` block. Keep all other keys. Ensure the resulting JSON has no trailing/leading commas.

- [ ] **Step 3: Remove the same keys from the German locale**

Apply the identical deletions to `client/src/i18n/locales/de/plugins.json` (same key names; German values).

- [ ] **Step 4: Verify both JSON files parse**

Run (from `client/`): `node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/plugins.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/plugins.json','utf8')); console.log('OK')"`
Expected: `OK`.

- [ ] **Step 5: Run the three pre-PR gates**

Run (from `client/`): `npx eslint .`
Expected: 0 errors.

Run (from `client/`): `npm run build`
Expected: exit 0.

Run (from `client/`): `npx vitest run`
Expected: all tests PASS (including `PluginDocumentation.twoTier` and `PluginsPage.scopePicker`).

- [ ] **Step 6: Commit**

```bash
git add client/src/i18n/locales/en/plugins.json client/src/i18n/locales/de/plugins.json
git commit -m "i18n(plugins): drop stale install/lifecycle/hooks doc keys (unused after rewrite)"
```

---

## Self-Review

**1. Spec coverage:**
- §1 Security banner reframed → Task 2 Step 3 (banner section, `tiers.bundledOnlyPerms` prefix, reworded `docs.securityWarning*` from Task 1). ✓
- §2 Trust Tiers (NEW) → Task 2 Step 3 (two-card `md:grid-cols-2`, `ShieldCheck`/`Boxes`, `tiers.title`). ✓
- §3 Capability Scopes (NEW, live catalog, grouped by tier, separator-safe lookup, conditional danger flag) → Task 2 Step 3. ✓
- §4 Installing & enabling reframed → Task 2 Step 3 (`tiers.install*` + `docs.marketplaceHint`). ✓
- §5 Bundled reference condensed (keep permission grid, hooks grid → summary + GitHub link, remove hooks machinery) → Task 2 Step 3 + removal in Task 3. ✓
- §6 Version footer unchanged → Task 2 Step 3. ✓
- i18n add `tiers.*` (de+en) → Task 1; remove stale keys → Task 3. ✓
- Error handling (empty catalog → `tiers.scopesUnavailable`; missing `scopeDescs[key]` → fallback) → Task 2 Step 3 + test Step 1. ✓
- Prop threading (no new fetch) → Task 2 Step 4. ✓
- Testing (centralized path, key assertions, 4 cases) → Task 2 Step 1. ✓
- Pre-PR gates → Task 3 Step 5. ✓

**2. Placeholder scan:** No TBD/TODO/"add error handling" — all code shown in full, all commands concrete with expected output.

**3. Type consistency:** `PluginDocumentationProps { permissions: PermissionInfo[]; scopeCatalog: ScopeInfo[] }` matches the test's `render(<PluginDocumentation permissions={...} scopeCatalog={...} />)` and `PluginsPage`'s `scopeCatalog` state type (`ScopeInfo[]`). `scopeDescs` typed `Record<string, { label; description }>` matches the picker. Tier literal `('frontend'|'backend')` matches `ScopeInfo.tier` and `scopeTiers.*`. Removal list (Task 3) is disjoint from the keep list and from keys the rewrite uses.

**Decomposition note:** The spec listed 4 tasks; prop-threading was merged into the component rewrite (Task 2) because an unused `scopeCatalog` prop would fail the eslint `no-unused-vars` gate on its own — the two are not independently shippable. i18n-add (Task 1) precedes the rewrite so no fallback-key intermediate state ships; i18n-removal (Task 3) follows the rewrite so keys are genuinely unused when deleted.
