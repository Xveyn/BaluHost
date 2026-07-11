import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SmartDeviceCard } from '../../../components/dashboard/SmartDeviceCard';
import type { SmartDevice } from '../../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const device: SmartDevice = { name: '/dev/sda', model: 'Samsung SSD', serial: 'SN-9', temperature: 41, status: 'PASSED', capacity_bytes: 1000, used_bytes: 400, used_percent: 40, mount_point: '/', raid_member_of: null, last_self_test: null, attributes: [] };

describe('SmartDeviceCard', () => {
  it('renders model, serial, status and usage percent', () => {
    render(<SmartDeviceCard device={device} usedBytes={400} usagePercent={40} />);
    expect(screen.getByText('Samsung SSD')).toBeInTheDocument();
    expect(screen.getByText(/SN-9/)).toBeInTheDocument();
    expect(screen.getByText('PASSED')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
  });
});
