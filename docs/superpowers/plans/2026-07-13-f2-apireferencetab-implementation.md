# ApiReferenceTab F2 Decomposition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behaviour-preserving decomposition of `client/src/components/manual/ApiReferenceTab.tsx` (565 lines) into a pure helper + a state hook + presentation subcomponents, leaving a thin orchestrator (~90–130 lines).

**Architecture:** Extract the pure rate-limit matcher to `lib/`, the view/fetch/derived state to `hooks/useApiReference.ts`, and each JSX block to a presentation component under `components/manual/api-reference/`. Build the new units alongside the still-working original (Tasks 1–4 add files only), then swap the orchestrator to consume them (Task 5). Every extracted unit is a verbatim port — no behaviour change.

**Tech Stack:** React 18 + TypeScript (strict), Tailwind, lucide-react, react-i18next, Vitest + @testing-library/react.

**Spec:** `docs/superpowers/plans/2026-07-13-f2-apireferencetab-decomposition.md`
**Source of truth for verbatim slices:** the pre-change `ApiReferenceTab.tsx` (line ranges cited per task).

## Global Constraints

- Same F2 pattern as #396–#414: pure helper + `hooks/use…` + `<feature>/*` presentation + thin orchestrator; per-unit Vitest; verbatim/behaviour-preserving.
- Full split (Variante A): every JSX block becomes its own component.
- Tailwind classes, `t()` keys, icons, and the `getApiBaseUrl` heuristic (3001 dev / 8000 prod) copied **verbatim** — do NOT "clean up" the matcher branch order or the base-url logic.
- Pure matcher `lib/apiRateLimitMatch.ts`; presentation under `components/manual/api-reference/` with a barrel `index.ts`.
- Tests live under `client/src/__tests__/**` mirroring the source path (repo convention).
- Gates before PR: `npx eslint .` (0 errors — warnings allowed), `npm run build` (tsc -b), `npx vitest run` (all from `client/`).
- CRLF repo (`core.autocrlf=true`) — let git handle EOL; do not fight it.

---

### Task 1: Pure rate-limit matcher `lib/apiRateLimitMatch.ts`

**Files:**
- Create: `client/src/lib/apiRateLimitMatch.ts`
- Test: `client/src/__tests__/lib/apiRateLimitMatch.test.ts`
- Source: verbatim from `ApiReferenceTab.tsx:25-34` (type) and `:42-115` (function)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `export interface RateLimitConfig { id: number; endpoint_type: string; limit_string: string; description: string | null; enabled: boolean; created_at: string; updated_at: string | null; updated_by: number | null; }`
  - `export function matchEndpointToRateLimitType(method: string, path: string): string | null`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/lib/apiRateLimitMatch.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { matchEndpointToRateLimitType } from '../../lib/apiRateLimitMatch'

