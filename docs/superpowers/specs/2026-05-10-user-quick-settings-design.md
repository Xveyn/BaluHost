# User Quick-Settings Dropdown

**Date:** 2026-05-10
**Status:** Approved
**Scope:** Frontend-only feature that gives the topbar username dropdown a real purpose in production: language, byte units, and a 2FA-setup nudge.

## Problem

Clicking the username pill in the topbar does nothing useful in production today. In dev mode it shows the "Switch to user" submenu (impersonation), but production users see only a static `username` chip in the dropdown — no actions, no settings.

User-scoped preferences (UI language, GB vs GiB) live on the Settings page, two clicks away. The 2FA setup also lives there. There is no quick way for a user to flip these without leaving the current page.

## Goals

- Turn the existing UserMenu dropdown into a useful Quick-Settings panel without disturbing the dev-only impersonation submenu.
- Inline three sections: language switcher, byte-unit switcher, and a conditional 2FA setup prompt.
- Reuse all existing stores and APIs — no new backend endpoints, no new tables.
- Desktop-only; mobile/tablet layout stays untouched.

## Non-Goals

- Date/time format toggle (12h/24h, locale). The required Frontend refactor (85 files, 136 inline `toLocale*` callsites) is out of scope and will be handled by a separate spec ("DateTime Formatter Refactor + User Preferences"). Once that spec lands, a `DateTimeFormatSection` will be added to this dropdown — that future addition is explicitly designed for, but not implemented here.
- Theme switcher in the dropdown. The Theme picker on the Settings page stays the only entry point.
- Quick-action shortcuts ("Profile", "Logout", "Settings link"). Out of scope; the existing Power button next to the user pill already provides logout.
- A separate Mobile/Tablet variant of the dropdown. Mobile users keep using the full Settings page via the hamburger.
- 2FA disable, regenerate-backup-codes, or backup-code review from the dropdown. The dropdown only nudges users with no 2FA *yet*; everything else stays on the Settings page card.

## Architecture

```
Topbar (Layout.tsx)
  └─ UserMenu.tsx                              (existing)
       ├─ Trigger pill (username + role)        (existing)
       └─ Dropdown
            ├─ DevImpersonationSection         (existing, dev+admin only)
            └─ <UserMenuQuickSettings />       NEW
                 ├─ <LanguageSection />        NEW
                 ├─ <ByteUnitSection />        NEW
                 └─ <TwoFactorPromptSection /> NEW (conditional)
                       └─ opens <Modal>
                            └─ <TwoFactorSetupFlow />  NEW (extracted)

Settings page
  └─ TwoFactorCard.tsx                          (existing, refactored)
       └─ uses <TwoFactorSetupFlow />           (shared with the modal)
```

Three independent inline sections separated by thin `border-t border-slate-800` dividers. Each section owns its data source, its state, and its tests.

The dev-only impersonation submenu is not touched. It continues to render at the top of the dropdown when `systemMode?.dev_mode === true && isAdmin && !isImpersonating`. A `border-t` separator goes between it and the Quick-Settings block when both are present.

## Frontend

### Files

| Action | Path | Why |
|---|---|---|
| Create | `client/src/components/UserMenuQuickSettings.tsx` | Container for the three Quick-Settings sections |
| Create | `client/src/components/quickSettings/LanguageSection.tsx` | Language picker, reuses `availableLanguages` and `i18n.changeLanguage` |
| Create | `client/src/components/quickSettings/ByteUnitSection.tsx` | Byte-unit picker, reuses `useByteUnitMode()` |
| Create | `client/src/components/quickSettings/TwoFactorPromptSection.tsx` | Conditional "2FA not enabled" nudge |
| Create | `client/src/components/quickSettings/TwoFactorSetupFlow.tsx` | Extracted setup flow (QR → verify → backup codes), reused by Modal and Settings card |
| Create | `client/src/components/quickSettings/twoFactorStatusStore.ts` | Module-level cached 2FA status (lazy load, post-setup invalidation) |
| Modify | `client/src/components/UserMenu.tsx` | Render `<UserMenuQuickSettings />` inside the dropdown; keep impersonation untouched |
| Modify | `client/src/components/settings/TwoFactorCard.tsx` | Replace inline setup-flow render branches with `<TwoFactorSetupFlow />` |
| Modify | `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json` | New strings under a `userMenu.quickSettings.*` key block |

