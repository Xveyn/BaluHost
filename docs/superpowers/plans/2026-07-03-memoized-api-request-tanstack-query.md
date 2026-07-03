# memoizedApiRequest → TanStack Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den In-Memory-Map-Cache (`apiCache`/`memoizedApiRequest`) in `client/src/lib/api.ts` ersatzlos entfernen und seine 3 Konsumenten (Backups, Shares, File-Permissions) auf TanStack Query bzw. Plain-Reads migrieren — schließt den #299-Bullet und #309/F6 vollständig.

**Architecture:** Reads werden `useQuery`-Hooks (`useBackups`, `useFileShares`) mit Keys aus `lib/queryKeys.ts`; Mutationen werden `useMutation` + `invalidateQueries` (erstes Mutation-Muster im Frontend). Share-Invalidierung lebt **in den Modals** (zentrale Semantik wie der alte `apiCache.delete`). File-Permissions werden ein Plain-Read ohne Query-Beteiligung. `AuthContext` leert den Query-Cache bei **jedem** Identitätswechsel (5 Pfade), damit user-scoped Queries nie über den Persister leaken.

**Tech Stack:** React 18, TypeScript strict, `@tanstack/react-query` v5 (installiert), Vitest + Testing Library, axios (`apiClient`).

**Spec:** `docs/superpowers/specs/2026-07-03-memoized-api-request-tanstack-query-design.md`

## Global Constraints

- Branch: `feat/tanstack-query-memoized-cache-299` (existiert bereits, Spec liegt darauf).
- Shell ist PowerShell 5.1: **niemals `&&`** — Befehle mit `;` verketten.
- Repo läuft mit `core.autocrlf=true` — CRLF-Warnungen beim Commit sind normal.
- Öffentliche Hook-/API-Signaturen stabil halten, wo Konsumenten existieren (Approach A aus #299). Ausnahme: `getBackup` wird gelöscht (toter Code, null Konsumenten).
- Query-Keys IMMER aus `lib/queryKeys.ts` — nie inline-Arrays.
- Kein neuer `refetchInterval` für Backups/Shares (Admin-/On-Demand-Daten; Mutationen invalidieren).
- Vor dem PR müssen ALLE drei Gates grün sein: `npx vitest run`, `npx eslint .` (0 Errors), `npm run build` (tsc -b, prüft auch das Test-Projekt).
- Alle Frontend-Kommandos laufen aus `client/`: `cd "D:\Programme (x86)\Baluhost\client"`.
- Commits: konventionelle Prefixe (`feat(client):`, `refactor(client):`, `test(client):`, `docs(client):`), Referenz `(#299)`.

---

### Task 1: Query-Keys für backups + shares

**Files:**
- Modify: `client/src/lib/queryKeys.ts`
- Test: `client/src/__tests__/lib/query-foundation.test.ts`

**Interfaces:**
- Produces: `queryKeys.backups.list(): readonly ['backups','list']`; `queryKeys.shares.all(): readonly ['shares']`; `queryKeys.shares.userShares(): readonly ['shares','user-shares']`; `queryKeys.shares.sharedWithMe(): readonly ['shares','shared-with-me']`; `queryKeys.shares.statistics(): readonly ['shares','statistics']`. Alle späteren Tasks nutzen exakt diese Namen.

- [ ] **Step 1: Failing Tests schreiben**

In `client/src/__tests__/lib/query-foundation.test.ts` ans Dateiende (nach dem `queryKeys.raid`-describe) anhängen:

```ts
describe('queryKeys.backups', () => {
  it('builds the list key', () => {
    expect(queryKeys.backups.list()).toEqual(['backups', 'list']);
  });
});

describe('queryKeys.shares', () => {
  it('builds the domain prefix and entity keys', () => {
    expect(queryKeys.shares.all()).toEqual(['shares']);
    expect(queryKeys.shares.userShares()).toEqual(['shares', 'user-shares']);
    expect(queryKeys.shares.sharedWithMe()).toEqual(['shares', 'shared-with-me']);
    expect(queryKeys.shares.statistics()).toEqual(['shares', 'statistics']);
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/lib/query-foundation.test.ts`
Expected: FAIL — `queryKeys.backups is undefined` (Property existiert nicht).

- [ ] **Step 3: Keys implementieren**

In `client/src/lib/queryKeys.ts` nach dem `raid:`-Block (vor dem schließenden `} as const;`) einfügen:

```ts
  backups: {
    list: () => ['backups', 'list'] as const,
  },
  shares: {
    /** Domain-Prefix — invalidiert alle drei shares-Reads auf einmal. */
    all: () => ['shares'] as const,
    userShares: () => ['shares', 'user-shares'] as const,
    sharedWithMe: () => ['shares', 'shared-with-me'] as const,
    statistics: () => ['shares', 'statistics'] as const,
  },
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/lib/query-foundation.test.ts`
Expected: PASS (alle describe-Blöcke grün).

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/lib/queryKeys.ts client/src/__tests__/lib/query-foundation.test.ts; git commit -m "feat(client): query keys for backups + shares domains (#299)"
```

---

### Task 2: AuthContext — Cache-Leerung bei jedem Identitätswechsel

**Files:**
- Modify: `client/src/contexts/AuthContext.tsx`
- Test: `client/src/__tests__/contexts/AuthContext.impersonation.test.tsx`
- Test: `client/src/__tests__/contexts/AuthContext.logout.test.tsx`

**Interfaces:**
- Consumes: `queryClient` aus `lib/queryClient`, `queryPersister` aus `lib/queryPersister` (beide bereits importiert).
- Produces: keine neue öffentliche API — `login/logout/impersonate/endImpersonation` behalten ihre Signaturen; sie leeren jetzt zusätzlich den Query-Cache.

**Kontext:** Sobald user-scoped Queries existieren (Task 7: `useFileShares`), darf der sessionStorage-Persister keine Daten des vorherigen Users an den nächsten leaken. Heute leert nur `logout()` (AuthContext.tsx:112-113). Fünf weitere Pfade müssen leeren — siehe Spec §3.6.

- [ ] **Step 1: Failing Tests schreiben (Impersonation)**

In `client/src/__tests__/contexts/AuthContext.impersonation.test.tsx`:

Nach den bestehenden `vi.mock(...)`-Blöcken (nach Zeile 12) und vor `import { impersonateUser } ...` einfügen:

```ts
import { queryClient } from '../../lib/queryClient';
import { queryPersister } from '../../lib/queryPersister';

vi.spyOn(queryClient, 'clear').mockImplementation(() => {});
vi.spyOn(queryPersister, 'removeClient').mockResolvedValue(undefined);
```

Im Test `'stores origin token and swaps to impersonation token'` ans Ende (nach `expect(ctx.user?.username).toBe('alice');`) anhängen:

```ts
    // Identity change → cached queries of the admin must not leak to alice
    expect(queryClient.clear).toHaveBeenCalled();
    expect(queryPersister.removeClient).toHaveBeenCalled();
```

Im Test `'endImpersonation restores the admin token'` ans Ende (nach `expect(ctx.user?.username).toBe('admin');`) anhängen:

```ts
    // Both swaps (impersonate + end) clear the cache
    expect(vi.mocked(queryClient.clear).mock.calls.length).toBeGreaterThanOrEqual(2);
```

- [ ] **Step 2: Failing Tests schreiben (login + auth:expired)**

In `client/src/__tests__/contexts/AuthContext.logout.test.tsx` innerhalb des `describe('AuthContext logout', ...)`-Blocks zwei Tests ergänzen (der Spy-Setup existiert dort bereits, Zeilen 8-9). Zusätzlich am Dateikopf den Typ-Import ergänzen:

```ts
import type { User } from '../../types/auth';
```

```ts
  it('login clears any cached data from a previous session', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    act(() => {
      result.current.login({ id: 1, username: 'bob', role: 'user' } as unknown as User, 'new-token');
    });
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
    expect(queryPersister.removeClient).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('token')).toBe('new-token');
  });

  it('auth:expired (plain, no impersonation) clears the query cache', () => {
    renderHook(() => useAuth(), { wrapper });
    act(() => {
      window.dispatchEvent(new CustomEvent('auth:expired'));
    });
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
    expect(queryPersister.removeClient).toHaveBeenCalledTimes(1);
  });