describe('matchEndpointToRateLimitType', () => {
  it('matches specific auth endpoints before the auth catch-all', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/auth/login')).toBe('auth_login')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/register')).toBe('auth_register')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/change-password')).toBe('auth_password_change')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/refresh')).toBe('auth_refresh')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/verify-2fa')).toBe('auth_2fa_verify')
    expect(matchEndpointToRateLimitType('POST', '/api/auth/2fa/setup')).toBe('auth_2fa_setup')
    // generic auth path falls through to the catch-all
    expect(matchEndpointToRateLimitType('GET', '/api/auth/me')).toBe('user_operations')
  })

  it('is case-insensitive on method and path', () => {
    expect(matchEndpointToRateLimitType('post', '/API/AUTH/LOGIN')).toBe('auth_login')
  })

  it('matches files specific-before-generic', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/files/upload/chunked/init')).toBe('file_chunked')
    expect(matchEndpointToRateLimitType('POST', '/api/files/upload')).toBe('file_upload')
    expect(matchEndpointToRateLimitType('GET', '/api/files/download/x')).toBe('file_download')
    expect(matchEndpointToRateLimitType('GET', '/api/files/list')).toBe('file_list')
    expect(matchEndpointToRateLimitType('DELETE', '/api/files/x')).toBe('file_delete')
    expect(matchEndpointToRateLimitType('PUT', '/api/files/x')).toBe('file_write')
  })

  it('matches activity as file_list', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/activity/feed')).toBe('file_list')
  })

  it('matches shares by write-method vs read', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/shares')).toBe('share_create')
    expect(matchEndpointToRateLimitType('PATCH', '/api/shares/1')).toBe('share_create')
    expect(matchEndpointToRateLimitType('DELETE', '/api/shares/1')).toBe('share_create')
    expect(matchEndpointToRateLimitType('GET', '/api/shares')).toBe('share_list')
  })

  it('matches mobile + desktop-pairing endpoints', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/mobile/register')).toBe('mobile_register')
    expect(matchEndpointToRateLimitType('POST', '/api/mobile/token/generate')).toBe('mobile_register')
    expect(matchEndpointToRateLimitType('POST', '/api/mobile/sync')).toBe('mobile_sync')
    expect(matchEndpointToRateLimitType('GET', '/api/mobile/upload-queue')).toBe('mobile_sync')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/device-code')).toBe('desktop_pairing_request')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/token')).toBe('desktop_pairing_poll')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/verify')).toBe('desktop_pairing_verify')
    expect(matchEndpointToRateLimitType('POST', '/api/desktop-pairing/approve')).toBe('desktop_pairing_approve')
  })

  it('matches vpn/backup/sync operation groups', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/vpn')).toBe('vpn_operations')
    expect(matchEndpointToRateLimitType('POST', '/api/vpn/clients')).toBe('vpn_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/backup')).toBe('backup_operations')
    expect(matchEndpointToRateLimitType('POST', '/api/sync/start')).toBe('sync_operations')
  })

  it('matches POST benchmark/run before the admin catch-all', () => {
    expect(matchEndpointToRateLimitType('POST', '/api/benchmark/run')).toBe('admin_benchmark')
    // non-run benchmark falls to admin catch-all
    expect(matchEndpointToRateLimitType('GET', '/api/benchmark/history')).toBe('admin_operations')
  })

  it('matches api-keys and users groups', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/api-keys')).toBe('api_key_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/users')).toBe('user_operations')
  })

  it('splits system/monitoring/energy by GET vs write', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/system/info')).toBe('system_monitor')
    expect(matchEndpointToRateLimitType('POST', '/api/system/reboot')).toBe('admin_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/monitoring/cpu')).toBe('system_monitor')
    expect(matchEndpointToRateLimitType('GET', '/api/energy/stats')).toBe('system_monitor')
  })

  it('splits vcl and ssd-cache by GET vs write', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/vcl/versions')).toBe('file_list')
    expect(matchEndpointToRateLimitType('POST', '/api/vcl/restore')).toBe('file_write')
    expect(matchEndpointToRateLimitType('GET', '/api/ssd-cache/status')).toBe('file_list')
    expect(matchEndpointToRateLimitType('POST', '/api/ssd-cache/clear')).toBe('admin_operations')
  })

  it('matches admin-prefix catch-all', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/pihole/status')).toBe('admin_operations')
    expect(matchEndpointToRateLimitType('POST', '/api/fans/config')).toBe('admin_operations')
    expect(matchEndpointToRateLimitType('GET', '/api/updates/check')).toBe('admin_operations')
  })

  it('returns null for unmatched paths', () => {
    expect(matchEndpointToRateLimitType('GET', '/api/unknown/x')).toBeNull()
    expect(matchEndpointToRateLimitType('GET', '/healthz')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `client/`): `npx vitest run src/__tests__/lib/apiRateLimitMatch.test.ts`
Expected: FAIL — cannot resolve `../../lib/apiRateLimitMatch`.

- [ ] **Step 3: Create the module (verbatim port)**

Create `client/src/lib/apiRateLimitMatch.ts`. Copy the `RateLimitConfig` interface from `ApiReferenceTab.tsx:25-34` and the function body from `:42-115` **unchanged**, exported:

```ts
export interface RateLimitConfig {
  id: number;
  endpoint_type: string;
  limit_string: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
  updated_by: number | null;
}

/**
 * Dynamically match an API endpoint to its rate limit endpoint_type
 * based on HTTP method and path patterns (mirrors backend decorator usage).
 */
export function matchEndpointToRateLimitType(method: string, path: string): string | null {
  // ... copy lines 43-114 of ApiReferenceTab.tsx VERBATIM (the p/m locals through
  //     the admin catch-all and the final `return null;`). Do not reorder branches.
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `client/`): `npx vitest run src/__tests__/lib/apiRateLimitMatch.test.ts`
Expected: PASS (all cases green).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/apiRateLimitMatch.ts client/src/__tests__/lib/apiRateLimitMatch.test.ts
git commit -m "feat(api-ref): extract pure apiRateLimitMatch helper + branch tests (#301)"
```

---

### Task 2: State hook `hooks/useApiReference.ts`

**Files:**
- Create: `client/src/hooks/useApiReference.ts`
- Test: `client/src/__tests__/hooks/useApiReference.test.tsx`
- Source: `ApiReferenceTab.tsx:244-330` (state, `getApiBaseUrl`, effect, `loadRateLimits`, `visibleSections`, `currentCategorySections`)

**Interfaces:**
- Consumes: `RateLimitConfig` from `lib/apiRateLimitMatch` (Task 1); `useOpenApiSchema` from `hooks/useOpenApiSchema` (returns `{ sections, categories, loading, error, refetch }`); `buildApiUrl` from `lib/api`; `ApiSection` from `data/api-endpoints/types`; `ApiCategory` from `lib/openapi-transform`.
- Produces:

```ts
export interface UseApiReferenceArgs { isAdmin: boolean; token: string | null }
export interface UseApiReferenceResult {
  activeView: 'docs' | 'limits';
  setActiveView: (v: 'docs' | 'limits') => void;
  selectedCategory: string | null;
  setSelectedCategory: (c: string | null) => void;
  selectedSection: string | null;
  setSelectedSection: (s: string | null) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  rateLimits: Record<string, RateLimitConfig>;
  loading: boolean;
  apiBaseUrl: string;
  apiSections: ApiSection[];
  apiCategories: ApiCategory[];
  schemaLoading: boolean;
  schemaError: string | null;
  refetchSchema: () => void;
  visibleSections: ApiSection[];
  currentCategorySections: ApiSection[];
}
export function useApiReference(args: UseApiReferenceArgs): UseApiReferenceResult
```

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/hooks/useApiReference.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'

// Controlled schema so the hook doesn't hit /openapi.json.
const mkSection = (title: string, paths: string[]) => ({
  title, icon: null,
  endpoints: paths.map(p => ({ method: 'GET', path: p, description: `${p} desc`, requiresAuth: false })),
})
const SECTIONS = [mkSection('Files', ['/api/files/list']), mkSection('Auth', ['/api/auth/me'])]
const CATEGORIES = [{ id: 'core', label: 'Core', sections: [SECTIONS[0]] }]

vi.mock('../../hooks/useOpenApiSchema', () => ({
  useOpenApiSchema: () => ({
    sections: SECTIONS, categories: CATEGORIES,
    loading: false, error: null, refetch: vi.fn(),
  }),
}))

import { useApiReference } from '../../hooks/useApiReference'

describe('useApiReference', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('non-admin skips the rate-limit fetch and clears loading', async () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: 't' }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetch).not.toHaveBeenCalled()
    expect(result.current.rateLimits).toEqual({})
  })

  it('admin loads rate limits and maps them by endpoint_type', async () => {
    const configs = [
      { id: 1, endpoint_type: 'auth_login', limit_string: '5/min', description: null,
        enabled: true, created_at: '', updated_at: null, updated_by: null },
    ]
    ;(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true, json: async () => ({ configs }),
    })
    const { result } = renderHook(() => useApiReference({ isAdmin: true, token: 'tok' }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(result.current.rateLimits.auth_login.limit_string).toBe('5/min')
  })

  it('visibleSections: no filter returns all sections', () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: null }))
    expect(result.current.visibleSections.map(s => s.title)).toEqual(['Files', 'Auth'])
  })

  it('visibleSections: search filters endpoints by path/description', () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: null }))
    act(() => result.current.setSearchQuery('files'))
    // only the "Files" section survives the /api/files/list path match
    expect(result.current.visibleSections.map(s => s.title)).toEqual(['Files'])
  })

  it('visibleSections: selecting a category narrows to its sections', () => {
    const { result } = renderHook(() => useApiReference({ isAdmin: false, token: null }))
    act(() => result.current.setSelectedCategory('core'))
    expect(result.current.visibleSections.map(s => s.title)).toEqual(['Files'])
  })
})
```

> Note: state updates must be wrapped in `act(...)` from `@testing-library/react` (the repo standard — see `useRaidSetupWizard.test.tsx` / `useSleepConfigForm.test.ts`), then assert on `result.current.visibleSections`. Do NOT assert on the raw fixture constants — that would test nothing.

- [ ] **Step 2: Run test to verify it fails**

Run (from `client/`): `npx vitest run src/__tests__/hooks/useApiReference.test.tsx`
Expected: FAIL — cannot resolve `../../hooks/useApiReference`.

- [ ] **Step 3: Create the hook (verbatim port of the state)**

Create `client/src/hooks/useApiReference.ts`. Move the state, `getApiBaseUrl`, the `useEffect([isAdmin])` + `loadRateLimits`, `visibleSections` memo, and `currentCategorySections` from `ApiReferenceTab.tsx:244-330` **unchanged**; wire the `useOpenApiSchema()` pass-through:

```ts
import { useState, useEffect, useMemo } from 'react';
import { buildApiUrl } from '../lib/api';
import type { ApiSection } from '../data/api-endpoints/types';
import type { ApiCategory } from '../lib/openapi-transform';
import type { RateLimitConfig } from '../lib/apiRateLimitMatch';
import { useOpenApiSchema } from './useOpenApiSchema';

