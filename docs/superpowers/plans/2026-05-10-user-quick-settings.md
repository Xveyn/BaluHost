# User Quick-Settings Dropdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the topbar username dropdown useful in production by adding three Quick-Settings sections — language, byte units, and a conditional 2FA setup nudge — without disturbing the existing dev-only impersonation submenu.

**Architecture:** One container component (`UserMenuQuickSettings`) holds three independent inline sections. Language and byte-unit sections reuse existing module-level stores (`i18next`, `lib/byteUnits.ts`). The 2FA prompt section uses a tiny lazy-loaded module-level cache for status; clicking "Set up now" opens a Modal containing a `TwoFactorSetupFlow` component extracted from the existing `TwoFactorCard`. The Modal is extended with `closeOnOverlayClick` / `closeOnEscape` props so the backup-codes step can suppress accidental dismissal.

**Tech Stack:** React 18 + TypeScript + Tailwind, `i18next` + `react-i18next`, `react-hot-toast`, Vitest + `@testing-library/react`, Playwright for E2E.

**Spec:** [`docs/superpowers/specs/2026-05-10-user-quick-settings-design.md`](../specs/2026-05-10-user-quick-settings-design.md)

---

## File Structure

| Action | Path | Purpose |
|---|---|---|
| Create | `client/src/components/quickSettings/twoFactorStatusStore.ts` | Lazy module-level cache + React hook for `/api/auth/2fa/status` |
| Create | `client/src/components/quickSettings/TwoFactorSetupFlow.tsx` | Extracted setup flow (QR → verify → backup codes); shared between Settings card and Modal |
| Create | `client/src/components/quickSettings/LanguageSection.tsx` | Compact horizontal language picker |
| Create | `client/src/components/quickSettings/ByteUnitSection.tsx` | Compact horizontal byte-unit picker |
| Create | `client/src/components/quickSettings/TwoFactorPromptSection.tsx` | Conditional "2FA not enabled" block + Modal trigger |
| Create | `client/src/components/UserMenuQuickSettings.tsx` | Container that composes the three sections |
| Modify | `client/src/components/ui/Modal.tsx` | Add optional `closeOnOverlayClick` and `closeOnEscape` props (default `true` for backwards compat) |
| Modify | `client/src/components/settings/TwoFactorCard.tsx` | Replace inline setup-render branches with `<TwoFactorSetupFlow />`; keep status display, disable, regenerate |
| Modify | `client/src/components/UserMenu.tsx` | Render `<UserMenuQuickSettings />`; widen dropdown `w-64` → `w-72`; add divider above; delete production-fallback `<div>username</div>` |
| Modify | `client/src/i18n/locales/de/common.json` | Add `userMenu.quickSettings.*` keys |
| Modify | `client/src/i18n/locales/en/common.json` | Add `userMenu.quickSettings.*` keys |
| Create | `client/src/__tests__/components/ui/Modal.test.tsx` | Unit tests for the new close-suppression props |
| Create | `client/src/__tests__/components/quickSettings/twoFactorStatusStore.test.ts` | Cache + hook tests |
| Create | `client/src/__tests__/components/quickSettings/LanguageSection.test.tsx` | Render + click + active state |
| Create | `client/src/__tests__/components/quickSettings/ByteUnitSection.test.tsx` | Render + click + active state |
| Create | `client/src/__tests__/components/quickSettings/TwoFactorPromptSection.test.tsx` | Conditional rendering by status |
| Create | `client/src/__tests__/components/quickSettings/TwoFactorSetupFlow.test.tsx` | Three-step state machine |
| Create | `client/src/__tests__/components/UserMenuQuickSettings.test.tsx` | Composition test |
| Create | `client/tests/e2e/userMenuQuickSettings.spec.ts` | E2E: language switch, unit switch, 2FA prompt visibility |

Tests live under `client/src/__tests__/` mirroring source paths — this is the established project convention (see `vite.config.ts:60-65` `include` glob).

---

## Task 1: Extend `Modal` with optional close-suppression props

**Why first:** `TwoFactorSetupFlow`'s backup-codes step depends on these props. Doing it first means subsequent tasks can use the props without forward references. Defaults preserve existing behavior — no other consumer is affected.