```

- [ ] **Step 3: Tests laufen lassen — müssen fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/contexts/AuthContext.impersonation.test.tsx src/__tests__/contexts/AuthContext.logout.test.tsx`
Expected: FAIL — `expected "clear" to be called at least once` (bzw. `toHaveBeenCalledTimes(1)` = 0 calls) in den 4 neuen/erweiterten Tests; die Bestandstests bleiben grün.

- [ ] **Step 4: `clearQueryCache`-Helfer + 5 Aufrufe implementieren**

In `client/src/contexts/AuthContext.tsx`:

**(a)** Nach der `fetchMe`-Funktion (nach Zeile 37) modulweiten Helfer einfügen:

```ts
/**
 * Drop all cached queries and the persisted sessionStorage blob.
 * MUST run on EVERY identity change (login, logout, impersonation swaps,
 * auth expiry) — user-scoped queries (#299) would otherwise leak across
 * users via the persister's F5 instant-paint.
 */
function clearQueryCache(): void {
  queryClient.clear();
  void queryPersister.removeClient();
}
```

**(b)** `login` (Zeile 96-100) — Leerung VOR dem Setzen der neuen Session:

```ts
  const login = (userData: User, newToken: string) => {
    // A previous session on this tab (e.g. ended via auth:expired) may have
    // left user-scoped data in the cache/persister — never show it to the
    // next account.
    clearQueryCache();
    localStorage.setItem('token', newToken);
    setToken(newToken);
    setUser(userData);
  };
```

**(c)** `logout` (Zeile 102-114) — die zwei Direktaufrufe durch den Helfer ersetzen:

```ts
  const logout = useCallback(() => {
    localStorage.removeItem('token');
    sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
    sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
    setImpersonationOrigin(null);
    setToken(null);
    setUser(null);
    // Drop any cached data for the ended session so a next login on the same
    // tab can't briefly show it before refetch (see clearQueryCache).
    clearQueryCache();
  }, []);
```

**(d)** `impersonate` (Zeile 116-131) — nach dem Token-Swap leeren (Reihenfolge: erst Token, dann leeren, damit die von `clear()` ausgelösten Refetches den neuen Token tragen):

```ts
    sessionStorage.setItem(ORIGIN_TOKEN_KEY, currentToken);
    sessionStorage.setItem(ORIGIN_USERNAME_KEY, currentUsername);
    localStorage.setItem('token', result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    setImpersonationOrigin(currentUsername);
    clearQueryCache();
```

**(e)** `endImpersonation` (Zeile 133-153) — nach dem Restore leeren:

```ts
    sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
    sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
    localStorage.setItem('token', originToken);
    setToken(originToken);
    setImpersonationOrigin(null);
    clearQueryCache();
```
(Der `if (!originToken) { logout(); return; }`-Frühausstieg leert bereits über `logout()`.)

**(f)** `auth:expired`-Handler (Zeile 156-182) — BEIDE Zweige leeren. Im Impersonation-Zweig nach `setImpersonationOrigin(null);`:

```ts
        setImpersonationOrigin(null);
        clearQueryCache();
```

Im Plain-Zweig:

```ts
      } else {
        setToken(null);
        setUser(null);
        clearQueryCache();
      }
```

- [ ] **Step 5: Tests laufen lassen — müssen bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/contexts/`
Expected: PASS — alle AuthContext-Tests (impersonation, logout inkl. der 2 neuen, der Bestand `AuthContext.test.tsx`).

- [ ] **Step 6: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/contexts/AuthContext.tsx client/src/__tests__/contexts/AuthContext.impersonation.test.tsx client/src/__tests__/contexts/AuthContext.logout.test.tsx; git commit -m "feat(client): clear query cache on every identity change, not just logout (#299)"
```

---

### Task 3: api/backup.ts — plain listBackups, toten getBackup löschen

**Files:**
- Modify: `client/src/api/backup.ts`
- Create: `client/src/__tests__/api/backup.test.ts`

**Interfaces:**
- Produces: `listBackups(): Promise<BackupListResponse>` (Signatur unverändert, intern plain GET). `getBackup` existiert danach NICHT mehr (war toter Code, kein Konsument — via Projektsuche verifiziert).