export interface UseApiReferenceArgs { isAdmin: boolean; token: string | null }
export interface UseApiReferenceResult { /* ...as in Interfaces block... */ }

export function useApiReference({ isAdmin, token }: UseApiReferenceArgs): UseApiReferenceResult {
  const [activeView, setActiveView] = useState<'docs' | 'limits'>('docs');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [loading, setLoading] = useState(true);

  const {
    sections: apiSections, categories: apiCategories,
    loading: schemaLoading, error: schemaError, refetch: refetchSchema,
  } = useOpenApiSchema();

  const getApiBaseUrl = (): string => {
    const hostname = window.location.hostname;
    const isDev = import.meta.env.DEV;
    const port = isDev ? 3001 : 8000;
    const protocol = window.location.protocol;
    return `${protocol}//${hostname}:${port}`;
  };
  const apiBaseUrl = getApiBaseUrl();

  useEffect(() => {
    if (isAdmin) {
      loadRateLimits();
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const loadRateLimits = async () => {
    if (!token) { setLoading(false); return; }
    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits'), {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        const map: Record<string, RateLimitConfig> = {};
        data.configs.forEach((c: RateLimitConfig) => { map[c.endpoint_type] = c; });
        setRateLimits(map);
      }
    } catch {
      // Rate limits not available
    } finally {
      setLoading(false);
    }
  };

  const visibleSections = useMemo(() => {
    // copy the memo BODY, lines 306-325, verbatim (NOT line 326 — that is the
    // closing `}, [...]);` which this template already provides; copying it too
    // duplicates the closing and is a syntax error).
  }, [searchQuery, selectedCategory, selectedSection, apiSections, apiCategories]);

  const currentCategorySections = selectedCategory
    ? apiCategories.find(c => c.id === selectedCategory)?.sections ?? []
    : [];

  return {
    activeView, setActiveView, selectedCategory, setSelectedCategory,
    selectedSection, setSelectedSection, searchQuery, setSearchQuery,
    rateLimits, loading, apiBaseUrl,
    apiSections, apiCategories, schemaLoading, schemaError, refetchSchema,
    visibleSections, currentCategorySections,
  };
}
```

> Behaviour note: the effect dep array stays `[isAdmin]` (matches the original — it does NOT re-fetch on token change). The `eslint-disable-next-line react-hooks/exhaustive-deps` is a benign addition (the original relies on the ungated warning); it changes no behaviour and just silences the one warning this moved code would otherwise emit. `exhaustive-deps` is a warning, not part of the 0-error gate — the disable is cosmetic. `loadRateLimits` is referenced in the effect above its `const` declaration exactly as the original does; the deferred effect callback runs after the `const` is initialised, so there is no TDZ error.

- [ ] **Step 4: Run test to verify it passes**

Run (from `client/`): `npx vitest run src/__tests__/hooks/useApiReference.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useApiReference.ts client/src/__tests__/hooks/useApiReference.test.tsx
git commit -m "feat(api-ref): extract useApiReference state hook + tests (#301)"
```

---

### Task 3: `EndpointCard` presentation component

**Files:**
- Create: `client/src/components/manual/api-reference/EndpointCard.tsx`
- Test: `client/src/__tests__/components/manual/api-reference/EndpointCard.test.tsx`
- Source: `ApiReferenceTab.tsx:117-235` (the whole `EndpointCard` incl. its local state)

**Interfaces:**
- Consumes: `matchEndpointToRateLimitType`, `RateLimitConfig` from `lib/apiRateLimitMatch` (Task 1); `methodColors`, `ApiEndpoint` from `data/api-endpoints`.
- Produces: `export interface EndpointCardProps { endpoint: ApiEndpoint; rateLimits: Record<string, RateLimitConfig>; t: (key: string) => string }` and `export function EndpointCard(props: EndpointCardProps)`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/manual/api-reference/EndpointCard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EndpointCard } from '../../../../components/manual/api-reference/EndpointCard'
import type { ApiEndpoint } from '../../../../data/api-endpoints'

const t = (k: string) => k
const endpoint: ApiEndpoint = {
  method: 'POST', path: '/api/auth/login', description: 'Log in',
  requiresAuth: true,
  params: [], body: [], response: '{"token":"x"}',
} as ApiEndpoint

describe('EndpointCard', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
  })

  it('renders method, path and the auth shield', () => {
    render(<EndpointCard endpoint={endpoint} rateLimits={{}} t={t} />)
    expect(screen.getByText('POST')).toBeInTheDocument()
    expect(screen.getByText('/api/auth/login')).toBeInTheDocument()
    expect(screen.getByTitle('system:apiCenter.authRequired')).toBeInTheDocument()
  })

  it('shows the rate-limit badge when a matching config exists', () => {
    const rl = {
      auth_login: { id: 1, endpoint_type: 'auth_login', limit_string: '5/min',
        description: null, enabled: true, created_at: '', updated_at: null, updated_by: null },
    }
    render(<EndpointCard endpoint={endpoint} rateLimits={rl} t={t} />)
    expect(screen.getByText('5/min')).toBeInTheDocument()
  })

  it('expands to show the response and copies it', () => {
    render(<EndpointCard endpoint={endpoint} rateLimits={{}} t={t} />)
    // collapsed: response not shown
    expect(screen.queryByText('{"token":"x"}')).toBeNull()
    fireEvent.click(screen.getByText('/api/auth/login'))
    expect(screen.getByText('{"token":"x"}')).toBeInTheDocument()
    // after expansion the copy button is the only <button> in the card
    // (the header toggle is a <div onClick>, not a button)
    fireEvent.click(screen.getByRole('button'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('{"token":"x"}')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `client/`): `npx vitest run src/__tests__/components/manual/api-reference/EndpointCard.test.tsx`
Expected: FAIL — cannot resolve the component.

- [ ] **Step 3: Create the component (verbatim port)**

Create `client/src/components/manual/api-reference/EndpointCard.tsx`. Move `EndpointCard` from `ApiReferenceTab.tsx:117-235` **verbatim** (incl. `useState` for `isOpen`/`copied`, `copyToClipboard`, all JSX). Change only the imports:

```tsx
import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check, Zap, Shield } from 'lucide-react';
import { methodColors } from '../../../data/api-endpoints';
import type { ApiEndpoint } from '../../../data/api-endpoints';
import { matchEndpointToRateLimitType, type RateLimitConfig } from '../../../lib/apiRateLimitMatch';

