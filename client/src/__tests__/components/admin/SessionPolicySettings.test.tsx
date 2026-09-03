import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../api/pin', () => ({
  getAuthPolicy: vi.fn(),
  updateAuthPolicy: vi.fn(),
}));

import toast from 'react-hot-toast';
import { getAuthPolicy, updateAuthPolicy } from '../../../api/pin';
import { SessionPolicySettings } from '../../../components/admin/SessionPolicySettings';

const mockedGet = getAuthPolicy as unknown as ReturnType<typeof vi.fn>;
const mockedUpdate = updateAuthPolicy as unknown as ReturnType<typeof vi.fn>;

const POLICY = {
  pin_login_enabled: true,
  pin_grace_window_seconds: 86400,
  idle_timeout_minutes: 4,
  idle_warning_seconds: 60,
  access_token_minutes: 15,
};

function field(testId: string): HTMLInputElement {
  return screen.getByTestId(testId) as HTMLInputElement;
}

describe('SessionPolicySettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGet.mockResolvedValue({ ...POLICY });
    mockedUpdate.mockImplementation((body) => Promise.resolve({ ...POLICY, ...body }));
  });

  it('shows the stored values', async () => {
    render(<SessionPolicySettings />);

    await waitFor(() => expect(field('session-idle-minutes').value).toBe('4'));
    expect(field('session-warning-seconds').value).toBe('60');
    expect(field('session-token-minutes').value).toBe('15');
  });

  it('saves all three fields in one request', async () => {
    // Deliberately one Save button rather than save-on-change: the server
    // refuses an idle window that outlives the token, so raising both needs to
    // travel together or the intermediate state gets rejected.
    render(<SessionPolicySettings />);
    await waitFor(() => expect(field('session-idle-minutes')).toBeTruthy());

    fireEvent.change(field('session-idle-minutes'), { target: { value: '30' } });
    fireEvent.change(field('session-token-minutes'), { target: { value: '720' } });
    fireEvent.click(screen.getByTestId('session-policy-save'));

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalledWith({
      idle_timeout_minutes: 30,
      idle_warning_seconds: 60,
      access_token_minutes: 720,
    }));
    expect(toast.success).toHaveBeenCalled();
  });

  it('refuses an idle window that outlives the token without asking the server', async () => {
    render(<SessionPolicySettings />);
    await waitFor(() => expect(field('session-idle-minutes')).toBeTruthy());

    fireEvent.change(field('session-idle-minutes'), { target: { value: '30' } });
    fireEvent.click(screen.getByTestId('session-policy-save'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(mockedUpdate).not.toHaveBeenCalled();
  });

  it('allows a long idle window once the token covers it', async () => {
    render(<SessionPolicySettings />);
    await waitFor(() => expect(field('session-idle-minutes')).toBeTruthy());

    fireEvent.change(field('session-idle-minutes'), { target: { value: '60' } });
    fireEvent.change(field('session-token-minutes'), { target: { value: '61' } });
    fireEvent.click(screen.getByTestId('session-policy-save'));

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalled());
  });

  it('skips the coupling check when the idle logout is switched off', async () => {
    render(<SessionPolicySettings />);
    await waitFor(() => expect(field('session-idle-minutes')).toBeTruthy());

    fireEvent.change(field('session-idle-minutes'), { target: { value: '0' } });
    fireEvent.click(screen.getByTestId('session-policy-save'));

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ idle_timeout_minutes: 0 }),
    ));
  });

  it('warns about the risk of a long token', async () => {
    // There is no revocation for access tokens — the number deserves a note
    // next to it, not just a spin box.
    render(<SessionPolicySettings />);

    await waitFor(() => expect(screen.getByTestId('session-token-hint')).toBeTruthy());
  });

  it('surfaces a server rejection', async () => {
    mockedUpdate.mockRejectedValue({
      response: { data: { detail: 'The idle window outlives the access token.' } },
    });
    render(<SessionPolicySettings />);
    await waitFor(() => expect(field('session-idle-minutes')).toBeTruthy());

    fireEvent.click(screen.getByTestId('session-policy-save'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