- [ ] **Step 1: Failing Test schreiben**

Create `client/src/__tests__/api/backup.test.ts` (Muster: `shares.test.ts`):

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { listBackups, createBackup, deleteBackup } from '../../api/backup';

vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  buildApiUrl: (p: string) => p,
}));

import { apiClient } from '../../lib/api';

describe('backup API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it('listBackups calls GET /api/backups/ directly (no memo cache)', async () => {
    const payload = { backups: [], total_size_bytes: 0, total_size_mb: 0 };
    vi.mocked(apiClient.get).mockResolvedValue({ data: payload });

    const result = await listBackups();

    expect(apiClient.get).toHaveBeenCalledWith('/api/backups/');
    expect(result).toEqual(payload);
  });

  it('createBackup posts the request body', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 1 } });

    await createBackup({ includes_database: true });

    expect(apiClient.post).toHaveBeenCalledWith('/api/backups/', { includes_database: true });
  });

  it('deleteBackup calls DELETE with the id', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({});

    await deleteBackup(7);

    expect(apiClient.delete).toHaveBeenCalledWith('/api/backups/7');
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/api/backup.test.ts`
Expected: FAIL — `listBackups` ruft `memoizedApiRequest` (nicht `apiClient.get`); der Mock liefert dafür `undefined` → `expect(apiClient.get).toHaveBeenCalledWith(...)` schlägt fehl. (Hinweis: die Mock-Factory exportiert bewusst KEIN `memoizedApiRequest` mehr — der Import in `backup.ts` wird dadurch `undefined` und der Test crasht kontrolliert. Beides zählt als erwarteter Fail.)

- [ ] **Step 3: backup.ts umbauen**

In `client/src/api/backup.ts`:

Import (Zeile 5) ändern zu:

```ts
import { apiClient, buildApiUrl } from '../lib/api';
```

`listBackups` (Zeile 64-67) ersetzen durch:

```ts
export async function listBackups(): Promise<BackupListResponse> {
  const response = await apiClient.get<BackupListResponse>('/api/backups/');
  return response.data;
}
```

`getBackup` (Zeile 69-75, inkl. des Doc-Kommentars „Get backup details by ID") **komplett löschen** — toter Code ohne Konsumenten.

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/api/backup.test.ts`
Expected: PASS (3 Tests).

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/api/backup.ts client/src/__tests__/api/backup.test.ts; git commit -m "refactor(client): listBackups without memo cache, drop dead getBackup (#299)"
```

---

### Task 4: Hook useBackups

**Files:**
- Create: `client/src/hooks/useBackups.ts`
- Test: `client/src/__tests__/hooks/useBackups.test.tsx`

**Interfaces:**
- Consumes: `queryKeys.backups.list()` (Task 1), `listBackups` (Task 3).
- Produces: `useBackups(): { backups: Backup[]; loading: boolean; error: unknown; }` — `error` ist der ROHE Query-Error (oder `null`); der Konsument formatiert selbst via `getApiErrorMessage` + i18n (anders als `useRaidStatus`, das einen fertigen String liefert — hier braucht `BackupSettings` seine übersetzten Fallbacks).

- [ ] **Step 1: Failing Test schreiben**

Create `client/src/__tests__/hooks/useBackups.test.tsx` (Muster: `useRaidStatus.test.tsx`):

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useBackups } from '../../hooks/useBackups';
import * as backupApi from '../../api/backup';

vi.mock('../../api/backup');
const api = vi.mocked(backupApi);

const sample = {
  backups: [
    {
      id: 1, filename: 'b1.tar.gz', filepath: '/tmp/b1.tar.gz', size_bytes: 1000,
      size_mb: 0, backup_type: 'full' as const, status: 'completed' as const,
      created_at: '2026-07-01T00:00:00Z', completed_at: null, creator_id: 1,
      error_message: null, includes_database: true, includes_files: true, includes_config: false,
    },
  ],
  total_size_bytes: 1000,
  total_size_mb: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useBackups', () => {
  it('unwraps the backup list from the response', async () => {
    api.listBackups.mockResolvedValue(sample);
    const { result } = renderHook(() => useBackups(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.backups).toHaveLength(1);
    expect(result.current.backups[0].filename).toBe('b1.tar.gz');
    expect(result.current.error).toBeNull();
  });

  it('exposes the raw error when the fetch rejects', async () => {
    api.listBackups.mockRejectedValue(new Error('backup boom'));
    const { result } = renderHook(() => useBackups(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect((result.current.error as Error).message).toBe('backup boom');
    expect(result.current.backups).toEqual([]);
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/hooks/useBackups.test.tsx`
Expected: FAIL — `Cannot find module '../../hooks/useBackups'`.

- [ ] **Step 3: Hook implementieren**

Create `client/src/hooks/useBackups.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { listBackups, type Backup } from '../api/backup';

export interface UseBackupsResult {
  backups: Backup[];
  loading: boolean;
  /** Raw query error (null when none) — caller formats via getApiErrorMessage + i18n. */
  error: unknown;
}

/**
 * Backup list for BackupSettings. Query-backed — the two mount points
 * (BackupPage + SystemControlPage backup tab) share one cache entry.
 * No polling: create/delete mutations invalidate queryKeys.backups.list().
 */
export function useBackups(): UseBackupsResult {
  const query = useQuery({
    queryKey: queryKeys.backups.list(),
    queryFn: listBackups,
  });

  return {
    backups: query.data?.backups ?? [],
    loading: query.isLoading,
    error: query.isError ? query.error : null,
  };
}
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/hooks/useBackups.test.tsx`
Expected: PASS (2 Tests).

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/hooks/useBackups.ts client/src/__tests__/hooks/useBackups.test.tsx; git commit -m "feat(client): useBackups query hook (#299)"
```

---

### Task 5: BackupSettings → useBackups + useMutation (erstes Mutation-Muster)

**Files:**
- Modify: `client/src/components/BackupSettings.tsx`

**Interfaces:**
- Consumes: `useBackups()` (Task 4), `queryKeys.backups.list()` (Task 1), `createBackup`/`deleteBackup`/`restoreBackup`/`downloadBackup` aus `api/backup` (unverändert), `getApiErrorMessage` aus `lib/errorHandling` (bereits importiert).
- Produces: kein API-Export — aber dies ist die REFERENZ-Implementierung des `useMutation`+`invalidateQueries`-Musters für alle späteren Domain-PRs.

Kein eigener Komponententest (BackupSettings hat keinen Bestand-Test; Absicherung: Hook-Test aus Task 4 + `npm run build` + volle Vitest-Suite am Ende). Verifikation hier: Build + bestehende Suite bleiben grün.

- [ ] **Step 1: Imports umbauen**

In `client/src/components/BackupSettings.tsx` Kopfzeilen (Zeilen 1-8) ersetzen durch:

```tsx
import { useState, useMemo } from 'react';
import { Download, Trash2, RotateCcw, AlertTriangle, Database, FolderOpen, Settings, CheckCircle, XCircle, Clock, HardDrive } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createBackup, deleteBackup, restoreBackup, downloadBackup } from '../api/backup';
import type { Backup, CreateBackupRequest, RestoreBackupRequest } from '../api/backup';
import { useBackups } from '../hooks/useBackups';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { formatBytes } from '../lib/formatters';
```

(Entfällt: `useEffect`, `listBackups`, `BackupListResponse`-Typ, `import { apiCache } from '../lib/api';`.)

- [ ] **Step 2: State + Laden ersetzen**

Die States `backups`, `totalSizeBytes`, `loading`, `creating`, `deleting` (Zeilen 17-20, 28) sowie den `useEffect` + die `loadBackups`-Funktion (Zeilen 31-49) ersetzen durch:

```tsx
	const queryClient = useQueryClient();
	const { backups, loading, error: loadError } = useBackups();
	const totalSizeBytes = useMemo(
		() => backups.reduce((acc, b) => acc + b.size_bytes, 0),
		[backups]
	);
