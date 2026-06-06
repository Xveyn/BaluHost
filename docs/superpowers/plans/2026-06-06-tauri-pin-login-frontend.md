# Tauri PIN Login — Frontend Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Frontend for signing into the Tauri Companion app with a PIN (consuming the Plan-1 backend): a PIN login option on the Login screen (Tauri-only), a "Desktop-App PIN" management section (set/remove, TOTP-gated, only when 2FA on), and an admin auth-policy card (grace window + kill switch).

**Architecture:** Reuse the existing Login 2FA step (`pending_token` → `verify-2fa`). PIN login posts to `/api/auth/login-pin` and, when the grace window has expired, falls into the **same** existing TOTP step. PIN management + admin policy use the authenticated `apiClient`. The PIN login option is shown only when running inside the Tauri shell, detected pre-auth via `window.__BALU_API_BASE__`.

**Tech Stack:** React 18 + TypeScript + Vite, axios (`apiClient`), react-i18next, Vitest + Testing Library.

Spec: `docs/superpowers/specs/2026-06-06-tauri-pin-login-design.md`. Backend is **Plan 1** (already implemented). Endpoints consumed: `POST /api/auth/login-pin`, `GET/POST/DELETE /api/auth/pin`, `GET/PUT /api/admin/auth-policy`, existing `POST /api/auth/verify-2fa`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `client/src/lib/api.ts` | API base + Tauri detection | export `isTauri` flag |
| `client/src/api/pin.ts` | PIN + auth-policy API client | NEW |
| `client/src/pages/Login.tsx` | login screen | PIN-login mode (Tauri-only) |
| `client/src/components/settings/DesktopPinSettings.tsx` | set/remove PIN | NEW |
| `client/src/components/admin/AuthPolicySettings.tsx` | admin window + kill switch | NEW |
| `client/src/i18n/locales/{de,en}/login.json` | login strings | +PIN keys |
| `client/src/i18n/locales/{de,en}/settings.json` | settings strings | +PIN keys |
| `client/src/api/__tests__/pin.test.ts` | API client tests | NEW |

---

## Task 1: `isTauri` flag + PIN API client

**Files:**
- Modify: `client/src/lib/api.ts`
- Create: `client/src/api/pin.ts`
- Test: `client/src/api/__tests__/pin.test.ts`

- [ ] **Step 1: Export an `isTauri` flag**

In `client/src/lib/api.ts`, immediately after the `tauriApiBase` const (the block ending `: undefined;`), add:

```typescript
/** True when running inside the Tauri Companion shell (local channel). Read
 *  synchronously at module load; safe to use pre-auth on the Login screen. */
export const isTauri = Boolean(tauriApiBase);
```

- [ ] **Step 2: Write the failing test**

Create `client/src/api/__tests__/pin.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  buildApiUrl: (p: string) => p,
}));

import { apiClient } from '../../lib/api';
import { getPinStatus, setPin, removePin } from '../pin';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('pin api client', () => {
  it('getPinStatus returns pin_enabled', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { pin_enabled: true } } as any);
    const r = await getPinStatus();
    expect(r.pin_enabled).toBe(true);
    expect(apiClient.get).toHaveBeenCalledWith('/api/auth/pin');
  });

  it('setPin posts pin + code', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { message: 'PIN set' } } as any);
    await setPin('4827', '123456');
    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/pin', { pin: '4827', code: '123456' });
  });

  it('removePin sends code in the request body', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { message: 'PIN removed' } } as any);
    await removePin('123456');
    expect(apiClient.delete).toHaveBeenCalledWith('/api/auth/pin', { data: { code: '123456' } });
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx vitest run src/api/__tests__/pin.test.ts`
Expected: FAIL — cannot resolve `../pin`.

- [ ] **Step 4: Create the API client**

Create `client/src/api/pin.ts`:

```typescript
/** PIN login + management + admin auth-policy API client. */
import { apiClient, buildApiUrl } from '../lib/api';
import type { User } from '../types/auth';

export interface PinStatus {
  pin_enabled: boolean;
}

export interface AuthPolicy {
  pin_login_enabled: boolean;
  pin_grace_window_seconds: number;
}

/** Either a finished login (access_token) or a 2FA challenge (pending_token). */
export interface PinLoginResult {
  access_token?: string;
  user?: User;
  requires_2fa?: boolean;
  pending_token?: string;
  detail?: string;
}

/** PIN login is pre-auth and local-channel only — mirror Login.tsx's fetch path. */
export async function loginWithPin(username: string, pin: string): Promise<PinLoginResult> {
  const res = await fetch(buildApiUrl('/api/auth/login-pin'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, pin }),
  });
  const data = (await res.json().catch(() => ({}))) as PinLoginResult;
  if (!res.ok) {
    throw new Error(String(data.detail || `PIN login failed (${res.status})`));
  }
  return data;
}

export async function getPinStatus(): Promise<PinStatus> {
  const res = await apiClient.get<PinStatus>('/api/auth/pin');
  return res.data;
}

export async function setPin(pin: string, code: string): Promise<void> {
  await apiClient.post('/api/auth/pin', { pin, code });
}

export async function removePin(code: string): Promise<void> {
  await apiClient.delete('/api/auth/pin', { data: { code } });
}

export async function getAuthPolicy(): Promise<AuthPolicy> {
  const res = await apiClient.get<AuthPolicy>('/api/admin/auth-policy');
  return res.data;
}

export async function updateAuthPolicy(body: Partial<AuthPolicy>): Promise<AuthPolicy> {
  const res = await apiClient.put<AuthPolicy>('/api/admin/auth-policy', body);
  return res.data;
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx vitest run src/api/__tests__/pin.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add client/src/lib/api.ts client/src/api/pin.ts client/src/api/__tests__/pin.test.ts
git commit -m "feat(client): isTauri flag + PIN/auth-policy API client"
```

---

## Task 2: PIN login option on the Login screen

**Files:**
- Modify: `client/src/pages/Login.tsx`

> Context: `Login.tsx` already has a 2FA step (`twoFactorRequired`, `pendingToken`, `totpCode`,
> `handleVerify2FA`). PIN login reuses it: a PIN login that returns `requires_2fa` drops into the
> exact same TOTP step. Show the PIN option only when `isTauri`.

- [ ] **Step 1: Add imports + state**

In `client/src/pages/Login.tsx`:
- Add to the import from `../lib/api`: `import { buildApiUrl, isTauri } from '../lib/api';` (replace the existing `import { buildApiUrl } from '../lib/api';`).
- Add: `import { loginWithPin } from '../api/pin';`
- After the line `const [showPassword, setShowPassword] = useState(false);` add:

```tsx
  const [pinMode, setPinMode] = useState(false);
  const [pin, setPin] = useState('');
```

- [ ] **Step 2: Add the PIN submit handler**

Immediately after `handleSubmit` (after its closing `};`), add:

```tsx
  const handlePinSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await loginWithPin(username, pin);
      if (result.requires_2fa) {
        setPendingToken(String(result.pending_token ?? ''));
        setTwoFactorRequired(true);
        setLoading(false);
        return;
      }
      if (typeof result.access_token === 'string' && result.user) {
        login(result.user, result.access_token);
        return;
      }
      throw new Error('PIN login did not return a token');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'PIN login failed');
      setPin('');
    } finally {
      setLoading(false);
    }
  };
```

- [ ] **Step 3: Render the PIN form + toggle**

In the JSX, replace the `/* Regular Login Form */` block — i.e. the `<>...</>` that starts right after
`) : (` (the else branch of `twoFactorRequired ? (...) : (...)`) — so it conditionally renders the PIN
form when `pinMode`. Concretely, change the opening of that else-branch from:

```tsx
            /* Regular Login Form */
            <>
              <form onSubmit={handleSubmit} className="mt-8 sm:mt-10 space-y-4 sm:space-y-5">
```

to:

```tsx
            /* Regular Login Form */
            <>
              {pinMode ? (
                <form onSubmit={handlePinSubmit} className="mt-8 sm:mt-10 space-y-4 sm:space-y-5">
                  {error && (
                    <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 sm:px-4 py-2.5 sm:py-3 text-sm text-rose-200">
                      {error}
                    </div>
                  )}
                  <div className="space-y-2">
                    <label htmlFor="pin-username" className="text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary">
                      {t('form.username')}
                    </label>
                    <input
                      type="text" id="pin-username" className="input"
                      value={username} onChange={(e) => setUsername(e.target.value)}
                      placeholder="admin" required
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="pin" className="text-xs font-medium uppercase tracking-[0.2em] text-slate-100-tertiary">
                      {t('pin.label')}
                    </label>
                    <input
                      type="password" id="pin"
                      className="input text-center text-2xl tracking-[0.5em] font-mono"
                      value={pin}
                      onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
                      placeholder="••••" inputMode="numeric" autoComplete="off" required
                    />
                  </div>
                  <button type="submit" className="btn btn-primary w-full mt-5 sm:mt-6 touch-manipulation active:scale-[0.98]" disabled={loading || pin.length < 4}>
                    {loading ? t('form.loading') : t('pin.submit')}
                  </button>
                  <button type="button" onClick={() => { setPinMode(false); setError(''); setPin(''); }} className="w-full text-center text-sm text-slate-100-tertiary hover:text-slate-100-secondary transition-colors">
                    {t('pin.usePassword')}
                  </button>
                </form>
              ) : (
              <form onSubmit={handleSubmit} className="mt-8 sm:mt-10 space-y-4 sm:space-y-5">
```

Then find the **end** of that password `<form>` (the closing `</form>` right before the
`{devCredentials && (` block) and immediately after that `</form>` add the closing of the ternary plus
the "Use PIN" toggle (Tauri-only):

```tsx
              </form>
              )}

              {isTauri && !pinMode && (
                <button
                  type="button"
                  onClick={() => { setPinMode(true); setError(''); setPassword(''); }}
                  className="mt-3 w-full text-center text-sm text-slate-100-tertiary hover:text-slate-100-secondary transition-colors"
                >
                  {t('pin.usePin')}
                </button>
              )}
```

(That replaces the single `</form>` that preceded `{devCredentials && (`.)

- [ ] **Step 4: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 5: Manual sanity (web build has no Tauri, so the toggle is hidden)**

Run: `cd client && npm run build`
Expected: build succeeds. (`isTauri` is `false` in the web build → PIN toggle not rendered; password login unchanged.)

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/Login.tsx
git commit -m "feat(client): PIN login option on the Login screen (Tauri-only)"
```

---

## Task 3: Login i18n keys (DE + EN)

**Files:**
- Modify: `client/src/i18n/locales/de/login.json`
- Modify: `client/src/i18n/locales/en/login.json`

- [ ] **Step 1: Add a `pin` block to German login.json**

In `client/src/i18n/locales/de/login.json`, add a top-level `"pin"` object (place it next to the
existing `"twoFactor"` / `"form"` objects — match the file's structure):

```json
  "pin": {
    "label": "PIN",
    "submit": "Mit PIN anmelden",
    "usePin": "Stattdessen PIN verwenden",
    "usePassword": "Passwort verwenden"
  }
```

- [ ] **Step 2: Add the same block to English login.json**

In `client/src/i18n/locales/en/login.json`:

```json
  "pin": {
    "label": "PIN",
    "submit": "Sign in with PIN",
    "usePin": "Use a PIN instead",
    "usePassword": "Use password"
  }