export interface EndpointCardProps {
  endpoint: ApiEndpoint;
  rateLimits: Record<string, RateLimitConfig>;
  t: (key: string) => string;
}

export function EndpointCard({ endpoint, rateLimits, t }: EndpointCardProps) {
  // ... body verbatim from lines 126-234 ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `client/`): `npx vitest run src/__tests__/components/manual/api-reference/EndpointCard.test.tsx`
Expected: PASS. (The expanded card has exactly one `<button>` — the copy button — so `getByRole('button')` is unambiguous.)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/manual/api-reference/EndpointCard.tsx client/src/__tests__/components/manual/api-reference/EndpointCard.test.tsx
git commit -m "feat(api-ref): extract EndpointCard component + tests (#301)"
```

---

### Task 4: Remaining presentation components + barrel

**Files:**
- Create: `client/src/components/manual/api-reference/ApiViewToggle.tsx`
- Create: `client/src/components/manual/api-reference/ApiBaseUrlCard.tsx`
- Create: `client/src/components/manual/api-reference/ApiSearchBar.tsx`
- Create: `client/src/components/manual/api-reference/ApiCategoryTabs.tsx`
- Create: `client/src/components/manual/api-reference/ApiSchemaError.tsx`
- Create: `client/src/components/manual/api-reference/ApiLoadingSkeleton.tsx`
- Create: `client/src/components/manual/api-reference/ApiSectionList.tsx`
- Create: `client/src/components/manual/api-reference/index.ts`
- Test: `client/src/__tests__/components/manual/api-reference/ApiCategoryTabs.test.tsx`
- Test: `client/src/__tests__/components/manual/api-reference/ApiSectionList.test.tsx`
- Source ranges in `ApiReferenceTab.tsx`: view toggle `335-360`, schema error `380-395`, base-url card `398-426`, search `429-446`, category tabs `449-522`, loading skeleton `525-537`, section list `540-559`.

**Interfaces (props each component consumes; all values come from `useApiReference` in Task 5):**

```ts
// ApiViewToggle.tsx
export interface ApiViewToggleProps {
  activeView: 'docs' | 'limits';
  onChange: (v: 'docs' | 'limits') => void;
  t: (key: string) => string;
}
// ApiBaseUrlCard.tsx
export interface ApiBaseUrlCardProps { apiBaseUrl: string; t: (key: string) => string }
// ApiSearchBar.tsx
export interface ApiSearchBarProps {
  value: string; onChange: (q: string) => void; t: (key: string, fallback?: string) => string;
}
// ApiCategoryTabs.tsx
import type { ApiCategory } from '../../../lib/openapi-transform';
import type { ApiSection } from '../../../data/api-endpoints/types';
export interface ApiCategoryTabsProps {
  apiSections: ApiSection[];
  apiCategories: ApiCategory[];
  selectedCategory: string | null;
  selectedSection: string | null;
  currentCategorySections: ApiSection[];
  onSelectCategory: (id: string | null) => void;
  onSelectSection: (title: string | null) => void;
  t: (key: string) => string;
}
// ApiSchemaError.tsx
export interface ApiSchemaErrorProps { error: string; onRetry: () => void }
// ApiLoadingSkeleton.tsx  — no props
// ApiSectionList.tsx
export interface ApiSectionListProps {
  sections: ApiSection[];
  rateLimits: Record<string, RateLimitConfig>;
  t: (key: string) => string;
}
```

- [ ] **Step 1: Write the failing smoke tests (the two logic-bearing components)**

Create `client/src/__tests__/components/manual/api-reference/ApiCategoryTabs.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ApiCategoryTabs } from '../../../../components/manual/api-reference/ApiCategoryTabs'