```

Die übrigen States (`includesDatabase`, `includesFiles`, `includesConfig`, `backupPath`, `error`, `success`, Dialog-States, `restoring`) bleiben unverändert.

- [ ] **Step 3: Mutationen implementieren**

Die Funktionen `handleCreateBackup` (Zeilen 51-72) und `handleDeleteBackup` (Zeilen 74-91) ersetzen durch:

```tsx
	const createMutation = useMutation({
		mutationFn: (request: CreateBackupRequest) => createBackup(request),
		onSuccess: () => {
			setSuccess(t('backup.createSuccess'));
			void queryClient.invalidateQueries({ queryKey: queryKeys.backups.list() });
		},
		onError: (err: unknown) => {
			setError(getApiErrorMessage(err, t('backup.createFailed')));
		},
	});

	const deleteMutation = useMutation({
		mutationFn: (backupId: number) => deleteBackup(backupId),
		onSuccess: () => {
			setSuccess(t('backup.deleteSuccess'));
			void queryClient.invalidateQueries({ queryKey: queryKeys.backups.list() });
			setDeleteDialogOpen(false);
			setBackupToDelete(null);
		},
		onError: (err: unknown) => {
			setError(getApiErrorMessage(err, t('backup.deleteFailed')));
		},
	});

	function handleCreateBackup() {
		setError(null);
		setSuccess(null);
		createMutation.mutate({
			includes_database: includesDatabase,
			includes_files: includesFiles,
			includes_config: includesConfig,
			backup_path: backupPath,
		});
	}

	function handleDeleteBackup() {
		if (!backupToDelete) return;
		setError(null);
		deleteMutation.mutate(backupToDelete.id);
	}
```

- [ ] **Step 4: JSX auf isPending + Ladefehler umstellen**

Alle JSX-Verwendungen anpassen (Suchen & Ersetzen im File):
- Jedes `creating` → `createMutation.isPending` (Checkbox-`disabled`, Input-`disabled`, Create-Button `disabled` + Label).
- Jedes `deleting` → `deleteMutation.isPending` (Dialog-Buttons).
- Der Fehlerblock `{error && (...)}` zeigt zusätzlich Ladefehler. Direkt über dem `return` eine abgeleitete Variable einfügen und im JSX `error` durch `displayError` ersetzen (nur im Fehlerblock — die `setError`-Aufrufe bleiben):

```tsx
	const displayError = error ?? (loadError ? getApiErrorMessage(loadError, t('backup.loadFailed')) : null);
```

```tsx
			{displayError && (
				<div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
					<div className="flex items-center gap-2 text-red-400">
						<AlertTriangle className="w-5 h-5" />
						<span>{displayError}</span>
					</div>
				</div>
			)}
```

`handleRestoreBackup`, `handleDownload` und der gesamte Rest des JSX bleiben unverändert.

- [ ] **Step 5: Verifizieren (Build + Suite)**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npm run build; if ($?) { npx vitest run src/__tests__/hooks/useBackups.test.tsx src/__tests__/api/backup.test.ts }`
Expected: Build erfolgreich (tsc findet keine `apiCache`/`listBackups`-Referenzen mehr in BackupSettings); Tests PASS.

- [ ] **Step 6: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/components/BackupSettings.tsx; git commit -m "feat(client): BackupSettings on useBackups + useMutation, drop apiCache.clear (#299)"
```

---

### Task 6: api/shares.ts — plain listFileShares, apiCache-Invalidierung raus

**Files:**
- Modify: `client/src/api/shares.ts`
- Test: `client/src/__tests__/api/shares.test.ts`

**Interfaces:**
- Produces: `listFileShares(): Promise<FileShare[]>` (Signatur unverändert, intern plain GET). `createFileShare`/`updateFileShare`/`deleteFileShare` rufen KEINE Cache-Invalidierung mehr auf — die übernimmt ab Task 8/9 die Query-Schicht (Modals + SharesPage).

- [ ] **Step 1: Tests anpassen (failing)**

In `client/src/__tests__/api/shares.test.ts`:

Mock-Factory (Zeilen 12-21) ersetzen durch:

```ts
vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));
```

Import (Zeile 23) ändern zu:

```ts
import { apiClient } from '../../lib/api';
```

In `beforeEach` die Zeile `vi.mocked(apiCache.delete).mockReset();` entfernen.

Die drei Tests mit Cache-Assertions umbenennen und die `apiCache.delete`-Erwartungen entfernen:
- `'createFileShare calls POST and clears cache'` → `'createFileShare calls POST'`; Zeile `expect(apiCache.delete).toHaveBeenCalled();` löschen.
- `'updateFileShare calls PATCH and clears cache'` → `'updateFileShare calls PATCH'`; Cache-Assertion löschen.
- `'deleteFileShare calls DELETE and clears cache'` → `'deleteFileShare calls DELETE'`; Cache-Assertion löschen.

Neuen Test ergänzen (nach `getShareableUsers`):

```ts
  it('listFileShares calls GET /api/shares/user-shares directly (no memo cache)', async () => {
    const shares = [{ id: 1, file_id: 10 }];
    vi.mocked(apiClient.get).mockResolvedValue({ data: shares });

    const result = await listFileShares();

    expect(apiClient.get).toHaveBeenCalledWith('/api/shares/user-shares');
    expect(result).toEqual(shares);
  });
