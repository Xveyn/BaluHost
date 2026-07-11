import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SmartHealthPanel } from '../../../components/dashboard/SmartHealthPanel';
import type { SmartStatusResponse } from '../../../api/smart';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = { smartLoading: false, smartError: null, smartMode: null, smartModeLoading: false, onToggleSmartMode: () => {}, storageUsed: 0 };
const oneDevice: SmartStatusResponse = { checked_at: 'x', devices: [
  { name: '/dev/sda', model: 'Disk A', serial: 'A', temperature: 40, status: 'PASSED', capacity_bytes: 1000, used_bytes: 400, used_percent: 40, mount_point: '/', raid_member_of: null, last_self_test: null, attributes: [] },
] };

describe('SmartHealthPanel', () => {
  it('shows loading state', () => {
    render(<SmartHealthPanel {...base} smartData={null} smartLoading />);
    expect(screen.getByText('smart.loading')).toBeInTheDocument();
  });
  it('shows empty state', () => {
    render(<SmartHealthPanel {...base} smartData={{ checked_at: 'x', devices: [] }} />);
    expect(screen.getByText('smart.noDevices')).toBeInTheDocument();
  });
  it('renders devices', () => {
    render(<SmartHealthPanel {...base} smartData={oneDevice} />);
    expect(screen.getByText('Disk A')).toBeInTheDocument();
  });
  it('renders and fires the dev mode toggle', () => {
    const onToggleSmartMode = vi.fn();
    render(<SmartHealthPanel {...base} smartData={oneDevice} smartMode="mock" onToggleSmartMode={onToggleSmartMode} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onToggleSmartMode).toHaveBeenCalled();
  });
});
