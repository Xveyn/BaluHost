# Update Page → GitHub Releases — Frontend Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the update page's release notes + check changelog from the new curated **markdown** contracts (via `react-markdown`), show a "from CHANGELOG (offline)" hint, and remove the dead development-channel UI. Consumes the Plan-1 backend.

**Architecture:** `UpdateOverviewTab` is a presentational component fed by `UpdatePage`. Swap its categorized-commit rendering for `<Markdown>{body_markdown}</Markdown>` blocks (same `prose` pattern as the manual `ArticleView`), drop the dev-update card/props, and mirror the reshaped API types.

**Tech Stack:** React + TypeScript + Vite, `react-markdown` (already a dependency), Vitest.

Spec: `docs/superpowers/specs/2026-06-06-update-page-github-releases-design.md`. Backend = Plan 1 (done).

---

## File Structure

| File | Change |
|---|---|
| `client/src/api/updates.ts` | reshape `ReleaseNotesResponse` + `ReleaseNoteItem`; `ChangelogEntry.body_markdown`; extend `ReleaseInfo`; drop `UpdateCheckResponse.dev_*`, `DevUpdateStartRequest`, `startDevUpdate` |
| `client/src/components/updates/UpdateOverviewTab.tsx` | markdown rendering; remove dev-channel UI + props; `source` hint |
| `client/src/components/updates/UpdateHistoryTab.tsx` | releases list: drop now-empty `commit_short`, add GitHub link |
| `client/src/pages/UpdatePage.tsx` | remove dev-update state/handlers/props |
| `client/src/i18n/locales/{de,en}/updates.json` | `releaseNotes.fromChangelog` + `releaseNotes.viewOnGitHub` |
| `client/src/__tests__/components/updates/UpdateOverviewTab.test.tsx` | NEW |

---

## Task 1: API types

**Files:**
- Modify: `client/src/api/updates.ts`

- [ ] **Step 1: Reshape the release-notes + changelog + release types**

In `client/src/api/updates.ts`:

(a) Add `body_markdown` to `ChangelogEntry` (after `is_prerelease`):

```typescript
  body_markdown?: string | null;
```

(b) In `UpdateCheckResponse`, delete the four dev fields:

```typescript
  dev_version_available: boolean;
  dev_version: VersionInfo | null;
  dev_commits_ahead: number | null;
  dev_commits: CommitInfo[];
```

(c) Delete the `DevUpdateStartRequest` interface and the `startDevUpdate` function (the
`export async function startDevUpdate(...)` block).

(d) Replace the `ReleaseNoteCategory` + `ReleaseNotesResponse` block with:

```typescript
export interface ReleaseNoteItem {
  version: string;
  date: string | null;
  is_prerelease: boolean;
  url: string | null;
  body_markdown: string;
}

export interface ReleaseNotesResponse {
  current_version: string;
  since_version: string | null;
  source: 'github' | 'changelog';
  releases: ReleaseNoteItem[];
}
```

(e) Extend `ReleaseInfo` (add fields, make `commit_short` nullable):

```typescript
export interface ReleaseInfo {
  tag: string;
  version: string;
  date: string | null;
  is_prerelease: boolean;
  commit_short: string | null;
  name: string | null;
  html_url: string | null;
  body_markdown: string | null;
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: errors ONLY in `UpdateOverviewTab.tsx` / `UpdatePage.tsx` (they still reference the removed
fields/functions) — those are fixed in Tasks 2 & 3. No errors in `updates.ts` itself.

- [ ] **Step 3: Commit**

```bash
git add client/src/api/updates.ts
git commit -m "feat(updates): mirror GitHub-releases contracts in the API client"
```

---

## Task 2: UpdateOverviewTab — markdown rendering, drop dev UI

**Files:**
- Modify: `client/src/components/updates/UpdateOverviewTab.tsx`
- Test: `client/src/__tests__/components/updates/UpdateOverviewTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/updates/UpdateOverviewTab.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import UpdateOverviewTab from '../../../components/updates/UpdateOverviewTab';
import type { ReleaseNotesResponse } from '../../../api/updates';

const t = (k: string) => k;

const baseProps = {
  t,
  checkResult: null,
  currentUpdate: null,
  updateLoading: false,
  rollbackLoading: false,
  cancelLoading: false,
  showUpdateConfirm: false,
  onSetShowUpdateConfirm: vi.fn(),
  onSetShowRollbackConfirm: vi.fn(),
  onStartUpdate: vi.fn(),
  onCancel: vi.fn(),
};

function notes(source: 'github' | 'changelog'): ReleaseNotesResponse {
  return {
    current_version: '1.36.0',
    since_version: '1.35.0',
    source,
    releases: [
      { version: '1.36.0', date: null, is_prerelease: false, url: 'https://gh/r',
        body_markdown: '### Added\n- Shiny new thing' },
    ],
  };
}

