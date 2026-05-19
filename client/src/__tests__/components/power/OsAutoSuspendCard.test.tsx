import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../../api/sleep', () => ({
  getOsAutoSuspend: vi.fn(),
  setOsAutoSuspend: vi.fn(),
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
const stableT = (k: string, opts?: Record<string, unknown>) => {
  if (opts && 'source' in opts) return `${k}:${String(opts.source)}`;
  return k;
};
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}));

import { OsAutoSuspendCard } from '../../../components/power/OsAutoSuspendCard';
import * as sleepApi from '../../../api/sleep';

describe('OsAutoSuspendCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when supported=false', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: false,
      source: 'none',
      backend_label: '',
      enabled: false,
      timeout_minutes: 0,
      action: 'ignore',
    });
    const { container } = render(<OsAutoSuspendCard />);
    await waitFor(() => {
      expect(container.querySelector('[data-testid="os-auto-suspend-card"]')).toBeNull();
    });
  });

  it('renders source badge from response', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: true,
      timeout_minutes: 15,
      action: 'suspend',
    });
    render(<OsAutoSuspendCard />);
    await waitFor(() => {
      expect(screen.getByTestId('os-auto-suspend-source-badge')).toBeTruthy();
    });
    expect(screen.getByTestId('os-auto-suspend-source-badge').textContent).toContain('badgeSource.kde');
  });

  it('disables timeout/action when not enabled', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: false,
      timeout_minutes: 15,
      action: 'suspend',
    });
    render(<OsAutoSuspendCard />);
    await waitFor(() => {
      const t = screen.getByTestId('os-auto-suspend-timeout') as HTMLInputElement;
      expect(t.disabled).toBe(true);
    });
  });

  it('calls setOsAutoSuspend on save with current form values', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: true,
      timeout_minutes: 15,
      action: 'suspend',
    });
    (sleepApi.setOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: true,
      timeout_minutes: 20,
      action: 'hibernate',
    });
    render(<OsAutoSuspendCard />);
    await waitFor(() => screen.getByTestId('os-auto-suspend-save'));
    const timeoutInput = screen.getByTestId('os-auto-suspend-timeout') as HTMLInputElement;
    fireEvent.change(timeoutInput, { target: { value: '20' } });
    const actionSelect = screen.getByTestId('os-auto-suspend-action') as HTMLSelectElement;
    fireEvent.change(actionSelect, { target: { value: 'hibernate' } });
    fireEvent.click(screen.getByTestId('os-auto-suspend-save'));
    await waitFor(() => {
      expect(sleepApi.setOsAutoSuspend).toHaveBeenCalledWith({
        enabled: true,
        timeout_minutes: 20,
        action: 'hibernate',
      });
    });
  });

  it('shows error toast on load failure', async () => {
    const toast = (await import('react-hot-toast')).default;
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    render(<OsAutoSuspendCard />);
    await waitFor(() => {
      expect((toast.error as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0);
    });
  });
});