**Files:**
- Modify: `client/src/components/ui/Modal.tsx`
- Create: `client/src/__tests__/components/ui/Modal.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/ui/Modal.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { Modal } from '../../../components/ui/Modal';

describe('Modal close-suppression props', () => {
  it('closes on overlay click by default', () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal isOpen onClose={onClose} title="X">body</Modal>
    );
    const backdrop = container.querySelector('.bg-black\\/50') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not close on overlay click when closeOnOverlayClick=false', () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal isOpen onClose={onClose} title="X" closeOnOverlayClick={false}>body</Modal>
    );
    const backdrop = container.querySelector('.bg-black\\/50') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes on Escape by default', () => {
    const onClose = vi.fn();
    render(<Modal isOpen onClose={onClose} title="X">body</Modal>);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not close on Escape when closeOnEscape=false', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="X" closeOnEscape={false}>body</Modal>
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `client/`:
```bash
npm test -- src/__tests__/components/ui/Modal.test.tsx
```
Expected: 2 of 4 fail (`closeOnOverlayClick=false` case + `closeOnEscape=false` case) because the props don't exist yet. The two default-behavior tests pass.

- [ ] **Step 3: Implement the props**

Replace the file `client/src/components/ui/Modal.tsx` with:

```tsx
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /** Close when the user clicks the backdrop. Default: true. */
  closeOnOverlayClick?: boolean;
  /** Close when the user presses Escape. Default: true. */
  closeOnEscape?: boolean;
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  closeOnOverlayClick = true,
  closeOnEscape = true,
}: ModalProps) {
  const sizeClasses = {
    sm: 'max-w-[95vw] sm:max-w-sm',
    md: 'max-w-[95vw] sm:max-w-md',
    lg: 'max-w-[95vw] sm:max-w-lg',
    xl: 'max-w-[95vw] sm:max-w-xl',
    '2xl': 'max-w-[95vw] sm:max-w-2xl lg:max-w-4xl',
  };

  useEffect(() => {
    if (!closeOnEscape) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={closeOnOverlayClick ? onClose : undefined}
      />
      <div
        className={`relative w-full ${sizeClasses[size]} max-h-[90vh] bg-slate-900 border border-slate-800/60 rounded-xl shadow-2xl flex flex-col`}
      >
        {title && (
          <div className="flex items-center justify-between p-4 border-b border-slate-800/60 flex-shrink-0">
            <h3 className="text-lg font-semibold text-slate-100">
              {title}
            </h3>
            <button
              onClick={onClose}
              className="p-1 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
        <div className="p-4 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `client/`:
```bash
npm test -- src/__tests__/components/ui/Modal.test.tsx
```
Expected: All 4 tests PASS.

- [ ] **Step 5: Run typecheck to verify no other consumers broke**

Run from `client/`:
```bash
npx tsc --noEmit
```
Expected: PASS. The new props are optional so existing callers compile unchanged.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/ui/Modal.tsx client/src/__tests__/components/ui/Modal.test.tsx
git commit -m "feat(ui): add closeOnOverlayClick and closeOnEscape props to Modal"
```

---

## Task 2: `twoFactorStatusStore` — lazy cached 2FA status

**Files:**
- Create: `client/src/components/quickSettings/twoFactorStatusStore.ts`
- Create: `client/src/__tests__/components/quickSettings/twoFactorStatusStore.test.ts`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/quickSettings/twoFactorStatusStore.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as twoFactorApi from '../../../api/two-factor';
import { loadStatusOnce, refreshStatus } from '../../../components/quickSettings/twoFactorStatusStore';

describe('twoFactorStatusStore', () => {
  beforeEach(() => {
    refreshStatus();
    vi.restoreAllMocks();
  });

  it('first call hits the API once', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    await loadStatusOnce();
    expect(spy).toHaveBeenCalledOnce();
  });

  it('second call returns cached value without hitting the API again', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: true,
      enabled_at: '2026-01-01T00:00:00Z',
      backup_codes_remaining: 5,
    });
    await loadStatusOnce();
    await loadStatusOnce();
    expect(spy).toHaveBeenCalledOnce();
  });

  it('refreshStatus invalidates so next call hits the API again', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    await loadStatusOnce();
    refreshStatus();
    await loadStatusOnce();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('failed request resolves to null and does not throw', async () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockRejectedValue(new Error('network'));
    const result = await loadStatusOnce();
    expect(result).toBeNull();
  });

  it('concurrent calls share a single in-flight request', async () => {
    const spy = vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    await Promise.all([loadStatusOnce(), loadStatusOnce(), loadStatusOnce()]);
    expect(spy).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- src/__tests__/components/quickSettings/twoFactorStatusStore.test.ts
```
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the store**

Create `client/src/components/quickSettings/twoFactorStatusStore.ts`:

```ts
/**
 * Lazy module-level cache for the user's 2FA status.
 *
 * Same pattern as lib/byteUnits.ts — module state, no React Context.
 * Loaded on first access, kept for the duration of the page load,
 * invalidated explicitly via refreshStatus() after a successful setup.
 */
import { useEffect, useState } from 'react';
import { get2FAStatus, type TwoFactorStatus } from '../../api/two-factor';

let cached: TwoFactorStatus | null = null;
let inflight: Promise<TwoFactorStatus | null> | null = null;

export async function loadStatusOnce(): Promise<TwoFactorStatus | null> {
  if (cached) return cached;
  if (inflight) return inflight;
  inflight = get2FAStatus()
    .then((s) => {
      cached = s;
      return s as TwoFactorStatus | null;
    })
    .catch(() => null)
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function refreshStatus(): void {
  cached = null;
  inflight = null;
}

/**
 * React hook that triggers `loadStatusOnce()` when `enabled` is true.
 * Returns the cached status, or null while loading or on error.
 */
export function useTwoFactorStatus(enabled: boolean): TwoFactorStatus | null {
  const [status, setStatus] = useState<TwoFactorStatus | null>(cached);

  useEffect(() => {
    if (!enabled) return;
    if (cached) {
      setStatus(cached);
      return;
    }
    let cancelled = false;
    void loadStatusOnce().then((s) => {
      if (!cancelled) setStatus(s);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return status;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- src/__tests__/components/quickSettings/twoFactorStatusStore.test.ts
```
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/quickSettings/twoFactorStatusStore.ts client/src/__tests__/components/quickSettings/twoFactorStatusStore.test.ts
git commit -m "feat(quick-settings): lazy 2FA status store with React hook"
```

---

## Task 3: `TwoFactorSetupFlow` — extracted three-step setup component

**Why:** The setup logic is currently woven into `TwoFactorCard.tsx` across three render branches. Extracting it into a chrome-less component lets both the Settings card and the new Modal reuse the exact same flow.

**Files:**
- Create: `client/src/components/quickSettings/TwoFactorSetupFlow.tsx`
- Create: `client/src/__tests__/components/quickSettings/TwoFactorSetupFlow.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/quickSettings/TwoFactorSetupFlow.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as twoFactorApi from '../../../api/two-factor';
import { TwoFactorSetupFlow } from '../../../components/quickSettings/TwoFactorSetupFlow';

const mockSetupData = {
  qr_code: 'data:image/png;base64,FAKE',
  provisioning_uri: 'otpauth://totp/test',
  secret: 'JBSWY3DPEHPK3PXP',
};

const mockBackupCodes = {
  backup_codes: ['CODE-0001', 'CODE-0002', 'CODE-0003'],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('TwoFactorSetupFlow', () => {
  it('calls setup2FA on mount and renders QR + secret', async () => {
    const setup = vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => expect(setup).toHaveBeenCalledOnce());
    expect(screen.getByAltText(/qr/i)).toHaveAttribute('src', mockSetupData.qr_code);
    expect(screen.getByText(mockSetupData.secret)).toBeInTheDocument();
  });

  it('cancel button calls onCancel', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    const onCancel = vi.fn();

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={onCancel} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));
    const buttons = screen.getAllByRole('button');
    // Cancel is the first plain button in the verify form
    const cancelBtn = buttons.find((b) => b.getAttribute('type') === 'button');
    fireEvent.click(cancelBtn!);
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('successful verify transitions to backup-codes step', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    const verify = vi.spyOn(twoFactorApi, 'verifySetup2FA').mockResolvedValue(mockBackupCodes);

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));

    const codeInput = screen.getByPlaceholderText('000000') as HTMLInputElement;
    fireEvent.change(codeInput, { target: { value: '123456' } });

    const submitBtn = screen.getAllByRole('button').find((b) => b.getAttribute('type') === 'submit');
    fireEvent.click(submitBtn!);

    await waitFor(() => expect(verify).toHaveBeenCalledWith(mockSetupData.secret, '123456'));
    await waitFor(() => {
      mockBackupCodes.backup_codes.forEach((c) => expect(screen.getByText(c)).toBeInTheDocument());
    });
  });

  it('done button on backup-codes step calls onComplete', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    vi.spyOn(twoFactorApi, 'verifySetup2FA').mockResolvedValue(mockBackupCodes);
    const onComplete = vi.fn();

    render(<TwoFactorSetupFlow onComplete={onComplete} onCancel={vi.fn()} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));
    fireEvent.change(screen.getByPlaceholderText('000000'), { target: { value: '123456' } });
    fireEvent.click(screen.getAllByRole('button').find((b) => b.getAttribute('type') === 'submit')!);

    await waitFor(() => screen.getByText(mockBackupCodes.backup_codes[0]));
    const doneBtn = screen.getAllByRole('button').find((b) => /done|fertig/i.test(b.textContent ?? ''));
    fireEvent.click(doneBtn!);

    expect(onComplete).toHaveBeenCalledOnce();
  });

  it('reports the current step via onStepChange', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    vi.spyOn(twoFactorApi, 'verifySetup2FA').mockResolvedValue(mockBackupCodes);
    const onStepChange = vi.fn();

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={vi.fn()} onStepChange={onStepChange} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));
    expect(onStepChange).toHaveBeenLastCalledWith('verify');

    fireEvent.change(screen.getByPlaceholderText('000000'), { target: { value: '123456' } });
    fireEvent.click(screen.getAllByRole('button').find((b) => b.getAttribute('type') === 'submit')!);

    await waitFor(() => expect(onStepChange).toHaveBeenLastCalledWith('backup-codes'));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- src/__tests__/components/quickSettings/TwoFactorSetupFlow.test.tsx