describe('UpdateOverviewTab release notes', () => {
  it('renders the markdown body of each release', () => {
    render(<UpdateOverviewTab {...baseProps} releaseNotes={notes('github')} />);
    expect(screen.getByText('Shiny new thing')).toBeInTheDocument();
    expect(screen.queryByText('releaseNotes.fromChangelog')).not.toBeInTheDocument();
  });

  it('shows the CHANGELOG offline hint when source is changelog', () => {
    render(<UpdateOverviewTab {...baseProps} releaseNotes={notes('changelog')} />);
    expect(screen.getByText('releaseNotes.fromChangelog')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/updates/UpdateOverviewTab.test.tsx`
Expected: FAIL — the component still reads `releaseNotes.categories` (type error / no markdown), and its
props type still requires the dev props.

- [ ] **Step 3: Replace `UpdateOverviewTab.tsx` entirely**

Replace the **whole file** `client/src/components/updates/UpdateOverviewTab.tsx` with:

```tsx
import {
  Download,
  CheckCircle,
  AlertTriangle,
  GitBranch,
  Clock,
  Loader2,
  Zap,
  FileText,
  Package,
} from 'lucide-react';
import Markdown from 'react-markdown';
import type { UpdateCheckResponse, ReleaseNotesResponse } from '../../api/updates';
import { isUpdateInProgress, type UpdateProgressResponse } from '../../api/updates';
import UpdateProgress from './UpdateProgress';

const PROSE =
  'prose prose-invert prose-slate max-w-none prose-sm ' +
  'prose-headings:text-white prose-h2:text-base prose-h3:text-sm ' +
  'prose-p:text-slate-300 prose-li:text-slate-300 prose-strong:text-white ' +
  'prose-a:text-blue-400 prose-code:text-cyan-400';

interface UpdateOverviewTabProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  checkResult: UpdateCheckResponse | null;
  currentUpdate: UpdateProgressResponse | null;
  releaseNotes: ReleaseNotesResponse | null;
  updateLoading: boolean;
  rollbackLoading: boolean;
  cancelLoading: boolean;
  showUpdateConfirm: boolean;
  onSetShowUpdateConfirm: (show: boolean) => void;
  onSetShowRollbackConfirm: (show: boolean) => void;
  onStartUpdate: () => void;
  onCancel: () => void;
}

export default function UpdateOverviewTab({
  t,
  checkResult,
  currentUpdate,
  releaseNotes,
  updateLoading,
  rollbackLoading,
  cancelLoading,
  showUpdateConfirm,
  onSetShowUpdateConfirm,
  onSetShowRollbackConfirm,
  onStartUpdate,
  onCancel,
}: UpdateOverviewTabProps) {
  return (
    <div className="space-y-6">
      {/* Current Update Progress */}
      {currentUpdate && isUpdateInProgress(currentUpdate.status) && (
        <UpdateProgress
          progress={currentUpdate}
          onRollback={() => onSetShowRollbackConfirm(true)}
          rollbackLoading={rollbackLoading}
          onCancel={onCancel}
          cancelLoading={cancelLoading}
        />
      )}

      {/* Version Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Current Version */}
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <div className="flex items-center gap-2 mb-4">
            <Package className="h-5 w-5 text-slate-400" />
            <h3 className="font-medium text-white">{t('version.current')}</h3>
          </div>
          {checkResult && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-3xl font-bold text-white">
                  v{checkResult.current_version.version}
                </span>
                {checkResult.current_version.is_prerelease && (
                  <span className="ml-2 inline-flex items-center rounded-md bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
                    {t('preRelease.badge')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <GitBranch className="h-4 w-4" />
                <span className="font-mono">{checkResult.current_version.commit_short}</span>
                {checkResult.current_version.tag && (
                  <span className="px-2 py-0.5 bg-slate-700 rounded text-xs">
                    {checkResult.current_version.tag}
                  </span>
                )}
              </div>
              {checkResult.current_version.is_dev_build ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 rounded text-xs font-medium">
                    {t('version.devBuild')}
                  </span>
                </div>
              ) : !checkResult.current_version.is_prerelease ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-emerald-400">{t('version.stable')}</span>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Available Update */}
        <div
          className={`bg-slate-800 rounded-lg p-5 border ${
            checkResult?.update_available ? 'border-blue-500/50 bg-blue-500/5' : 'border-slate-700'
          }`}
        >
          <div className="flex items-center gap-2 mb-4">
            {checkResult?.update_available ? (
              <Zap className="h-5 w-5 text-blue-400" />
            ) : (
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            )}
            <h3 className="font-medium text-white">
              {checkResult?.update_available ? t('version.available') : t('version.upToDate')}
            </h3>
          </div>
          {checkResult?.update_available && checkResult.latest_version ? (
            <div className="space-y-3">
              <div className="text-3xl font-bold text-blue-400">
                v{checkResult.latest_version.version}
              </div>
              {checkResult.last_checked && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Clock className="h-3 w-3" />
                  {t('version.lastChecked')} {new Date(checkResult.last_checked).toLocaleString()}
                </div>
              )}
            </div>
          ) : (
            <p className="text-slate-400">{t('version.upToDateDesc')}</p>
          )}
        </div>
      </div>

      {/* Blockers Warning */}
      {checkResult?.blockers && checkResult.blockers.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5" />
            <div>
              <h4 className="font-medium text-amber-400">{t('blockers.title')}</h4>
              <ul className="mt-2 space-y-1 text-sm text-slate-300">
                {checkResult.blockers.map((blocker, i) => (
                  <li key={i}>• {blocker}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Release Notes (markdown, since last stable) */}
      {releaseNotes && releaseNotes.releases.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <div className="flex flex-wrap items-center gap-3 mb-1">
            <FileText className="h-5 w-5 text-blue-400" />
            <h3 className="font-medium text-white">{t('releaseNotes.title')}</h3>
            <span className="text-sm font-mono text-slate-400">v{releaseNotes.current_version}</span>
            {releaseNotes.source === 'changelog' && (
              <span className="text-xs text-amber-400/80">{t('releaseNotes.fromChangelog')}</span>
            )}
          </div>
          {releaseNotes.since_version && (
            <p className="text-sm text-slate-500 mb-4 ml-8">
              {t('releaseNotes.since', { version: releaseNotes.since_version })}
            </p>
          )}
          <div className="space-y-5 ml-8">
            {releaseNotes.releases.map((r) => (
              <div key={r.version}>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="font-medium text-white">v{r.version}</span>
                  {r.is_prerelease && (
                    <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded">
                      {t('preRelease.badge')}
                    </span>
                  )}
                  {r.date && (
                    <span className="text-xs text-slate-500">
                      {new Date(r.date).toLocaleDateString()}
                    </span>
                  )}
                  {r.url && (
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:underline"
                    >
                      {t('releaseNotes.viewOnGitHub')}
                    </a>
                  )}
                </div>
                <div className={PROSE}>
                  <Markdown>{r.body_markdown}</Markdown>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Changelog (what an update brings) */}
      {checkResult?.update_available && checkResult.changelog.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <h3 className="font-medium text-white mb-4">{t('changelog.title')}</h3>
          <div className="space-y-4">
            {checkResult.changelog.map((entry, i) => (
              <div key={i} className="border-l-2 border-blue-500/50 pl-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-white">v{entry.version}</span>
                  {entry.is_prerelease && (
                    <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded">
                      {t('changelog.prerelease')}
                    </span>
                  )}
                </div>
                {entry.body_markdown && (
                  <div className={PROSE}>
                    <Markdown>{entry.body_markdown}</Markdown>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Update Button */}
      {checkResult?.update_available && (
        <div className="flex justify-end gap-3">
          {!showUpdateConfirm ? (
            <button
              onClick={() => onSetShowUpdateConfirm(true)}
              disabled={!checkResult.can_update || updateLoading || !!currentUpdate}
              className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-all touch-manipulation active:scale-95 font-medium"
            >
              <Download className="h-5 w-5" />
              {t('buttons.updateTo', { version: checkResult.latest_version?.version })}
            </button>
          ) : (
            <div className="flex items-center gap-3 p-3 bg-slate-700 rounded-lg">
              <span className="text-sm text-slate-300">{t('buttons.confirmUpdate')}</span>
              <button
                onClick={onStartUpdate}
                disabled={updateLoading}
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-all touch-manipulation active:scale-95"
              >
                {updateLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : t('buttons.yesUpdate')}
              </button>
              <button
                onClick={() => onSetShowUpdateConfirm(false)}
                className="px-4 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-sm transition-all touch-manipulation active:scale-95"
              >
                {t('common:cancel')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/updates/UpdateOverviewTab.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/updates/UpdateOverviewTab.tsx client/src/__tests__/components/updates/UpdateOverviewTab.test.tsx
git commit -m "feat(updates): render release notes as markdown; drop dev-channel UI"
```

---

## Task 3: UpdatePage — remove dev-update wiring

**Files:**
- Modify: `client/src/pages/UpdatePage.tsx`

- [ ] **Step 1: Drop the `startDevUpdate` import**

In `client/src/pages/UpdatePage.tsx`, remove `startDevUpdate,` from the
`from '../api/updates'` import block.

- [ ] **Step 2: Remove the dev state**

Delete these two state lines:

```typescript
  const [showDevUpdateConfirm, setShowDevUpdateConfirm] = useState(false);
  const [devUpdateLoading, setDevUpdateLoading] = useState(false);
```

- [ ] **Step 3: Remove the `handleStartDevUpdate` handler**

Delete the entire `// Start dev update` / `const handleStartDevUpdate = async () => { ... };` block.

- [ ] **Step 4: Remove the dev props from `<UpdateOverviewTab>`**

In the `<UpdateOverviewTab ... />` render, delete these four props:

```tsx
          devUpdateLoading={devUpdateLoading}
          showDevUpdateConfirm={showDevUpdateConfirm}
          onSetShowDevUpdateConfirm={setShowDevUpdateConfirm}
          onStartDevUpdate={handleStartDevUpdate}
```

- [ ] **Step 5: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: PASS (no errors anywhere now).

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/UpdatePage.tsx
git commit -m "refactor(updates): remove dev-channel update wiring from UpdatePage"
```

---

## Task 4: i18n keys

**Files:**
- Modify: `client/src/i18n/locales/de/updates.json`
- Modify: `client/src/i18n/locales/en/updates.json`

- [ ] **Step 1: Add the two new keys to the `releaseNotes` object (German)**

In `client/src/i18n/locales/de/updates.json`, inside the existing `"releaseNotes"` object (next to its
`"since"` key), add:

```json
    "fromChangelog": "aus CHANGELOG (offline)",
    "viewOnGitHub": "Auf GitHub ansehen"
```

- [ ] **Step 2: Add them in English**

In `client/src/i18n/locales/en/updates.json`, inside `"releaseNotes"`:

```json
    "fromChangelog": "from CHANGELOG (offline)",
    "viewOnGitHub": "View on GitHub"
```

- [ ] **Step 3: Validate JSON**

Run:
```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/updates.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/updates.json','utf8')); console.log('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/updates.json client/src/i18n/locales/en/updates.json
git commit -m "i18n(updates): release-notes source hint + GitHub link (de/en)"
```

---

## Task 5: UpdateHistoryTab — releases list (GitHub link, null-safe)

**Files:**
- Modify: `client/src/components/updates/UpdateHistoryTab.tsx`

> Context: the releases list now comes from GitHub, so `commit_short` is usually `null` (React renders
> it as empty — no crash, but a dangling empty span). Replace it with a "View on GitHub" link.

- [ ] **Step 1: Replace the release row's left block**

In `client/src/components/updates/UpdateHistoryTab.tsx`, find:

```tsx
                <div className="flex items-center gap-3">
                  <span className="font-mono text-white">{release.tag}</span>
                  <span className="font-mono text-xs text-slate-500">{release.commit_short}</span>
                </div>
```

and replace it with:

```tsx
                <div className="flex items-center gap-3">
                  <span className="font-mono text-white">{release.tag}</span>
                  {release.html_url && (
                    <a
                      href={release.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:underline"
                    >
                      {t('releaseNotes.viewOnGitHub')}
                    </a>
                  )}
                </div>
```

(`releaseNotes.viewOnGitHub` was added in Task 4 and lives in the same `updates` namespace.)

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/updates/UpdateHistoryTab.tsx
git commit -m "feat(updates): releases list links to GitHub (commit_short now nullable)"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run the new test + full vitest suite**

Run: `cd client && npx vitest run`
Expected: all green (incl. the new `UpdateOverviewTab.test.tsx`).

- [ ] **Step 2: Production build (type-check)**

Run: `cd client && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke (dev)**

1. `python start_dev.py`, login as admin → Updates page → Overview.
2. Release Notes card shows the dev backend's **markdown** body (a "Added" heading + bullet), no
   category icons, no "Install dev version" button.
3. (Against the public repo / prod) the notes show GitHub bodies since the last stable; if GitHub is
   blocked, a "from CHANGELOG (offline)" hint appears.

- [ ] **Step 4: No commit** (verification only).

---

## Notes for the implementer

- **`react-markdown`** is already a dependency (used by the manual `ArticleView` as `import Markdown from 'react-markdown'`). No raw-HTML plugin → GitHub bodies render safely.
- The dev-channel i18n strings (`version.devVersionAvailable`, `version.devCommitsAhead`, `version.devWarning`, `buttons.installDevVersion`, `buttons.confirmDevInstall`, `toast.devUpdateStarted`) become unused after this change — leave them (harmless) unless asked to prune.
- `commit_short` on the latest version may be an empty string from the GitHub path — the Available card no longer renders it, so no "undefined" leaks.
- The `'development'` value stays in the `UpdateChannel` TS union (matches the backend enum kept for config compatibility); only the dev-*update* path is gone.
```