```

Und `listFileShares` in den Import-Block am Dateikopf (Zeilen 2-10) aufnehmen.

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/api/shares.test.ts`
Expected: FAIL — `shares.ts` importiert noch `apiCache`/`memoizedApiRequest`, die die Factory nicht mehr liefert (`apiCache.delete is not a function` bzw. `memoizedApiRequest is not a function` im neuen `listFileShares`-Test).

- [ ] **Step 3: shares.ts umbauen**

In `client/src/api/shares.ts`:

Import (Zeile 5) ändern zu:

```ts
import { apiClient } from '../lib/api';
```

Die Konstante `SHARES_CACHE_KEY` (Zeile 89) löschen.

`createFileShare` (Zeilen 91-95): die Zeile `apiCache.delete(SHARES_CACHE_KEY);` löschen.

`listFileShares` (Zeilen 97-100) ersetzen durch:

```ts
export const listFileShares = async (): Promise<FileShare[]> => {
  const response = await apiClient.get('/api/shares/user-shares');
  return response.data;
};
```

`updateFileShare` (Zeilen 112-119): die Zeile `apiCache.delete(SHARES_CACHE_KEY);` löschen.

`deleteFileShare` (Zeilen 121-124): die Zeile `apiCache.delete(SHARES_CACHE_KEY);` löschen.

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/api/shares.test.ts`
Expected: PASS (8 Tests).

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/api/shares.ts client/src/__tests__/api/shares.test.ts; git commit -m "refactor(client): shares API without memo cache — invalidation moves to the query layer (#299)"
```

---

### Task 7: Hook useFileShares

**Files:**
- Create: `client/src/hooks/useFileShares.ts`
- Test: `client/src/__tests__/hooks/useFileShares.test.tsx`

**Interfaces:**
- Consumes: `queryKeys.shares.*` (Task 1); `listFileShares`, `listFilesSharedWithMe`, `getShareStatistics` + Typen `FileShare`, `SharedWithMe`, `ShareStatistics` aus `api/shares` (Task 6).
- Produces: `useFileShares(): { fileShares: FileShare[]; sharedWithMe: SharedWithMe[]; statistics: ShareStatistics | null; loading: boolean; error: unknown; }` — Feldnamen matchen exakt die bisherigen `SharesPage`-State-Variablen, damit das JSX unberührt bleibt.

- [ ] **Step 1: Failing Test schreiben**

Create `client/src/__tests__/hooks/useFileShares.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useFileShares } from '../../hooks/useFileShares';
import * as sharesApi from '../../api/shares';
import type { FileShare, SharedWithMe } from '../../api/shares';

vi.mock('../../api/shares');
const api = vi.mocked(sharesApi);

const stats = { total_file_shares: 2, active_file_shares: 1, files_shared_with_me: 3 };

beforeEach(() => {
  vi.clearAllMocks();
  api.listFileShares.mockResolvedValue([{ id: 1 } as unknown as FileShare]);
  api.listFilesSharedWithMe.mockResolvedValue([{ share_id: 9 } as unknown as SharedWithMe]);
  api.getShareStatistics.mockResolvedValue(stats);
});

describe('useFileShares', () => {
  it('exposes all three reads under the SharesPage state names', async () => {
    const { result } = renderHook(() => useFileShares(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fileShares).toHaveLength(1);
    expect(result.current.sharedWithMe).toHaveLength(1);
    expect(result.current.statistics).toEqual(stats);
    expect(result.current.error).toBeNull();
  });

  it('stays loading until every query settled', async () => {
    let resolveStats!: (v: typeof stats) => void;
    api.getShareStatistics.mockReturnValue(new Promise((r) => { resolveStats = r; }));
    const { result } = renderHook(() => useFileShares(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.fileShares).toHaveLength(1));
    expect(result.current.loading).toBe(true);
    resolveStats(stats);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('surfaces the first failing query as raw error', async () => {
    api.listFileShares.mockRejectedValue(new Error('shares boom'));
    const { result } = renderHook(() => useFileShares(), { wrapper: createQueryWrapper() });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect((result.current.error as Error).message).toBe('shares boom');
    expect(result.current.fileShares).toEqual([]);
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/hooks/useFileShares.test.tsx`
Expected: FAIL — `Cannot find module '../../hooks/useFileShares'`.

- [ ] **Step 3: Hook implementieren**