const t = (k: string) => k
const section = (title: string) => ({ title, icon: null, endpoints: [
  { method: 'GET', path: `/api/${title}`, description: '', requiresAuth: false },
] })
const apiSections = [section('files'), section('auth')]
const apiCategories = [{ id: 'core', label: 'Core', sections: [section('files')] }]

describe('ApiCategoryTabs', () => {
  it('renders the "all" pill with the total endpoint count and per-category pills', () => {
    render(<ApiCategoryTabs apiSections={apiSections} apiCategories={apiCategories}
      selectedCategory={null} selectedSection={null} currentCategorySections={[]}
      onSelectCategory={vi.fn()} onSelectSection={vi.fn()} t={t} />)
    expect(screen.getByText('Core')).toBeInTheDocument()
    expect(screen.getByText('(2)')).toBeInTheDocument() // total endpoints across all sections
  })

  it('calls onSelectCategory when a category pill is clicked', () => {
    const onSelectCategory = vi.fn()
    render(<ApiCategoryTabs apiSections={apiSections} apiCategories={apiCategories}
      selectedCategory={null} selectedSection={null} currentCategorySections={[]}
      onSelectCategory={onSelectCategory} onSelectSection={vi.fn()} t={t} />)
    fireEvent.click(screen.getByText('Core'))
    expect(onSelectCategory).toHaveBeenCalledWith('core')
  })
})
```

Create `client/src/__tests__/components/manual/api-reference/ApiSectionList.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ApiSectionList } from '../../../../components/manual/api-reference/ApiSectionList'