```

- [ ] **Step 3: Validate JSON**

Run:
```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/login.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/login.json','utf8')); console.log('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/login.json client/src/i18n/locales/en/login.json
git commit -m "i18n(login): PIN login strings (de/en)"
```

---

## Task 4: Desktop-App PIN settings section

**Files:**
- Create: `client/src/components/settings/DesktopPinSettings.tsx`
- Modify: the security/2FA settings host component (located in Step 1)
- Modify: `client/src/i18n/locales/{de,en}/settings.json`

- [ ] **Step 1: Locate the 2FA settings host**

Find the component that renders the 2FA management UI (it calls `/api/auth/2fa/setup` or shows
2FA status). Use the vectordb MCP: `mcp__vectordb-search__search_files` with query
"two factor 2FA settings component setup enable disable" and `projectPath` `D:/Programme (x86)/Baluhost`.
Likely under `client/src/components/settings/`. Open it; note its file path and the place where the
2FA block ends — you will mount `<DesktopPinSettings />` right after it. Note which i18n namespace it
uses (`useTranslation('settings')` is expected).

- [ ] **Step 2: Add settings i18n keys (DE + EN)**

In `client/src/i18n/locales/de/settings.json`, add (match the file's nesting — top-level `"pin"` object):

```json
  "pin": {
    "title": "Desktop-App-PIN",
    "description": "Melde dich in der BaluHost-Companion-App mit einer PIN statt dem Passwort an (erfordert aktives 2FA).",
    "enabled": "PIN aktiv",
    "disabled": "Keine PIN gesetzt",
    "needs2fa": "Aktiviere zuerst die Zwei-Faktor-Authentifizierung.",
    "pinLabel": "PIN (4–8 Ziffern)",
    "confirmLabel": "PIN bestätigen",
    "codeLabel": "2FA-Code",
    "save": "PIN speichern",
    "remove": "PIN entfernen",
    "mismatch": "Die PINs stimmen nicht überein.",
    "saved": "PIN gespeichert",
    "removed": "PIN entfernt",
    "saveError": "PIN konnte nicht gespeichert werden",
    "removeError": "PIN konnte nicht entfernt werden"
  }
```

In `client/src/i18n/locales/en/settings.json`:

```json
  "pin": {
    "title": "Desktop app PIN",
    "description": "Sign in to the BaluHost Companion app with a PIN instead of your password (requires 2FA enabled).",
    "enabled": "PIN active",
    "disabled": "No PIN set",
    "needs2fa": "Enable two-factor authentication first.",
    "pinLabel": "PIN (4–8 digits)",
    "confirmLabel": "Confirm PIN",
    "codeLabel": "2FA code",
    "save": "Save PIN",
    "remove": "Remove PIN",
    "mismatch": "The PINs do not match.",
    "saved": "PIN saved",
    "removed": "PIN removed",
    "saveError": "Could not save PIN",
    "removeError": "Could not remove PIN"
  }
```

- [ ] **Step 3: Create the component**

Create `client/src/components/settings/DesktopPinSettings.tsx`:

```tsx
/** Desktop-app PIN management — visible only when 2FA is enabled. */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { getPinStatus, setPin as apiSetPin, removePin } from '../../api/pin';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  twoFactorEnabled: boolean;
}

