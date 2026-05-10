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
      // The button label may render as the i18n key in test env
      // (no resources loaded). The key contains "enableNow".
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
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
    const button = await screen.findByRole('button');
    fireEvent.click(button);
    expect(onOpenSetup).toHaveBeenCalledOnce();
  });
});