A small `quickSettings/` subdirectory keeps the section files together without polluting the top-level `components/` directory.

### `UserMenuQuickSettings`

```tsx
export default function UserMenuQuickSettings() {
  return (
    <div className="flex flex-col">
      <LanguageSection />
      <div className="border-t border-slate-800/70 my-1" />
      <ByteUnitSection />
      <TwoFactorPromptSection />  {/* renders nothing if not applicable; manages its own divider */}
    </div>
  );
}
```

The component is presentational only; each section owns its data and effects.

### `LanguageSection`

- Renders the existing `availableLanguages` array (currently DE + EN).
- Active language detected the same way `LanguageSettings.tsx` does it (`i18n.language === lang.code || i18n.language.startsWith(lang.code + '-')`), so the highlight matches whatever the user sees on the Settings page.
- Click calls `i18n.changeLanguage(lang.code)`. No API call. No close-on-click.
- Visually compact: a horizontal row of two pill buttons with flag + 2-letter code, not the vertical full-width list used on the Settings page (saves vertical real estate in the dropdown).

### `ByteUnitSection`

- Reuses `useByteUnitMode()` from `lib/byteUnits.ts`.
- Two pill buttons: "GiB" (binary) and "GB" (decimal). Sub-label shows "binär" / "dezimal" in tiny text.
- Click calls `setMode(mode)`. No close-on-click.
- All `formatBytes()` consumers re-render automatically through the `useSyncExternalStore` subscription that already exists.

### `TwoFactorPromptSection`

- On first render, calls `loadStatusOnce()` from `twoFactorStatusStore.ts`.
- While the status is `null` (loading or error): renders nothing (no loading skeleton, no flicker).
- If `status.enabled === true`: renders nothing.
- If `status.enabled === false`: renders a small amber-tinted block with `ShieldAlert` icon, label "2FA noch nicht aktiv", and a primary button "Jetzt einrichten". A `border-t` separator above the block is included by the section itself, so it disappears together with the block.
- Click on "Jetzt einrichten":
  1. Closes the dropdown.
  2. Opens a `<Modal>` containing `<TwoFactorSetupFlow onComplete={handleComplete} onCancel={closeModal} />`.
  3. On `onComplete`: invalidates the cached status (`refreshStatus()`), closes the modal. The next dropdown open will see `enabled: true` and the prompt is gone.

### `TwoFactorSetupFlow` (extracted from `TwoFactorCard`)

A pure, re-usable flow component. Props:

```tsx
interface TwoFactorSetupFlowProps {
  onComplete: () => void;     // called after the user clicks "Done" on the backup-codes screen
  onCancel: () => void;       // called when the user backs out of the QR/verify step
}
```

Internal state mirrors the existing logic in `TwoFactorCard.tsx:35-118`:

1. **Initial step:** call `setup2FA()` immediately on mount → render QR + manual secret + 6-digit verify input. Cancel button calls `onCancel`.
2. **Verify step:** call `verifySetup2FA(secret, code)` → on success, transition to backup-codes step.
3. **Backup-codes step:** display the codes in a 2-col grid, "Copy all" button (uses `navigator.clipboard`), "Done" button calls `onComplete`. Outside-click and Escape on the parent Modal are suppressed during this step so users do not lose their codes by accident. Implementation detail to verify in the plan: confirm whether `client/src/components/ui/Modal.tsx` already exposes props like `closeOnOverlayClick` / `closeOnEscape`. If not, the extension is in scope of this feature — the existing TwoFactorCard already needs the same protection on the backup-codes branch and currently has none, so adding the props is a strict improvement.

No card-wrapper styling. No header. The wrapping context (Modal in the dropdown case, Card in the Settings page case) provides the chrome.

### `TwoFactorCard` (refactor)

After extraction, `TwoFactorCard.tsx` keeps:

- Status loading + display (enabled / disabled badge with `enabled_at` timestamp).
- "Backup codes remaining" counter.
- Disable form (existing).
- Regenerate backup codes button (existing).
- The card chrome (`<h3>`, the Card wrapper).