export function DesktopPinSettings({ twoFactorEnabled }: Props) {
  const { t } = useTranslation('settings');
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pin, setPinValue] = useState('');
  const [confirm, setConfirm] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!twoFactorEnabled) { setLoading(false); return; }
    getPinStatus()
      .then((s) => setEnabled(s.pin_enabled))
      .catch(() => setEnabled(false))
      .finally(() => setLoading(false));
  }, [twoFactorEnabled]);

  const onSave = async () => {
    if (pin !== confirm) { toast.error(t('pin.mismatch')); return; }
    setBusy(true);
    try {
      await apiSetPin(pin, code);
      setEnabled(true);
      setPinValue(''); setConfirm(''); setCode('');
      toast.success(t('pin.saved'));
    } catch (err) {
      handleApiError(err, t('pin.saveError'));
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async () => {
    setBusy(true);
    try {
      await removePin(code);
      setEnabled(false);
      setCode('');
      toast.success(t('pin.removed'));
    } catch (err) {
      handleApiError(err, t('pin.removeError'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-semibold text-slate-100">{t('pin.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">{t('pin.description')}</p>

      {!twoFactorEnabled ? (
        <p className="mt-4 text-sm text-amber-300">{t('pin.needs2fa')}</p>
      ) : (
        <div className="mt-4 space-y-3">
          <p className="text-sm">
            <span className={enabled ? 'text-emerald-400' : 'text-slate-400'}>
              {enabled ? t('pin.enabled') : t('pin.disabled')}
            </span>
          </p>

          {!enabled && (
            <>
              <input type="password" inputMode="numeric" placeholder={t('pin.pinLabel')}
                className="input" value={pin}
                onChange={(e) => setPinValue(e.target.value.replace(/\D/g, '').slice(0, 8))} />
              <input type="password" inputMode="numeric" placeholder={t('pin.confirmLabel')}
                className="input" value={confirm}
                onChange={(e) => setConfirm(e.target.value.replace(/\D/g, '').slice(0, 8))} />
            </>
          )}

          <input type="text" inputMode="numeric" placeholder={t('pin.codeLabel')}
            className="input" value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
            autoComplete="one-time-code" />

          <div className="flex gap-2">
            {!enabled ? (
              <button className="btn btn-primary" disabled={busy || pin.length < 4 || code.length < 6} onClick={onSave}>
                {t('pin.save')}
              </button>
            ) : (
              <button className="btn btn-danger" disabled={busy || code.length < 6} onClick={onRemove}>
                {t('pin.remove')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Mount it after the 2FA block**

In the host component found in Step 1, import and render the section, passing the host's existing
2FA-enabled boolean (whatever it is named there — it tracks `totp` status):

```tsx
import { DesktopPinSettings } from './DesktopPinSettings';
// ...after the 2FA management block:
<DesktopPinSettings twoFactorEnabled={/* the host's 2FA-enabled state */} />
```

- [ ] **Step 5: Type-check + JSON validate**

Run: `cd client && npx tsc --noEmit && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/settings.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/settings.json','utf8')); console.log('OK')"`
Expected: no TS errors; `OK`.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/settings/DesktopPinSettings.tsx client/src/i18n/locales/de/settings.json client/src/i18n/locales/en/settings.json <host-component-path>
git commit -m "feat(settings): Desktop-app PIN management section (2FA-gated)"
```

---

## Task 5: Admin auth-policy card

**Files:**
- Create: `client/src/components/admin/AuthPolicySettings.tsx`
- Modify: an admin settings host (located in Step 1)
- Modify: `client/src/i18n/locales/{de,en}/admin.json`

- [ ] **Step 1: Locate an admin settings host**

Find an admin-only settings page/section to host the card — e.g. where rate-limit config or other
admin settings render. Use vectordb: `mcp__vectordb-search__search_files` query "admin settings page
rate limit config security" (`projectPath` `D:/Programme (x86)/Baluhost`). Note the file + a sensible
mount point and its i18n namespace (`admin` expected).

- [ ] **Step 2: Add admin i18n keys (DE + EN)**

`client/src/i18n/locales/de/admin.json` — add a top-level `"authPolicy"` object:

```json
  "authPolicy": {
    "title": "PIN-Login-Richtlinie",
    "description": "Steuert das Gnadenfenster, in dem die Desktop-App-PIN ohne 2FA-Code genügt.",
    "enabled": "PIN-Login aktiviert",
    "window": "Gnadenfenster",
    "saved": "Richtlinie gespeichert",
    "saveError": "Richtlinie konnte nicht gespeichert werden",
    "windows": { "1h": "1 Stunde", "8h": "8 Stunden", "24h": "24 Stunden", "7d": "7 Tage" }
  }
```

`client/src/i18n/locales/en/admin.json`:

```json
  "authPolicy": {
    "title": "PIN login policy",
    "description": "Controls the grace window in which the desktop-app PIN suffices without a 2FA code.",
    "enabled": "PIN login enabled",
    "window": "Grace window",
    "saved": "Policy saved",
    "saveError": "Could not save policy",
    "windows": { "1h": "1 hour", "8h": "8 hours", "24h": "24 hours", "7d": "7 days" }
  }
```

- [ ] **Step 3: Create the component**

Create `client/src/components/admin/AuthPolicySettings.tsx`:

```tsx
/** Admin: system-wide PIN-login policy (grace window + kill switch). */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { getAuthPolicy, updateAuthPolicy } from '../../api/pin';
import { handleApiError } from '../../lib/errorHandling';

const WINDOW_OPTIONS: { key: string; seconds: number }[] = [
  { key: '1h', seconds: 3600 },
  { key: '8h', seconds: 28800 },
  { key: '24h', seconds: 86400 },
  { key: '7d', seconds: 604800 },
];

export function AuthPolicySettings() {
  const { t } = useTranslation('admin');
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [windowSeconds, setWindowSeconds] = useState(86400);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAuthPolicy()
      .then((p) => { setEnabled(p.pin_login_enabled); setWindowSeconds(p.pin_grace_window_seconds); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async (next: { pin_login_enabled?: boolean; pin_grace_window_seconds?: number }) => {
    setBusy(true);
    try {
      const p = await updateAuthPolicy(next);
      setEnabled(p.pin_login_enabled);
      setWindowSeconds(p.pin_grace_window_seconds);
      toast.success(t('authPolicy.saved'));
    } catch (err) {
      handleApiError(err, t('authPolicy.saveError'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-semibold text-slate-100">{t('authPolicy.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">{t('authPolicy.description')}</p>

      <label className="mt-4 flex items-center justify-between">
        <span className="text-sm text-slate-300">{t('authPolicy.enabled')}</span>
        <input type="checkbox" checked={enabled} disabled={busy}
          onChange={(e) => save({ pin_login_enabled: e.target.checked })}
          className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50" />
      </label>

      <label className="mt-4 block text-sm text-slate-300">
        {t('authPolicy.window')}
        <select className="input mt-1" value={windowSeconds} disabled={busy}
          onChange={(e) => save({ pin_grace_window_seconds: Number(e.target.value) })}>
          {WINDOW_OPTIONS.map((o) => (
            <option key={o.key} value={o.seconds}>{t(`authPolicy.windows.${o.key}`)}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Mount it in the admin host**

In the admin host found in Step 1, import and render `<AuthPolicySettings />` at a sensible spot:

```tsx
import { AuthPolicySettings } from '../admin/AuthPolicySettings';
// ...
<AuthPolicySettings />
```

(Adjust the relative import path to the host's location.)

- [ ] **Step 5: Type-check + JSON validate**

Run: `cd client && npx tsc --noEmit && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/admin.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/admin.json','utf8')); console.log('OK')"`
Expected: no TS errors; `OK`.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/admin/AuthPolicySettings.tsx client/src/i18n/locales/de/admin.json client/src/i18n/locales/en/admin.json <host-component-path>
git commit -m "feat(admin): PIN-login policy settings card"
```

---

## Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the new unit test + full vitest suite**

Run: `cd client && npx vitest run`
Expected: all green (incl. `src/api/__tests__/pin.test.ts`).

- [ ] **Step 2: Production build (type-check)**

Run: `cd client && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke (dev)**

1. `python start_dev.py`; in the web UI (not Tauri) the PIN login toggle is **absent** (isTauri false) — password login unchanged.
2. Enable 2FA for a user, then in Settings → Desktop-App PIN: set a PIN (enter a TOTP code).
3. Admin settings → PIN login policy: set the window / toggle the kill switch.
4. (Tauri smoke is part of the Companion app run, not this web flow.)

- [ ] **Step 4: No commit** (verification only).

---

## Notes for the implementer

- **Tauri-only gating:** the PIN login option keys off `isTauri` (`window.__BALU_API_BASE__`), so the web build never shows it. The backend additionally enforces local-channel (403), so this is defense-in-depth, not the only gate.
- **2FA-step reuse:** a PIN login that returns `requires_2fa` flows into the **existing** `handleVerify2FA` step — do not duplicate the TOTP UI.
- **Mount points (Tasks 4–5)** are located during implementation via vectordb (the host components aren't pinned in this plan); everything else has exact anchors.
- `handleApiError` is in `client/src/lib/errorHandling.ts` (`handleApiError(err, fallback)` shows a toast). `User` type is in `client/src/types/auth.ts`.
```