Create `client/src/hooks/useFileShares.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import {
  listFileShares,
  listFilesSharedWithMe,
  getShareStatistics,
  type FileShare,
  type SharedWithMe,
  type ShareStatistics,
} from '../api/shares';

export interface UseFileSharesResult {
  fileShares: FileShare[];
  sharedWithMe: SharedWithMe[];
  statistics: ShareStatistics | null;
  loading: boolean;
  /** Raw error of the first failing query (null when all fine). */
  error: unknown;
}

/**
 * The three shares-domain reads for SharesPage (user-scoped!). Mutations
 * anywhere in the app invalidate queryKeys.shares.all() — see the share
 * modals. Cross-user leaking is prevented by AuthContext.clearQueryCache().
 */
export function useFileShares(): UseFileSharesResult {
  const userShares = useQuery({
    queryKey: queryKeys.shares.userShares(),
    queryFn: listFileShares,
  });
  const sharedWithMe = useQuery({
    queryKey: queryKeys.shares.sharedWithMe(),
    queryFn: listFilesSharedWithMe,
  });
  const statistics = useQuery({
    queryKey: queryKeys.shares.statistics(),
    queryFn: getShareStatistics,
  });

  const queries = [userShares, sharedWithMe, statistics];
  return {
    fileShares: userShares.data ?? [],
    sharedWithMe: sharedWithMe.data ?? [],
    statistics: statistics.data ?? null,
    loading: queries.some((q) => q.isLoading),
    error: queries.find((q) => q.isError)?.error ?? null,
  };
}
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/hooks/useFileShares.test.tsx`
Expected: PASS (3 Tests).

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/hooks/useFileShares.ts client/src/__tests__/hooks/useFileShares.test.tsx; git commit -m "feat(client): useFileShares query hook for the shares domain (#299)"
```

---

### Task 8: Share-Modals invalidieren selbst (zentrale Semantik)

**Files:**
- Modify: `client/src/components/CreateFileShareModal.tsx`
- Modify: `client/src/components/EditFileShareModal.tsx`
- Modify: `client/src/components/ShareFileModal.tsx`

**Interfaces:**
- Consumes: `queryKeys.shares.all()` (Task 1), `useQueryClient` aus `@tanstack/react-query`.
- Produces: Verhaltensgarantie für Task 9 — JEDE Share-Mutation invalidiert `['shares']` selbst, egal wo das Modal gemountet ist (SharesPage ODER FileManager). Die `onSuccess`-Props bleiben rein UI (Modal schließen).

**Warum in den Modals:** Der alte `apiCache.delete` saß in den api-Funktionen → jede Mutation-Site invalidierte automatisch. `ShareFileModal` ist in `FileManager.tsx:900` gemountet — Invalidierung nur in SharesPage-Callbacks würde diese Site verfehlen (Spec §3.4).

Kein eigener Komponententest (kein Bestand; Absicherung: Build + Suite; das Invalidierungs-Verhalten ist ein Ein-Zeilen-Call auf ein getestetes TanStack-Primitive).

- [ ] **Step 1: CreateFileShareModal**

In `client/src/components/CreateFileShareModal.tsx`:

Bei den Imports ergänzen:

```tsx
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
```

In der Komponente (nach `const [loading, setLoading] = ...` bzw. bei den anderen Hook-Aufrufen am Komponentenanfang):

```tsx
  const queryClient = useQueryClient();
```

In `handleSubmit` (Zeile 91-110) nach dem `await createFileShare({...});` und vor `onSuccess();` einfügen:

```tsx
      // Central invalidation (replaces the old apiCache.delete in the API fn):
      // works from every mount point, incl. FileManager.
      void queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() });
```

- [ ] **Step 2: EditFileShareModal**

In `client/src/components/EditFileShareModal.tsx` identisch: die zwei Imports + `const queryClient = useQueryClient();` (nach Zeile 15), und in `handleSubmit` (Zeile 24-39) nach `await updateFileShare(...)` / vor `onSuccess();`:

```tsx
      void queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() });
```

- [ ] **Step 3: ShareFileModal**

In `client/src/components/ShareFileModal.tsx` identisch: Imports + `const queryClient = useQueryClient();` (nach Zeile 21), und in `handleInternalSubmit` (Zeile 67-86) nach `await createFileShare({...});` / vor `onSuccess();`:

```tsx
      void queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() });
```

**Wichtig:** `handleCloudSubmit` (Zeile 89-106) NICHT anfassen — Cloud-Exports sind eine andere Domain (kein `['shares']`-Read betroffen).

- [ ] **Step 4: Verifizieren**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npm run build`
Expected: Build erfolgreich.

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/components/CreateFileShareModal.tsx client/src/components/EditFileShareModal.tsx client/src/components/ShareFileModal.tsx; git commit -m "feat(client): share modals invalidate the shares query domain after mutations (#299)"
```

---

### Task 9: SharesPage → useFileShares + Delete-Mutation

**Files:**
- Modify: `client/src/pages/SharesPage.tsx`

**Interfaces:**
- Consumes: `useFileShares()` (Task 7) — Feldnamen `fileShares`/`sharedWithMe`/`statistics` matchen die bisherigen States, JSX bleibt unberührt; `queryKeys.shares.all()` (Task 1); Modals invalidieren selbst (Task 8).
- Produces: kein Export.

- [ ] **Step 1: Imports + State umbauen**

In `client/src/pages/SharesPage.tsx`:

Import-Block (Zeilen 4-13) ändern — `listFileShares`, `listFilesSharedWithMe`, `getShareStatistics` raus, Typen bleiben:

```tsx
import {
  deleteFileShare,
  getShareableUsers,
  type FileShare,
} from '../api/shares';
```

Neue Imports ergänzen:

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useFileShares } from '../hooks/useFileShares';
import { queryKeys } from '../lib/queryKeys';
```

(`SharedWithMe`/`ShareStatistics`-Typimporte entfallen — die States dazu verschwinden.)

Die States (Zeilen 37-42) umbauen — `fileShares`, `sharedWithMe`, `statistics`, `loading` entfallen; Cloud-States bleiben, bekommen eigenes Loading:

```tsx
  const [cloudExports, setCloudExports] = useState<CloudExportJob[]>([]);
  const [cloudStats, setCloudStats] = useState<CloudExportStats | null>(null);
  const [cloudLoading, setCloudLoading] = useState(true);
```

Direkt darunter Hook + kombiniertes Loading (Name `loading` bleibt → JSX unberührt):

```tsx
  const queryClient = useQueryClient();
  const { fileShares, sharedWithMe, statistics, loading: sharesLoading } = useFileShares();
  const loading = sharesLoading || cloudLoading;
```

- [ ] **Step 2: loadData durch loadCloudExports ersetzen**

`loadData` (Zeilen 67-87) ersetzen durch:

```tsx
  const loadCloudExports = async () => {
    setCloudLoading(true);
    try {
      const [cExports, cStats] = await Promise.all([
        listCloudExports().catch(() => []),
        getCloudExportStatistics().catch(() => null),
      ]);
      setCloudExports(cExports);
      setCloudStats(cStats);
    } finally {
      setCloudLoading(false);
    }
  };
```

