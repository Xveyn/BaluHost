import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PermissionStatusCard } from '../../../components/power/PermissionStatusCard';

const linuxStatus = (writeAccess: boolean) => ({
  is_using_linux_backend: true,
  permission_status: {
    has_write_access: writeAccess, user: 'baluhost',
    in_cpufreq_group: true, sudo_available: false,
  },
}) as never;

describe('PermissionStatusCard', () => {
  it('renders nothing without a Linux backend', () => {
    const { container } = render(<PermissionStatusCard status={{ is_using_linux_backend: false } as never} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the warning banner when write access is missing', () => {
    const { container } = render(<PermissionStatusCard status={linuxStatus(false)} />);
    expect(container.querySelector('[data-testid="power-permission-warning"]')).not.toBeNull();
  });

  it('hides the warning banner when write access is present', () => {
    const { container } = render(<PermissionStatusCard status={linuxStatus(true)} />);
    expect(container.querySelector('[data-testid="power-permission-warning"]')).toBeNull();
  });
});
