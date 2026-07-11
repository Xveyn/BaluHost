import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SystemHealthCard } from '../../../components/dashboard/SystemHealthCard';
import type { SmartStatusResponse } from '../../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const smart: SmartStatusResponse = { checked_at: 'x', devices: [
  { name: 'a', model: 'm', serial: 's1', temperature: 40, status: 'PASSED', capacity_bytes: 1000, used_bytes: 400, used_percent: 40, mount_point: '/', raid_member_of: null, last_self_test: null, attributes: [] },
] };

describe('SystemHealthCard', () => {
  it('renders health rows with all-drives-ok when SMART passed', () => {
    render(<SystemHealthCard smartData={smart} smartLoading={false} smartError={null} raidData={{ arrays: [] }} raidLoading={false} storagePercent={40} />);
    expect(screen.getByText('health.checksTitle')).toBeInTheDocument();
    expect(screen.getByText('health.allDrivesOk')).toBeInTheDocument();
    expect(screen.getByText('40,0%')).toBeInTheDocument();
  });
});