Den Mount-Effect (Zeilen 53-56) anpassen:

```tsx
  useEffect(() => {
    loadCloudExports();
    fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

(Falls der bestehende Effect keinen eslint-disable-Kommentar hat und `eslint .` nicht meckert, den Kommentar weglassen — exakt dem Bestandsstil folgen.)

- [ ] **Step 3: Delete als Mutation**

`handleDeleteFileShare` (Zeilen 89-99) ersetzen durch:

```tsx
  const deleteShareMutation = useMutation({
    mutationFn: (shareId: number) => deleteFileShare(shareId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() });
    },
    onError: () => {
      toast.error(t('shares:toast.revokeFailed'));
    },
  });

  const handleDeleteFileShare = async (shareId: number) => {
    const ok = await confirm(t('confirm.revokeShare'), { title: t('confirm.revokeShare'), variant: 'danger', confirmLabel: t('common:actions.revoke', 'Revoke') });
    if (!ok) return;
    deleteShareMutation.mutate(shareId);
  };
```

- [ ] **Step 4: Cloud-Handler + Modal-Callbacks anpassen**

In `handleRevokeExport` (Zeile ~115) und `handleRetryExport` (Zeile ~125): `await loadData();` → `await loadCloudExports();`.

Modal-Callbacks (Zeilen 886-905): die `loadData();`-Aufrufe entfernen (Modals invalidieren seit Task 8 selbst):

```tsx
      {showCreateShareModal && (
        <CreateFileShareModal
          users={users}
          onClose={() => setShowCreateShareModal(false)}
          onSuccess={() => setShowCreateShareModal(false)}
        />
      )}
      {editingShare && (
        <EditFileShareModal
          fileShare={editingShare}
          onClose={() => setEditingShare(null)}
          onSuccess={() => setEditingShare(null)}
        />
      )}
```

- [ ] **Step 5: Verifizieren**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npm run build; if ($?) { npx eslint src/pages/SharesPage.tsx }`
Expected: Build erfolgreich (keine Referenzen mehr auf entfernte States/Imports); ESLint 0 Errors (insb. keine unused imports).

- [ ] **Step 6: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/pages/SharesPage.tsx; git commit -m "feat(client): SharesPage on useFileShares + delete mutation (#299)"
```

---

### Task 10: api/files.ts — getFilePermissions als Plain-Read

**Files:**
- Modify: `client/src/api/files.ts`
- Test: `client/src/__tests__/api/files.test.ts`
- Modify: `client/src/__tests__/api/plugins.scopeCatalog.test.ts`

**Interfaces:**
- Produces: `getFilePermissions(path: string)` (Signatur unverändert, intern plain GET — KEINE Query-Beteiligung, siehe Spec §3.5: kein Persister-Bloat, immer frische Rechte). `FileManager.tsx` bleibt unberührt.

- [ ] **Step 1: Tests anpassen (failing)**

In `client/src/__tests__/api/files.test.ts`:

Mock-Factory (Zeilen 10-16) ersetzen durch:

```ts
vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));
```

Import (Zeile 18) ändern zu:

```ts
import { apiClient } from '../../lib/api';
```

In `beforeEach`: `vi.mocked(memoizedApiRequest).mockReset();` ersetzen durch `vi.mocked(apiClient.get).mockReset();`.

Den Test `'getFilePermissions uses memoizedApiRequest'` (Zeilen 40-46) ersetzen durch:

```ts
  it('getFilePermissions calls GET with the path param (always fresh, no memo cache)', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { owner_id: 1, rules: [] } });

    const result = await getFilePermissions('/my/file.txt');

    expect(apiClient.get).toHaveBeenCalledWith('/api/files/permissions', { params: { path: '/my/file.txt' } });
    expect(result).toEqual({ owner_id: 1, rules: [] });
  });
```

In `client/src/__tests__/api/plugins.scopeCatalog.test.ts`: die Zeile 7 `memoizedApiRequest: vi.fn(),` aus der `vi.mock('../../lib/api', ...)`-Factory entfernen (Rest der Factory unverändert).

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/api/files.test.ts src/__tests__/api/plugins.scopeCatalog.test.ts`
Expected: `files.test.ts` FAIL (`getFilePermissions` ruft noch `memoizedApiRequest`, das die Factory nicht mehr liefert); `plugins.scopeCatalog.test.ts` PASS (der Eintrag war eine unbenutzte Leiche).

- [ ] **Step 3: files.ts umbauen**

In `client/src/api/files.ts`:

Import (Zeile 5) ändern zu:

```ts
import { apiClient } from '../lib/api';
```

`getFilePermissions` (Zeilen 29-32) ersetzen durch:

```ts
export async function getFilePermissions(path: string) {
  // Plain read on purpose: the permission dialog must always show fresh
  // rules (the old 60s memo cache could serve stale ones) and this
  // user-scoped data must not be mirrored into the persisted query cache.
  const res = await apiClient.get(`/api/files/permissions`, { params: { path } });
  return res.data;
}
```

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run src/__tests__/api/files.test.ts src/__tests__/api/plugins.scopeCatalog.test.ts`
Expected: PASS (alle Tests beider Dateien).

- [ ] **Step 5: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/api/files.ts client/src/__tests__/api/files.test.ts client/src/__tests__/api/plugins.scopeCatalog.test.ts; git commit -m "refactor(client): getFilePermissions as plain read — always fresh, no memo cache (#299)"
```

---

### Task 11: lib/api.ts — apiCache + memoizedApiRequest löschen

**Files:**
- Modify: `client/src/lib/api.ts:82-97`

**Interfaces:**
- Produces: `lib/api.ts` exportiert NUR noch `API_VERSION`, `isTauri`, `API_BASE_URL`, `buildApiUrl`, `apiClient`, `fireAuthExpired`, `extractErrorMessage`. `apiCache`, `memoizedApiRequest`, `CacheEntry`, `DEFAULT_TTL` existieren nicht mehr — der Compiler erzwingt, dass Tasks 3-10 alle Konsumenten erwischt haben.

- [ ] **Step 1: Block löschen**