```
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the setup flow**

Create `client/src/components/quickSettings/TwoFactorSetupFlow.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Copy, KeyRound } from 'lucide-react';
import {
  setup2FA,
  verifySetup2FA,
  type TwoFactorSetupData,
} from '../../api/two-factor';

export type TwoFactorSetupStep = 'loading' | 'verify' | 'backup-codes';

export interface TwoFactorSetupFlowProps {
  onComplete: () => void;
  onCancel: () => void;
  /** Optional callback whenever the internal step changes. Used by the
   * parent (e.g., a Modal) to suppress accidental dismissal during the
   * backup-codes step. */
  onStepChange?: (step: TwoFactorSetupStep) => void;
}

export function TwoFactorSetupFlow({
  onComplete,
  onCancel,
  onStepChange,
}: TwoFactorSetupFlowProps) {
  const { t } = useTranslation('settings');
  const [step, setStep] = useState<TwoFactorSetupStep>('loading');
  const [setupData, setSetupData] = useState<TwoFactorSetupData | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Trigger setup once on mount
  useEffect(() => {
    let cancelled = false;
    setSaving(true);
    setup2FA()
      .then((data) => {
        if (cancelled) return;
        setSetupData(data);
        setStep('verify');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail =
          err instanceof Object && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : undefined;
        setError(detail || 'Failed to start 2FA setup');
      })
      .finally(() => {
        if (!cancelled) setSaving(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Notify parent of step transitions
  useEffect(() => {
    onStepChange?.(step);
  }, [step, onStepChange]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setupData) return;
    setError('');
    setSaving(true);
    try {
      const result = await verifySetup2FA(setupData.secret, verifyCode);
      setBackupCodes(result.backup_codes);
      setVerifyCode('');
      setStep('backup-codes');
    } catch (err: unknown) {
      const detail =
        err instanceof Object && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || 'Invalid verification code');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyBackupCodes = () => {
    void navigator.clipboard.writeText(backupCodes.join('\n'));
    toast.success(t('security.backupCodesCopied'));
  };

  // Loading / initial setup call in flight
  if (step === 'loading' || !setupData) {
    return (
      <div className="text-sm text-slate-300 py-4">
        {error ? (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-rose-200">
            {error}
          </div>
        ) : (
          t('profile.loading')
        )}
      </div>
    );
  }

  if (step === 'backup-codes') {
    return (
      <div>
        <div className="flex items-center gap-2 mb-3">
          <KeyRound className="w-5 h-5 text-amber-400" />
          <h4 className="text-base font-semibold text-slate-100">
            {t('security.backupCodesTitle')}
          </h4>
        </div>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 mb-4">
          {t('security.backupCodesWarning')}
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {backupCodes.map((code) => (
            <div
              key={code}
              className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm text-center"
            >
              {code}
            </div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            onClick={handleCopyBackupCodes}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            <Copy className="w-4 h-4" />
            {t('security.copyBackupCodes')}
          </button>
          <button
            type="button"
            onClick={onComplete}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors"
          >
            {t('security.backupCodesDone')}
          </button>
        </div>
      </div>
    );
  }

  // step === 'verify'
  return (
    <div>
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {error}
        </div>
      )}

      <p className="text-sm text-slate-300 mb-4">{t('security.setupStep1')}</p>

      <div className="flex justify-center mb-4">
        <img
          src={setupData.qr_code}
          alt="TOTP QR Code"
          className="w-48 h-48 sm:w-56 sm:h-56 rounded-lg bg-white p-2"
        />
      </div>

      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-400 mb-1">
          {t('security.manualEntry')}
        </label>
        <div className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm break-all select-all">
          {setupData.secret}
        </div>
      </div>

      <p className="text-sm text-slate-300 mb-3">{t('security.setupStep2')}</p>

      <form onSubmit={handleVerify} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">
            {t('security.verificationCode')}
          </label>
          <input
            type="text"
            value={verifyCode}
            onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            className="input text-center text-xl tracking-[0.4em] font-mono"
            placeholder="000000"
            autoComplete="one-time-code"
            inputMode="numeric"
            required
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            {t('security.cancel')}
          </button>
          <button
            type="submit"
            disabled={saving || verifyCode.length < 6}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
          >
            {saving ? t('security.verifying') : t('security.verify')}
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- src/__tests__/components/quickSettings/TwoFactorSetupFlow.test.tsx
```
Expected: All 5 tests PASS. (i18n returns the key as text in test env, so `setupStep1` etc. render as their key strings — that's fine, the tests don't depend on translated labels.)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/quickSettings/TwoFactorSetupFlow.tsx client/src/__tests__/components/quickSettings/TwoFactorSetupFlow.test.tsx
git commit -m "feat(quick-settings): extract TwoFactorSetupFlow from settings card"
```

---

## Task 4: Refactor `TwoFactorCard` to use `TwoFactorSetupFlow`

**Why now:** Verify the extraction did not regress the existing Settings page before adding new consumers.

**Files:**
- Modify: `client/src/components/settings/TwoFactorCard.tsx`

- [ ] **Step 1: Read current implementation**

Open `client/src/components/settings/TwoFactorCard.tsx` for reference. The existing setup-flow render branches are at lines 132-236 (backup codes + setup data branches). Disable form (lines 238-300) and default status view (lines 302-371) stay.

- [ ] **Step 2: Replace the setup-flow branches**

Apply this diff to `client/src/components/settings/TwoFactorCard.tsx`:

1. Remove `setupData`, `verifyCode`, `backupCodes` state variables and the `handleStartSetup`, `handleVerifySetup`, `handleBackupCodesDone`, `handleCopyBackupCodes` handlers (replaced by the extracted component). Keep `setShowDisable`, disable handlers, and the regenerate handler.

2. Add a single boolean `showSetup` state and a step-tracking state.

3. Replace the inline setup branches with a render of `<TwoFactorSetupFlow />` when `showSetup === true`.

The full new file content:

```tsx
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Shield, ShieldCheck, ShieldOff, RefreshCw, KeyRound, Copy } from 'lucide-react';
import {
  get2FAStatus,
  disable2FA,
  regenerateBackupCodes,
  type TwoFactorStatus,
} from '../../api/two-factor';
import { TwoFactorSetupFlow } from '../quickSettings/TwoFactorSetupFlow';
import { refreshStatus as refreshTwoFactorCache } from '../quickSettings/twoFactorStatusStore';

export default function TwoFactorCard() {
  const { t } = useTranslation('settings');
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [regeneratedCodes, setRegeneratedCodes] = useState<string[] | null>(null);
  const [showDisable, setShowDisable] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const data = await get2FAStatus();
      setStatus(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleSetupComplete = () => {
    setShowSetup(false);
    refreshTwoFactorCache();
    void loadStatus();
  };

  const handleDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await disable2FA(disablePassword, disableCode);
      setShowDisable(false);
      setDisablePassword('');
      setDisableCode('');
      refreshTwoFactorCache();
      void loadStatus();
    } catch (err: unknown) {
      const detail =
        err instanceof Object && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || 'Failed to disable 2FA');
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerateBackupCodes = async () => {
    if (!confirm(t('security.regenerateWarning'))) return;
    setError('');
    setSaving(true);
    try {
      const result = await regenerateBackupCodes();
      setRegeneratedCodes(result.backup_codes);
    } catch (err: unknown) {
      const detail =
        err instanceof Object && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || 'Failed to regenerate backup codes');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyRegenerated = () => {
    if (regeneratedCodes) {
      void navigator.clipboard.writeText(regeneratedCodes.join('\n'));
      toast.success(t('security.backupCodesCopied'));
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>
        <p className="text-slate-400 text-sm">{t('profile.loading')}</p>
      </div>
    );
  }

  if (regeneratedCodes) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <KeyRound className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-amber-400" />
          {t('security.backupCodesTitle')}
        </h3>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 mb-4">
          {t('security.backupCodesWarning')}
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {regeneratedCodes.map((code) => (
            <div
              key={code}
              className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm text-center"
            >
              {code}
            </div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            onClick={handleCopyRegenerated}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            <Copy className="w-4 h-4" />
            {t('security.copyBackupCodes')}
          </button>
          <button
            type="button"
            onClick={() => setRegeneratedCodes(null)}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors"
          >
            {t('security.backupCodesDone')}
          </button>
        </div>
      </div>
    );
  }

  if (showSetup) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>
        <TwoFactorSetupFlow
          onComplete={handleSetupComplete}
          onCancel={() => setShowSetup(false)}
        />
      </div>
    );
  }

  if (showDisable) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <ShieldOff className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-rose-400" />
          {t('security.disable2FA')}
        </h3>
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {t('security.disableWarning')}
        </div>
        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}
        <form onSubmit={handleDisable} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.disablePassword')}</label>
            <input
              type="password"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
              className="input"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.disableCode')}</label>
            <input
              type="text"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="input text-center font-mono tracking-wider"
              placeholder="000000"
              autoComplete="one-time-code"
              inputMode="numeric"
              required
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { setShowDisable(false); setError(''); setDisablePassword(''); setDisableCode(''); }}
              className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
            >
              {t('security.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-rose-500 hover:bg-rose-600 transition-colors disabled:opacity-50"
            >
              {saving ? t('security.changing') : t('security.disable2FA')}
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
        <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
        {t('security.twoFactor')}
      </h3>
      <p className="text-sm text-slate-300 mb-4">{t('security.twoFactorDescription')}</p>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {error}
        </div>
      )}

      {status?.enabled ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
            <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-emerald-300">{t('security.twoFactorEnabled')}</p>
              {status.enabled_at && (
                <p className="text-xs text-emerald-400/70">
                  {t('security.twoFactorEnabledSince')} {new Date(status.enabled_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm text-slate-300">
            <KeyRound className="w-4 h-4" />
            <span>{t('security.backupCodesRemaining', { count: status.backup_codes_remaining })}</span>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={handleRegenerateBackupCodes}
              disabled={saving}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors disabled:opacity-50"
            >
              <RefreshCw className="w-4 h-4" />
              {t('security.regenerateBackupCodes')}
            </button>
            <button
              onClick={() => { setShowDisable(true); setError(''); }}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-rose-300 rounded-lg bg-rose-500/10 border border-rose-500/30 hover:bg-rose-500/20 transition-colors"
            >
              <ShieldOff className="w-4 h-4" />
              {t('security.disable2FA')}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
            <ShieldOff className="w-5 h-5 text-slate-400 flex-shrink-0" />
            <p className="text-sm text-slate-400">{t('security.twoFactorDisabled')}</p>
          </div>
          <button
            onClick={() => { setShowSetup(true); setError(''); }}
            disabled={saving}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
          >
            <ShieldCheck className="w-4 h-4" />
            {t('security.enable2FA')}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run typecheck**

```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 4: Manually verify the Settings page still works**

Run `python start_dev.py`, navigate to Settings → Security, click "Enable 2FA", confirm: QR appears, manual secret visible, Cancel returns to status view, after entering a valid TOTP code (use `pyotp` or an authenticator) the backup-codes screen appears, "Done" returns to status with `enabled=true`. Then disable 2FA — same flow as before.

If you cannot run a TOTP authenticator, at minimum verify: status loads, "Enable 2FA" click triggers the QR-code render (mock-mode or real), Cancel returns to the status view.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/settings/TwoFactorCard.tsx
git commit -m "refactor(settings): use TwoFactorSetupFlow in TwoFactorCard"
```

---

## Task 5: `LanguageSection` — compact horizontal language picker

**Files:**
- Create: `client/src/components/quickSettings/LanguageSection.tsx`
- Create: `client/src/__tests__/components/quickSettings/LanguageSection.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/quickSettings/LanguageSection.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguageSection } from '../../../components/quickSettings/LanguageSection';

let currentLanguage = 'de';
const changeLanguage = vi.fn((code: string) => {
  currentLanguage = code;
  return Promise.resolve();
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      get language() { return currentLanguage; },
      changeLanguage,
    },
  }),
}));

describe('LanguageSection', () => {
  beforeEach(() => {
    currentLanguage = 'de';
    changeLanguage.mockClear();
  });

  it('renders both available languages', () => {
    render(<LanguageSection />);
    expect(screen.getByText('Deutsch')).toBeInTheDocument();
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('calls i18n.changeLanguage with the clicked language code', () => {
    render(<LanguageSection />);
    fireEvent.click(screen.getByText('English').closest('button')!);
    expect(changeLanguage).toHaveBeenCalledWith('en');
  });

  it('marks the active language with aria-pressed=true', () => {
    render(<LanguageSection />);
    const deBtn = screen.getByText('Deutsch').closest('button')!;
    const enBtn = screen.getByText('English').closest('button')!;
    expect(deBtn).toHaveAttribute('aria-pressed', 'true');
    expect(enBtn).toHaveAttribute('aria-pressed', 'false');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- src/__tests__/components/quickSettings/LanguageSection.test.tsx
```
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the section**

Create `client/src/components/quickSettings/LanguageSection.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { availableLanguages } from '../../i18n';

export function LanguageSection() {
  const { t, i18n } = useTranslation('common');

  const isActive = (code: string) =>
    i18n.language === code || i18n.language.startsWith(code + '-');

  return (
    <section className="px-3 py-2">
      <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
        <Globe className="w-3.5 h-3.5" />
        {t('userMenu.quickSettings.language.title')}
      </div>
      <div className="flex gap-2">
        {availableLanguages.map((lang) => {
          const active = isActive(lang.code);
          return (
            <button
              key={lang.code}
              type="button"
              aria-pressed={active}
              onClick={() => void i18n.changeLanguage(lang.code)}
              className={`flex-1 flex items-center justify-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition ${
                active
                  ? 'border-sky-500/60 bg-sky-500/15 text-white'
                  : 'border-slate-700/60 bg-slate-800/40 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              <span className="text-base leading-none">{lang.flag}</span>
              <span>{lang.name}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- src/__tests__/components/quickSettings/LanguageSection.test.tsx
```
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/quickSettings/LanguageSection.tsx client/src/__tests__/components/quickSettings/LanguageSection.test.tsx
git commit -m "feat(quick-settings): add LanguageSection"
```

---

## Task 6: `ByteUnitSection` — compact horizontal byte-unit picker

**Files:**
- Create: `client/src/components/quickSettings/ByteUnitSection.tsx`
- Create: `client/src/__tests__/components/quickSettings/ByteUnitSection.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/quickSettings/ByteUnitSection.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { setByteUnitMode } from '../../../lib/byteUnits';
import { ByteUnitSection } from '../../../components/quickSettings/ByteUnitSection';

beforeEach(() => {
  act(() => {
    setByteUnitMode('binary');
  });
});

describe('ByteUnitSection', () => {
  it('renders both modes', () => {
    render(<ByteUnitSection />);
    expect(screen.getByText('GiB')).toBeInTheDocument();
    expect(screen.getByText('GB')).toBeInTheDocument();
  });

  it('marks binary as active by default', () => {
    render(<ByteUnitSection />);
    const binaryBtn = screen.getByText('GiB').closest('button')!;
    const decimalBtn = screen.getByText('GB').closest('button')!;
    expect(binaryBtn).toHaveAttribute('aria-pressed', 'true');
    expect(decimalBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('switches to decimal on click and updates the active state', () => {
    render(<ByteUnitSection />);
    fireEvent.click(screen.getByText('GB').closest('button')!);
    const binaryBtn = screen.getByText('GiB').closest('button')!;
    const decimalBtn = screen.getByText('GB').closest('button')!;
    expect(binaryBtn).toHaveAttribute('aria-pressed', 'false');
    expect(decimalBtn).toHaveAttribute('aria-pressed', 'true');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- src/__tests__/components/quickSettings/ByteUnitSection.test.tsx
```
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the section**

Create `client/src/components/quickSettings/ByteUnitSection.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import { Binary } from 'lucide-react';
import { useByteUnitMode } from '../../hooks/useByteUnitMode';
import type { ByteUnitMode } from '../../lib/byteUnits';

const MODES: { mode: ByteUnitMode; shortKey: string; hintKey: string }[] = [
  { mode: 'binary',  shortKey: 'userMenu.quickSettings.byteUnits.binaryShort',  hintKey: 'userMenu.quickSettings.byteUnits.binaryHint'  },
  { mode: 'decimal', shortKey: 'userMenu.quickSettings.byteUnits.decimalShort', hintKey: 'userMenu.quickSettings.byteUnits.decimalHint' },
];

export function ByteUnitSection() {
  const { t } = useTranslation('common');
  const [mode, setMode] = useByteUnitMode();

  return (
    <section className="px-3 py-2">
      <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
        <Binary className="w-3.5 h-3.5" />
        {t('userMenu.quickSettings.byteUnits.title')}
      </div>
      <div className="flex gap-2">
        {MODES.map((opt) => {
          const active = mode === opt.mode;
          return (
            <button
              key={opt.mode}
              type="button"
              aria-pressed={active}
              onClick={() => setMode(opt.mode)}
              className={`flex-1 flex flex-col items-center rounded-lg border px-3 py-1.5 text-sm transition ${
                active
                  ? 'border-sky-500/60 bg-sky-500/15 text-white'
                  : 'border-slate-700/60 bg-slate-800/40 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              <span className="font-medium">{t(opt.shortKey)}</span>
              <span className="text-[10px] text-slate-400 leading-tight">{t(opt.hintKey)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- src/__tests__/components/quickSettings/ByteUnitSection.test.tsx
```
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/quickSettings/ByteUnitSection.tsx client/src/__tests__/components/quickSettings/ByteUnitSection.test.tsx
git commit -m "feat(quick-settings): add ByteUnitSection"
```

---

## Task 7: `TwoFactorPromptSection` — conditional 2FA setup nudge

**Files:**
- Create: `client/src/components/quickSettings/TwoFactorPromptSection.tsx`
- Create: `client/src/__tests__/components/quickSettings/TwoFactorPromptSection.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/quickSettings/TwoFactorPromptSection.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import * as twoFactorApi from '../../../api/two-factor';
import { TwoFactorPromptSection } from '../../../components/quickSettings/TwoFactorPromptSection';
import { refreshStatus } from '../../../components/quickSettings/twoFactorStatusStore';

beforeEach(() => {
  refreshStatus();
  vi.restoreAllMocks();
});

describe('TwoFactorPromptSection', () => {
  it('renders nothing while status is loading', () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})  // never resolves
    );
    const { container } = render(<TwoFactorPromptSection onOpenSetup={vi.fn()} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when status returns enabled=true', async () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: true,
      enabled_at: '2026-01-01T00:00:00Z',
      backup_codes_remaining: 5,
    });
    const { container } = render(<TwoFactorPromptSection onOpenSetup={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.innerHTML).toBe('');
  });

  it('renders the prompt when status returns enabled=false', async () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    render(<TwoFactorPromptSection onOpenSetup={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /set up|einrichten/i })).toBeInTheDocument();
    });
  });

  it('renders nothing when the status request fails', async () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockRejectedValue(new Error('network'));
    const { container } = render(<TwoFactorPromptSection onOpenSetup={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.innerHTML).toBe('');
  });

  it('clicking the button calls onOpenSetup', async () => {
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    const onOpenSetup = vi.fn();
    render(<TwoFactorPromptSection onOpenSetup={onOpenSetup} />);
    const button = await screen.findByRole('button', { name: /set up|einrichten/i });
    fireEvent.click(button);
    expect(onOpenSetup).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- src/__tests__/components/quickSettings/TwoFactorPromptSection.test.tsx
```
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the section**

Create `client/src/components/quickSettings/TwoFactorPromptSection.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import { ShieldAlert } from 'lucide-react';
import { useTwoFactorStatus } from './twoFactorStatusStore';

export interface TwoFactorPromptSectionProps {
  onOpenSetup: () => void;
}

export function TwoFactorPromptSection({ onOpenSetup }: TwoFactorPromptSectionProps) {
  const { t } = useTranslation('common');
  const status = useTwoFactorStatus(true);

  // Loading or enabled or error → render nothing
  if (status === null || status.enabled) return null;

  return (
    <>
      <div className="border-t border-slate-800/70 my-1" />
      <section className="px-3 py-2">
        <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-amber-300">
          <ShieldAlert className="w-3.5 h-3.5" />
          {t('userMenu.quickSettings.twoFactor.notEnabled')}
        </div>
        <button
          type="button"
          onClick={onOpenSetup}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-sm font-medium text-amber-200 hover:bg-amber-500/20 transition"
        >
          {t('userMenu.quickSettings.twoFactor.enableNow')}
        </button>
      </section>
    </>
  );
}
```

- [ ] **Step 4: Add the new i18n keys (en + de)**

Open `client/src/i18n/locales/en/common.json`. Find the top-level closing `}` and insert (preserving any trailing comma rules):

```json
"userMenu": {
  "quickSettings": {
    "language": {
      "title": "Language"
    },
    "byteUnits": {
      "title": "Units",
      "binaryShort": "GiB",
      "decimalShort": "GB",
      "binaryHint": "binary",
      "decimalHint": "decimal"
    },
    "twoFactor": {
      "notEnabled": "2FA not enabled yet",
      "enableNow": "Set up now",
      "modalTitle": "Set up Two-Factor Authentication"
    }
  }
}
```

Open `client/src/i18n/locales/de/common.json` and insert the German equivalent at the same position:

```json
"userMenu": {
  "quickSettings": {
    "language": {
      "title": "Sprache"
    },
    "byteUnits": {
      "title": "Einheiten",
      "binaryShort": "GiB",
      "decimalShort": "GB",
      "binaryHint": "binär",
      "decimalHint": "dezimal"
    },
    "twoFactor": {
      "notEnabled": "2FA noch nicht aktiv",
      "enableNow": "Jetzt einrichten",
      "modalTitle": "Zwei-Faktor-Authentifizierung einrichten"
    }
  }
}
```

If the file already has a top-level `userMenu` key, merge into it instead of duplicating. Verify by `python -m json.tool client/src/i18n/locales/en/common.json > /dev/null` (and same for `de`).

- [ ] **Step 5: Run tests to verify they pass**

```bash
npm test -- src/__tests__/components/quickSettings/TwoFactorPromptSection.test.tsx
```
Expected: All 5 tests PASS. The button-name regex `/set up|einrichten/i` matches the i18n raw key `userMenu.quickSettings.twoFactor.enableNow` returned in the test environment, since the regex matches the substring "set up" inside the key string (`Set up now`) — but the test's label match is against the rendered text. In the Vitest environment without resources, `t()` returns the key. Adjust the regex if needed to match the literal key string `userMenu.quickSettings.twoFactor.enableNow` — the easier and more robust approach is to use a `data-testid="two-factor-prompt-button"` attribute on the button and target by it. Update both the component and test if you go that route.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/quickSettings/TwoFactorPromptSection.tsx client/src/__tests__/components/quickSettings/TwoFactorPromptSection.test.tsx client/src/i18n/locales/de/common.json client/src/i18n/locales/en/common.json
git commit -m "feat(quick-settings): add TwoFactorPromptSection + i18n keys"
```

---

## Task 8: `UserMenuQuickSettings` container

**Files:**
- Create: `client/src/components/UserMenuQuickSettings.tsx`
- Create: `client/src/__tests__/components/UserMenuQuickSettings.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `client/src/__tests__/components/UserMenuQuickSettings.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import * as twoFactorApi from '../../api/two-factor';
import UserMenuQuickSettings from '../../components/UserMenuQuickSettings';
import { refreshStatus } from '../../components/quickSettings/twoFactorStatusStore';

describe('UserMenuQuickSettings', () => {
  it('renders the language section', () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})
    );
    render(<UserMenuQuickSettings />);
    expect(screen.getByText('Deutsch')).toBeInTheDocument();
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('renders the byte-unit section', () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})
    );
    render(<UserMenuQuickSettings />);
    expect(screen.getByText('GiB')).toBeInTheDocument();
    expect(screen.getByText('GB')).toBeInTheDocument();
  });

  it('does not render 2FA prompt section while status is loading', () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})
    );
    render(<UserMenuQuickSettings />);
    expect(
      screen.queryByText(/2fa|two[- ]factor/i)
    ).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- src/__tests__/components/UserMenuQuickSettings.test.tsx
```
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the container with Modal**

Create `client/src/components/UserMenuQuickSettings.tsx`:

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from './ui/Modal';
import { LanguageSection } from './quickSettings/LanguageSection';
import { ByteUnitSection } from './quickSettings/ByteUnitSection';
import { TwoFactorPromptSection } from './quickSettings/TwoFactorPromptSection';
import { TwoFactorSetupFlow, type TwoFactorSetupStep } from './quickSettings/TwoFactorSetupFlow';
import { refreshStatus } from './quickSettings/twoFactorStatusStore';

export default function UserMenuQuickSettings() {
  const { t } = useTranslation('common');
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupStep, setSetupStep] = useState<TwoFactorSetupStep>('loading');

  const handleSetupComplete = () => {
    refreshStatus();
    setSetupOpen(false);
  };

  // Backup-codes step must not be dismissable by accident
  const lockClose = setupStep === 'backup-codes';

  return (
    <div className="flex flex-col">
      <LanguageSection />
      <div className="border-t border-slate-800/70 my-1" />
      <ByteUnitSection />
      <TwoFactorPromptSection onOpenSetup={() => setSetupOpen(true)} />

      <Modal
        isOpen={setupOpen}
        onClose={() => setSetupOpen(false)}
        title={t('userMenu.quickSettings.twoFactor.modalTitle')}
        size="lg"
        closeOnOverlayClick={!lockClose}
        closeOnEscape={!lockClose}
      >
        <TwoFactorSetupFlow
          onComplete={handleSetupComplete}
          onCancel={() => setSetupOpen(false)}
          onStepChange={setSetupStep}
        />
      </Modal>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- src/__tests__/components/UserMenuQuickSettings.test.tsx
```
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/UserMenuQuickSettings.tsx client/src/__tests__/components/UserMenuQuickSettings.test.tsx
git commit -m "feat(quick-settings): UserMenuQuickSettings container with Modal"
```

---

## Task 9: Wire `UserMenuQuickSettings` into `UserMenu`

**Files:**
- Modify: `client/src/components/UserMenu.tsx`

- [ ] **Step 1: Apply the wiring change**

Open `client/src/components/UserMenu.tsx`. Make these three changes:

1. Add the import at the top of the file (after the existing `apiClient` import):

```tsx
import UserMenuQuickSettings from './UserMenuQuickSettings';
```

2. Widen the dropdown panel from `w-64` to `w-72`. Find the line:

```tsx
<div className="absolute right-0 mt-2 w-64 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
```

Replace with:

```tsx
<div className="absolute right-0 mt-2 w-72 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
```

3. Replace the conditional dev-block + production fallback (the whole `{canSwitchUser ? (...) : (...)}` ternary, lines ~85-152) with:

```tsx
{canSwitchUser && (
  <>
    {/* Existing impersonation submenu — keep verbatim */}
    <div
      className="relative"
      onMouseEnter={() => {
        setSubmenuOpen(true);
        void loadUsers();
      }}
      onMouseLeave={() => setSubmenuOpen(false)}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/70"
      >
        <span className="flex items-center gap-2">
          <UserPlus className="h-4 w-4" />
          {t('impersonation.switchToUser')}
        </span>
        <ChevronRight className="h-4 w-4 text-slate-400" />
      </button>

      {submenuOpen && (
        <div className="absolute right-full top-0 mr-1 w-64 max-h-80 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
          {loadingUsers && (
            <div className="px-3 py-2 text-sm text-slate-400">
              {t('impersonation.loading')}
            </div>
          )}
          {!loadingUsers && users !== null && users.length === 0 && (
            <div className="px-3 py-2 text-sm text-slate-400">
              {t('impersonation.empty')}
            </div>
          )}
          {!loadingUsers &&
            users !== null &&
            users
              .filter((u) => u.id !== user.id)
              .map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onClick={() => void onSwitchToUser(u.id)}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/70"
                >
                  <span className="flex items-center gap-2">
                    {u.role === 'admin' ? (
                      <Shield className="h-4 w-4 text-amber-400" />
                    ) : (
                      <UserIcon className="h-4 w-4 text-slate-400" />
                    )}
                    {u.username}
                  </span>
                  <span
                    className={
                      u.role === 'admin'
                        ? 'rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300'
                        : 'rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300'
                    }
                  >
                    {u.role}
                  </span>
                </button>
              ))}
        </div>
      )}
    </div>
    <div className="border-t border-slate-800/70 my-1" />
  </>
)}
<UserMenuQuickSettings />
```

- [ ] **Step 2: Run typecheck**

```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 3: Run all unit tests**

```bash
npm test
```
Expected: PASS for all new and existing tests.

- [ ] **Step 4: Manual smoke test (dev mode)**

```bash
python start_dev.py
```

Open http://localhost:5173, log in as admin (DevMode2024). Verify:

- Click the username pill → dropdown opens.
- "Switch to user →" submenu still hovers on the right (dev-only).
- Below it: a divider, then the Language section (DE active), then the Byte-Units section (GiB active).
- 2FA prompt: depending on whether the seeded admin has 2FA. If not, the amber "2FA noch nicht aktiv" block is visible at the bottom of the dropdown.
- Click EN → sidebar labels switch to English.
- Click GB → reopen Dashboard, storage cards now show "GB" suffix.
- Log out, log in as the regular user (`user` / `User123`); verify only the Quick-Settings sections render (no impersonation submenu).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/UserMenu.tsx
git commit -m "feat(user-menu): wire Quick-Settings into the dropdown"
```

---

## Task 10: Playwright E2E test

**Files:**
- Create: `client/tests/e2e/userMenuQuickSettings.spec.ts`

- [ ] **Step 1: Inspect existing E2E patterns**

Open `client/tests/e2e/fixtures/auth.fixture.ts` and a couple of existing specs (e.g. anything in `client/tests/e2e/`) to confirm the login fixture name, the locator strategy (CSS / role / data-testid) used elsewhere, and how API mocking is wired (`context.route(...)`). Match those conventions exactly — do not invent a new pattern.

- [ ] **Step 2: Write the spec**

Create `client/tests/e2e/userMenuQuickSettings.spec.ts`:

```ts
import { test, expect } from './fixtures/auth.fixture';

// Adjust the import above and the helper names below if your repo's
// existing fixtures use different names (e.g. authenticatedPage).

test.describe('User Menu Quick-Settings', () => {
  test('language switch round-trip', async ({ page }) => {
    await page.goto('/');
    // Open the user menu (button shows the username text "admin")
    await page.getByRole('button', { name: /admin/i }).first().click();

    // Click English
    await page.getByRole('button', { name: /English/ }).click();

    // Sidebar (or any UI text) should now be in English. Pick a stable
    // English string from the sidebar that does not appear in German.
    // Example: "Dashboard" exists in both, "Settings" too — but
    // "File Manager" vs "Dateimanager" differs.
    await expect(page.getByRole('link', { name: /File Manager/ })).toBeVisible();

    // Switch back to Deutsch
    await page.getByRole('button', { name: /admin/i }).first().click();
    await page.getByRole('button', { name: /Deutsch/ }).click();
    await expect(page.getByRole('link', { name: /Dateimanager/ })).toBeVisible();
  });

  test('byte-unit switch round-trip', async ({ page }) => {
    await page.goto('/');
    // Storage card on Dashboard shows GiB by default
    await expect(page.getByText(/GiB/).first()).toBeVisible();

    await page.getByRole('button', { name: /admin/i }).first().click();
    await page.getByRole('button', { name: /^GB$/ }).click();

    await expect(page.getByText(/\bGB\b/).first()).toBeVisible();

    // Switch back
    await page.getByRole('button', { name: /admin/i }).first().click();
    await page.getByRole('button', { name: /^GiB$/ }).click();
    await expect(page.getByText(/GiB/).first()).toBeVisible();
  });

  test('2FA prompt visible when not enabled, hidden when enabled', async ({ page, context }) => {
    // Mock status: not enabled
    await context.route('**/api/auth/2fa/status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: false,
          enabled_at: null,
          backup_codes_remaining: 0,
        }),
      })
    );

    await page.goto('/');
    await page.getByRole('button', { name: /admin/i }).first().click();
    await expect(page.getByRole('button', { name: /Jetzt einrichten|Set up now/ })).toBeVisible();

    // Reload with status enabled
    await context.unroute('**/api/auth/2fa/status');
    await context.route('**/api/auth/2fa/status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: true,
          enabled_at: new Date().toISOString(),
          backup_codes_remaining: 5,
        }),
      })
    );
    await page.reload();
    await page.getByRole('button', { name: /admin/i }).first().click();
    await expect(page.getByRole('button', { name: /Jetzt einrichten|Set up now/ })).toHaveCount(0);
  });
});
```

- [ ] **Step 3: Run the E2E suite**

Backend + frontend must be running first:

```bash
python start_dev.py
```

In a second shell:

```bash
cd client
npx playwright test userMenuQuickSettings
```

Expected: all three tests PASS. If a locator fails, fix the locator (the actual sidebar labels and dashboard text may differ slightly from the example regexes); do not weaken the assertions.

- [ ] **Step 4: Commit**

```bash
git add client/tests/e2e/userMenuQuickSettings.spec.ts
git commit -m "test(e2e): user menu Quick-Settings end-to-end"
```

---

## Task 11: Final verification + housekeeping

- [ ] **Step 1: Run the full unit test suite**

```bash
cd client
npm test -- --run
```
Expected: ALL tests pass (existing + new).

- [ ] **Step 2: Run typecheck**

```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 3: Run the production build to catch any tree-shake / mode-pi regressions**

```bash
npm run build
```
Expected: SUCCESS, no warnings about missing translations or unused exports related to the new files.

- [ ] **Step 4: Manual end-to-end check in dev**

`python start_dev.py`, log in as admin, open the dropdown, exercise:

1. Switch language DE → EN → DE.
2. Switch units GiB → GB → GiB.
3. Click "Jetzt einrichten" — Modal opens with QR.
4. Cancel — Modal closes, prompt still visible.
5. Reopen — complete the verify step with a real TOTP code (you can use `pyotp` against the displayed secret).
6. Backup-codes step — try to dismiss by clicking the backdrop and pressing Escape. Both should be suppressed.
7. Click "Done" — Modal closes. Reopen the dropdown — 2FA prompt is gone.
8. Go to Settings → Security and verify the disabled-card reflects the new state. Disable 2FA from there. Reopen the user dropdown — prompt should reappear after the next page reload (cache is per page-load).

- [ ] **Step 5: Confirmation commit (if any small fixes were needed)**

If steps 1-4 surfaced a bug, fix it inline and commit with a `fix(...)` message. If everything passes, no commit needed.

- [ ] **Step 6: Push the branch**

```bash
git push
```

---

## Self-Review Notes

**Spec coverage check (against `2026-05-10-user-quick-settings-design.md`):**

- Architecture diagram → Tasks 5, 6, 7, 8, 9 build the components in the diagram. Task 3 + 4 cover the `TwoFactorSetupFlow` extraction.
- Files table → every row in the spec maps to a Create/Modify in this plan's File Structure table.
- `LanguageSection` reuses `availableLanguages` and `i18n.changeLanguage` ✓ (Task 5, Step 3)
- `ByteUnitSection` reuses `useByteUnitMode()` ✓ (Task 6, Step 3)
- `TwoFactorPromptSection` lazy-loads via store, hides on `enabled` or error ✓ (Task 7)
- `twoFactorStatusStore` matches the spec's pseudo-code (loadStatusOnce + refreshStatus + useTwoFactorStatus hook) ✓ (Task 2)
- `TwoFactorSetupFlow` accepts `onComplete` + `onCancel` props ✓; spec adds optional `onStepChange` so the parent can suppress modal close on backup-codes step ✓ (Task 3)
- Modal `closeOnOverlayClick` / `closeOnEscape` props ✓ (Task 1)
- i18n keys under `common.userMenu.quickSettings.*` ✓ (Task 7, Step 4)
- `UserMenu.tsx` wiring + dropdown widening + impersonation preservation ✓ (Task 9)
- E2E coverage ✓ (Task 10)
- Behavior contract from spec (dropdown stays open on language/unit click, closes on 2FA click, status invalidation after setup) — Task 8's container handles this via state + Modal mount; Task 9's wiring leaves the dropdown's existing close-on-outside-click intact while letting Quick-Settings clicks not propagate to close.

**Type/name consistency:** `loadStatusOnce`, `refreshStatus`, `useTwoFactorStatus`, `TwoFactorSetupStep`, `TwoFactorSetupFlowProps`, `TwoFactorPromptSectionProps`, `closeOnOverlayClick`, `closeOnEscape` — all spelled identically wherever they appear.

**Placeholder scan:** None. Every code block is complete; every shell command has expected output. Test regex notes (button name) flag a known fragility and offer a `data-testid` fallback inline.

**Out-of-scope reminders honored:** No date/time refactor. No theme switcher. No quick-action shortcuts. No mobile variant. No 2FA disable/regenerate from the dropdown.