When the user clicks "Enable 2FA" on the card, it now renders `<TwoFactorSetupFlow onComplete={…} onCancel={…} />` inline instead of the previous inline render branches. Behavior on the Settings page is unchanged.

### `twoFactorStatusStore` (cache)

A tiny module-level singleton — same pattern as `lib/byteUnits.ts`:

```ts
let cached: TwoFactorStatus | null = null;
let inflight: Promise<TwoFactorStatus> | null = null;

export async function loadStatusOnce(): Promise<TwoFactorStatus | null> {
  if (cached) return cached;
  if (inflight) return inflight;
  inflight = get2FAStatus().then(
    (s) => { cached = s; inflight = null; return s; },
    () => { inflight = null; return null; }   // swallow errors silently
  );
  return inflight;
}

export function refreshStatus(): void {
  cached = null;
}
```

The store is lazy: `loadStatusOnce()` is only called when the dropdown is opened for the first time in a session. Once loaded, every subsequent open is instant. After successful 2FA setup the dropdown invalidates the cache so the prompt disappears on next open.

A React-friendly hook wraps it:

```ts
export function useTwoFactorStatus(open: boolean): TwoFactorStatus | null {
  const [status, setStatus] = useState(cached);
  useEffect(() => {
    if (!open || cached !== null) return;
    let cancelled = false;
    loadStatusOnce().then((s) => { if (!cancelled) setStatus(s); });
    return () => { cancelled = true; };
  }, [open]);
  return status;
}
```

`TwoFactorPromptSection` calls `useTwoFactorStatus(true)` since it only renders when the dropdown is open (parent unmounts it on close).

### Behavior contract

| Event | Effect |
|---|---|
| User clicks the language pill | `i18n.changeLanguage()`; dropdown stays open; `LanguageDetector` persists to `localStorage['baluhost-language']` |
| User clicks the byte-unit pill | `setByteUnitMode()`; dropdown stays open; persisted to `localStorage['baluhost-byte-units']`; all consumers re-render via store subscription |
| User clicks "2FA jetzt einrichten" | Dropdown closes; Modal opens with `<TwoFactorSetupFlow />` |
| User completes 2FA setup | Modal closes; `refreshStatus()` invalidates the cache; on next dropdown open the section is gone |
| User cancels Modal mid-flow (QR or verify step) | Modal closes; status cache untouched; `users.totp_enabled` was never set on the backend, so the prompt stays |
| User opens the dropdown | First time: trigger lazy 2FA status load; subsequent times: instant from cache |
| Outside-click / Escape on the dropdown | Closes the dropdown; nothing else |
| Outside-click / Escape on the Modal during backup-codes step | Suppressed (user must click "Done") |
| 2FA status request fails | Section silently does not render; no toast; retried on next session (page reload) |
| Impersonation active | Quick-Settings remain functional; settings act on the browser-local store as today (not per-user). Out of scope to change. |

### Existing impersonation block

`UserMenu.tsx:84-152` already renders the impersonation submenu inside the dropdown. After this change, the dropdown JSX becomes:

```tsx
{open && (
  <div className="absolute right-0 mt-2 w-72 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
    {canSwitchUser && (
      <>
        <ImpersonationSubmenu /* existing block */ />
        <div className="border-t border-slate-800/70 my-1" />
      </>
    )}
    <UserMenuQuickSettings />
  </div>
)}
```

The `w-64 → w-72` widening accommodates the byte-unit row comfortably; impersonation submenu width was already 64 with chevron, fits in 72 fine.

The dev-only fallback `<div className="px-3 py-2 text-xs text-slate-500">{user.username}</div>` (line 151) is **deleted** — the dropdown is no longer empty in production.

### i18n strings

New keys under the `common` namespace, `userMenu.quickSettings`:

| Key | German | English |
|---|---|---|
| `language.title` | "Sprache" | "Language" |
| `byteUnits.title` | "Einheiten" | "Units" |
| `byteUnits.binaryShort` | "GiB" | "GiB" |
| `byteUnits.decimalShort` | "GB" | "GB" |
| `byteUnits.binaryHint` | "binär" | "binary" |
| `byteUnits.decimalHint` | "dezimal" | "decimal" |
| `twoFactor.notEnabled` | "2FA noch nicht aktiv" | "2FA not enabled yet" |
| `twoFactor.enableNow` | "Jetzt einrichten" | "Set up now" |
| `twoFactor.modalTitle` | "Zwei-Faktor-Authentifizierung einrichten" | "Set up Two-Factor Authentication" |

`TwoFactorSetupFlow` reuses the existing `settings.security.*` keys already defined for `TwoFactorCard` (setupStep1, setupStep2, manualEntry, verificationCode, verify, verifying, backupCodesTitle, backupCodesWarning, copyBackupCodes, backupCodesDone, cancel) — no duplication.

## Backend

No changes. All required endpoints exist:

- `GET /api/auth/2fa/status` — used today by `TwoFactorCard` via `get2FAStatus()`.
- `POST /api/auth/2fa/setup` — used today via `setup2FA()`.
- `POST /api/auth/2fa/verify-setup` — used today via `verifySetup2FA()`.

## Tests

### Vitest unit (new files)

- `client/src/components/quickSettings/__tests__/LanguageSection.test.tsx`
  - Renders the available languages.
  - Click triggers `i18n.changeLanguage` with the correct code.
  - The active language has the active styling.
- `client/src/components/quickSettings/__tests__/ByteUnitSection.test.tsx`
  - Renders both modes.
  - Click triggers `setByteUnitMode` and updates the active styling.
- `client/src/components/quickSettings/__tests__/TwoFactorPromptSection.test.tsx`
  - Renders nothing while status is loading.
  - Renders nothing when `enabled: true`.
  - Renders the prompt when `enabled: false`.
  - Click on "Set up now" calls the handler that opens the Modal.
- `client/src/components/quickSettings/__tests__/twoFactorStatusStore.test.ts`
  - First call hits the API once; second call is cache.
  - `refreshStatus()` invalidates so next call hits the API again.
  - Failed request resolves to `null` and does not throw.

### Playwright E2E (new file)

`client/tests/e2e/userMenuQuickSettings.spec.ts`:

- **Language switch round-trip:** open dropdown, click EN, sidebar label changes to English; click DE, label switches back.
- **Byte unit switch round-trip:** open Dashboard, observe storage card units, open dropdown, click GB, dashboard storage card now shows "GB" suffix; click GiB, returns to "GiB".
- **2FA prompt visible when not enabled:** with mocked `/api/auth/2fa/status` returning `{enabled: false}`, prompt is rendered; click opens the modal with QR; mock verify success; modal closes; reopen dropdown — prompt gone.
- **2FA prompt hidden when enabled:** with status `{enabled: true}`, prompt is not rendered.
- **Impersonation + Quick-Settings coexistence (dev mode):** impersonation submenu and Quick-Settings sections both visible in the dropdown.

### Manual smoke

- Run `python start_dev.py`, log in as admin, verify all three sections render, language and unit switching feels instant, 2FA modal opens and completes end-to-end.
- Disable 2FA on the Settings page, return to the dropdown, hard-reload, verify the prompt reappears (cache invalidation across sessions works because cache is module-level / per page-load).

### Tests touched on existing code

- `TwoFactorCard.tsx` extraction may invalidate any existing snapshot or behavioral tests around the setup-flow render branches. If such tests exist (unlikely based on the search done during brainstorming), they move to the new `TwoFactorSetupFlow` test file.

## Implementation Order

1. Extract `TwoFactorSetupFlow` from `TwoFactorCard`; verify Settings page still works.
2. Add `twoFactorStatusStore` with hook + tests.
3. Add `ByteUnitSection`, `LanguageSection` with tests.
4. Add `TwoFactorPromptSection` with tests.
5. Add `UserMenuQuickSettings` container.
6. Wire into `UserMenu.tsx`, delete the dev-only fallback, widen the dropdown.
7. Add i18n keys for both languages.
8. E2E test pass.
9. Manual smoke in dev.

Steps 1–4 are independent and can be done in parallel.

## Open Questions

None at spec time. All branching decisions (caching strategy, modal close-suppression on backup step, impersonation interaction, mobile out-of-scope) are settled above.
