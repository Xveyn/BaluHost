import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string) => `${ns}:${key}`,
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/powerPermissions', () => ({
  getUserPowerPermissions: vi.fn(),
  updateUserPowerPermissions: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../lib/errorHandling', () => ({
  handleApiError: vi.fn(),
}));

import { PowerPermissionsSection } from '../../../components/user-management/PowerPermissionsSection';
import { getUserPowerPermissions } from '../../../api/powerPermissions';

const PERMS = {
  user_id: 7,
  can_soft_sleep: false, can_wake: false, can_suspend: false, can_wol: false,
  can_toggle_desktop: false, can_unlock_session: false, can_control_audio: false,
  can_manage_displays: false, can_manage_bluetooth: false,
  granted_by: null, granted_by_username: null, granted_at: null,
};

beforeEach(() => {
  vi.mocked(getUserPowerPermissions).mockResolvedValue(structuredClone(PERMS) as never);
});

describe('PowerPermissionsSection — Bluetooth', () => {
  it('bietet den Schalter fuer can_manage_bluetooth an', async () => {
    render(<PowerPermissionsSection userId={7} userRole="user" />);
    await waitFor(() => expect(getUserPowerPermissions).toHaveBeenCalled());
    expect(
      await screen.findByText('admin:users.systemPermissions.items.manageBluetooth.label'),
    ).toBeTruthy();
  });
});