In `client/src/lib/api.ts` die Zeilen 82-97 komplett entfernen:

```ts
// --- Memoized API Request Utility ---
type CacheEntry = { data: any; expires: number };
export const apiCache = new Map<string, CacheEntry>();
const DEFAULT_TTL = 60 * 1000; // 60 Sekunden

export async function memoizedApiRequest<T = any>(url: string, params?: any, ttl: number = DEFAULT_TTL): Promise<T> {
  const key = url + JSON.stringify(params || {});
  const now = Date.now();
  const cached = apiCache.get(key);
  if (cached && cached.expires > now) {
    return cached.data;
  }
  const res = await apiClient.get(url, { params });
  apiCache.set(key, { data: res.data, expires: now + ttl });
  return res.data;
}
```

(`extractErrorMessage` darunter bleibt.)

- [ ] **Step 2: Compile-Gate — beweist, dass kein Konsument übrig ist**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npm run build`
Expected: Build erfolgreich. Ein Fehler `Module '"../lib/api"' has no exported member 'memoizedApiRequest'` hieße: ein Konsument wurde in Tasks 3-10 übersehen — dann dort fixen, NICHT den Export wiederherstellen.

- [ ] **Step 3: Volle Testsuite**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run`
Expected: PASS — komplett grün (insb. keine `vi.mock`-Factory referenziert die entfernten Exporte mehr).

- [ ] **Step 4: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/lib/api.ts; git commit -m "refactor(client): remove apiCache + memoizedApiRequest — superseded by TanStack Query (#299, closes #309)"
```

---

### Task 12: CLAUDE.md-Doku, Schlussgates, Index

**Files:**
- Modify: `client/src/lib/CLAUDE.md`
- Modify: `client/src/api/CLAUDE.md`
- Modify: `client/src/hooks/CLAUDE.md`
- Modify: `client/src/contexts/CLAUDE.md`

- [ ] **Step 1: lib/CLAUDE.md**

In der Files-Tabelle die `api.ts`-Zeile ersetzen durch:

```markdown
| `api.ts` | **Core API client**: axios instance (`apiClient`), auth interceptor, 401 handling, `buildApiUrl()` for dev/prod path resolution, API version check via `X-API-Min-Version` header |
```

Im „Key Patterns"-Block die Zeile ``- `memoizedApiRequest()` uses an in-memory `Map` cache with configurable TTL (default 60s)`` ersetzen durch:

```markdown
- The old `memoizedApiRequest()` Map cache is gone (#299/#309) — caching/dedup is TanStack Query's job; api/* functions are plain typed calls
```

- [ ] **Step 2: api/CLAUDE.md**

Im „Base Client"-Block die Zeile ``- `memoizedApiRequest<T>(url, params?, ttl?)` — GET with in-memory cache (60s default TTL)`` löschen.

In „Conventions" die Zeile ``- Use `memoizedApiRequest()` for frequently polled read-only data (e.g., permissions, system info)`` ersetzen durch:

```markdown
- No client-side memo caching in api/* — read-caching/dedup lives in TanStack Query hooks (`useQuery` + `lib/queryKeys.ts`); mutations invalidate their domain (`invalidateQueries`)
```

- [ ] **Step 3: hooks/CLAUDE.md**

In der Data-Fetching-Tabelle nach der `useRaidStatus.ts`-Zeile ergänzen:

```markdown
| `useBackups.ts` | `api/backup` | Backup list via **TanStack Query** (no polling; create/delete mutations invalidate). Returns raw `error` for i18n formatting by the caller |
| `useFileShares.ts` | `api/shares` | The three shares-domain reads (user shares, shared-with-me, statistics) via **TanStack Query**; user-scoped — cache is cleared on every identity change (AuthContext) |
```

In „Conventions" nach der Query-Polling-Zeile ergänzen:

```markdown
- **Mutations use `useMutation`** with `onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.<domain>.all() })` — reference implementations: `BackupSettings.tsx`, the share modals (`CreateFileShareModal`/`EditFileShareModal`/`ShareFileModal` invalidate themselves so every mount point is covered), `SharesPage.tsx`
```

- [ ] **Step 4: contexts/CLAUDE.md**

In der `AuthContext.tsx`-Tabellenzeile den Purpose-Text ergänzen um:

```markdown
Clears the TanStack Query cache + persisted blob on EVERY identity change (login, logout, impersonate, endImpersonation, auth-expiry) so user-scoped queries never leak across users (#299)
```

- [ ] **Step 5: Schlussgates (alle drei, aus Memory-Pflicht)**

Run: `cd "D:\Programme (x86)\Baluhost\client"; npx vitest run; if ($?) { npx eslint . }; if ($?) { npm run build }`
Expected: Suite komplett PASS; ESLint 0 Errors; Build erfolgreich.

- [ ] **Step 6: vectordb-Index aktualisieren**

`mcp__vectordb-search__index_update` mit projectPath `D:/Programme (x86)/Baluhost` aufrufen (neue Hooks/gelöschte Exporte indexieren).

- [ ] **Step 7: Commit**

```powershell
cd "D:\Programme (x86)\Baluhost"; git add client/src/lib/CLAUDE.md client/src/api/CLAUDE.md client/src/hooks/CLAUDE.md client/src/contexts/CLAUDE.md; git commit -m "docs(client): CLAUDE.md updates for memoizedApiRequest removal + mutation pattern (#299)"
```

---

## Nach Abschluss (nicht Teil der Tasks — Operator-Schritte)

1. Push + PR gegen `main` (Release-Workflow: PR, kein lokaler Merge): `git push -u origin feat/tanstack-query-memoized-cache-299`, dann `gh pr create` (Body via `--body-file`, referenziert #299 + `Closes #309`).
2. In #299 die Checkbox „PR — memoizedApiRequest ablösen" abhaken + Hinweis, dass die Impersonation-Cache-Leerung (Hinweis-Block im Issue) umgesetzt ist.
3. Manueller Smoke (dev, `python start_dev.py`): Backup anlegen/löschen (Liste refresht ohne Reload), Share im FileManager anlegen → SharesPage zeigt ihn, Impersonation starten/beenden → keine fremden Shares sichtbar, F5 auf Dashboard → Instant-Paint intakt.