const t = (k: string) => k
const sections = [{
  title: 'Files', icon: null,
  endpoints: [{ method: 'GET', path: '/api/files/list', description: 'List', requiresAuth: false }],
}]

describe('ApiSectionList', () => {
  it('renders a section header and its endpoint cards', () => {
    render(<ApiSectionList sections={sections} rateLimits={{}} t={t} />)
    expect(screen.getByText('Files')).toBeInTheDocument()
    expect(screen.getByText('/api/files/list')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the smoke tests to verify they fail**

Run (from `client/`): `npx vitest run src/__tests__/components/manual/api-reference/ApiCategoryTabs.test.tsx src/__tests__/components/manual/api-reference/ApiSectionList.test.tsx`
Expected: FAIL — components not found.

- [ ] **Step 3: Create the seven components (verbatim JSX slices) + barrel**

For each file, wrap the cited JSX slice from `ApiReferenceTab.tsx` in the component signature from the Interfaces block, substituting the orchestrator locals with props (`activeView`→`props.activeView`, `setActiveView(x)`→`onChange(x)`, `searchQuery`→`value`, `setSearchQuery`→`onChange`, `refetchSchema`→`onRetry`, `schemaError`→`error`, `apiBaseUrl`/`rateLimits`/`t` etc.). Keep all Tailwind classes and `t()` keys verbatim. `toast` stays only in `ApiBaseUrlCard` (base-url copy) — import `toast from 'react-hot-toast'` there. `ApiSectionList` renders `EndpointCard` (Task 3) per endpoint (verbatim map from `:549-556`). Icons per file: `ApiViewToggle` → `Code, Gauge`; `ApiBaseUrlCard` → `Code, Copy`; `ApiSearchBar` → `Search`; `ApiSchemaError` → `AlertTriangle`; `ApiCategoryTabs` → none (uses `section.icon`); `ApiLoadingSkeleton` → none; `ApiSectionList` → none.

Then create the barrel `client/src/components/manual/api-reference/index.ts`:

```ts
export { EndpointCard } from './EndpointCard';
export { ApiViewToggle } from './ApiViewToggle';
export { ApiBaseUrlCard } from './ApiBaseUrlCard';
export { ApiSearchBar } from './ApiSearchBar';
export { ApiCategoryTabs } from './ApiCategoryTabs';
export { ApiSchemaError } from './ApiSchemaError';
export { ApiLoadingSkeleton } from './ApiLoadingSkeleton';
export { ApiSectionList } from './ApiSectionList';
```

> `ApiViewToggle` renders ONLY the two toggle buttons (the `isAdmin` guard stays in the orchestrator). `ApiCategoryTabs` renders the whole `!searchQuery.trim()` block (`:449-522`) INCLUDING the sub-tab section; the orchestrator passes `selectedCategory`/`currentCategorySections` so the component decides internally whether to show sub-tabs (verbatim condition `selectedCategory && currentCategorySections.length > 0`).

- [ ] **Step 4: Run the smoke tests to verify they pass**

Run (from `client/`): `npx vitest run src/__tests__/components/manual/api-reference/`
Expected: PASS (EndpointCard + ApiCategoryTabs + ApiSectionList).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/manual/api-reference/ client/src/__tests__/components/manual/api-reference/ApiCategoryTabs.test.tsx client/src/__tests__/components/manual/api-reference/ApiSectionList.test.tsx
git commit -m "feat(api-ref): extract remaining api-reference presentation components + barrel (#301)"
```

---

### Task 5: Thin orchestrator + docs + full gates

**Files:**
- Modify: `client/src/components/manual/ApiReferenceTab.tsx` (replace body; keep `export interface ApiReferenceTabProps` + `export function ApiReferenceTab`)
- Modify: `client/src/components/CLAUDE.md` (add `api-reference/*` note to the `manual/` row)

**Interfaces:**
- Consumes: `useApiReference` (Task 2); all components via the `api-reference` barrel (Tasks 3–4); `RateLimitsTab` from `../rate-limits`.
- Produces: unchanged public API — `export interface ApiReferenceTabProps { isAdmin: boolean; token: string | null }`, `export function ApiReferenceTab(props: ApiReferenceTabProps)`.

- [ ] **Step 1: Rewrite the orchestrator**

Replace the entire contents of `client/src/components/manual/ApiReferenceTab.tsx` with the thin version (remove the now-extracted `RateLimitConfig`, `matchEndpointToRateLimitType`, `EndpointCard`, and all inline JSX/state):

```tsx
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { RateLimitsTab } from '../rate-limits';
import { useApiReference } from '../../hooks/useApiReference';
import {
  ApiViewToggle, ApiBaseUrlCard, ApiSearchBar, ApiCategoryTabs,
  ApiSchemaError, ApiLoadingSkeleton, ApiSectionList,
} from './api-reference';

export interface ApiReferenceTabProps {
  isAdmin: boolean;
  token: string | null;
}

export function ApiReferenceTab({ isAdmin, token }: ApiReferenceTabProps) {
  const { t } = useTranslation(['system', 'common']);
  const api = useApiReference({ isAdmin, token });

  return (
    <div className="space-y-4 sm:space-y-6">
      {isAdmin && (
        <ApiViewToggle activeView={api.activeView} onChange={api.setActiveView} t={t} />
      )}

      {api.activeView === 'limits' && isAdmin && <RateLimitsTab />}

      {api.activeView === 'docs' && <>
        {/* Refresh */}
        <div className="flex justify-end">
          <button
            onClick={api.refetchSchema}
            className="p-2 bg-slate-800/40 hover:bg-slate-700/60 border border-slate-700/50 rounded-lg transition-colors touch-manipulation active:scale-95"
            title="Refresh API schema"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${api.schemaLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {api.schemaError && <ApiSchemaError error={api.schemaError} onRetry={api.refetchSchema} />}

        <ApiBaseUrlCard apiBaseUrl={api.apiBaseUrl} t={t} />

        <ApiSearchBar value={api.searchQuery} onChange={api.setSearchQuery} t={t} />

        {!api.searchQuery.trim() && (
          <ApiCategoryTabs
            apiSections={api.apiSections}
            apiCategories={api.apiCategories}
            selectedCategory={api.selectedCategory}
            selectedSection={api.selectedSection}
            currentCategorySections={api.currentCategorySections}
            onSelectCategory={(id) => { api.setSelectedCategory(id); api.setSelectedSection(null); }}
            onSelectSection={api.setSelectedSection}
            t={t}
          />
        )}

        {(api.loading || api.schemaLoading) && <ApiLoadingSkeleton />}

        {!api.loading && !api.schemaLoading && (
          <ApiSectionList sections={api.visibleSections} rateLimits={api.rateLimits} t={t} />
        )}
      </>}
    </div>
  );
}
```

> The refresh button stays inline (12 lines, not worth a component). Note `onSelectCategory` folds the original `setSelectedCategory(x); setSelectedSection(null)` pair (from `:455` and `:470`); the "all" pill inside `ApiCategoryTabs` calls `onSelectCategory(null)` → same reset. Keep `ApiCategoryTabs`' internal "all" and sub-tab buttons calling `onSelectCategory`/`onSelectSection` exactly as the original wired them.

- [ ] **Step 2: Typecheck + build**

Run (from `client/`): `npm run build`
Expected: PASS (tsc -b clean; no unused imports; `ApiReferenceTab.tsx` now ~95–120 lines).

- [ ] **Step 3: Lint (0-error gate) + full unit suite**

Run (from `client/`): `npx eslint .`
Expected: 0 errors (warnings allowed).

Run (from `client/`): `npx vitest run`
Expected: all green, including the four new test files.

- [ ] **Step 4: Update `components/CLAUDE.md`**

In the `manual/` table row, append the decomposition note (mirroring the other F2 rows), e.g.:

```
| `manual/` | User manual article viewer — `ApiReferenceTab` composes `api-reference/*` (`EndpointCard`, `ApiViewToggle`, `ApiBaseUrlCard`, `ApiSearchBar`, `ApiCategoryTabs`, `ApiSchemaError`, `ApiLoadingSkeleton`, `ApiSectionList`) + pure `lib/apiRateLimitMatch`; state/fetch in `hooks/useApiReference` (extracted F2/#301) |
```

- [ ] **Step 5: Commit**

```bash
git add client/src/components/manual/ApiReferenceTab.tsx client/src/components/CLAUDE.md
git commit -m "refactor(api-ref): ApiReferenceTab thin orchestrator over api-reference/* + useApiReference (#301) [F2]"
```

---

### Task 6: Browser smoke verification

**Files:** none (manual verification against the running dev app).

- [ ] **Step 1: Start dev + open the API reference**

Run: `python start_dev.py` (backend :8000/:3001, frontend :5173). Log in (admin/DevMode2024). Navigate to the manual → API reference tab.

- [ ] **Step 2: Exercise the flows (verbatim behaviour check)**

Confirm each still works as before the refactor:
- Admin Docs↔Rate Limits toggle switches views; `RateLimitsTab` renders under "Rate Limits".
- Category pill + sub-tab selection narrows the list; the "all" pill resets.
- Search filters endpoints (path/description) and hides the category tabs while active.
- An endpoint card expands/collapses; the response copy button copies (toast/clipboard).
- Base-url copy button copies the URL and toasts.
- Refresh spins and reloads the schema; the rate-limit badges show for admin.

- [ ] **Step 3: Record the result**

Note the outcome in the PR description (what was exercised, all green). No Playwright needed — no drag/touch interaction.

---

## Self-Review

- **Spec coverage:** pure helper (T1), hook (T2), EndpointCard (T3), 7 presentation components + barrel (T4), thin orchestrator + CLAUDE.md (T5), browser smoke (T6), full gates (T5 S2–S3). Test plan table from the spec → covered by T1 (matcher branches), T3 (card), T2 (hook), T4 (category/section smoke). All spec sections map to a task.
- **Placeholder scan:** verbatim-port steps cite exact source line ranges + show the import/signature deltas; no "TBD"/"add error handling". Acceptable because the moved code already exists and is unambiguous.
- **Type consistency:** `RateLimitConfig` defined in T1, consumed by T2/T3/T4; `UseApiReferenceResult` field names in T2 match the orchestrator's `api.*` reads in T5; component prop names in T4 match the T5 call sites (`onChange`/`onRetry`/`onSelectCategory`/`onSelectSection`/`value`/`error`/`apiBaseUrl`/`sections`).
