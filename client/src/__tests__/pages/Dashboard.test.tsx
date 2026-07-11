import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithQueryClient } from '../helpers/queryClient';

// --- i18n + router: identity `t`, no-op navigate (no <Router> in the test tree) ---
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

// --- Auth: non-admin (gates the admin-only service/scheduler alerts off) ---
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ isAdmin: false }) }));

// --- Page-level data hooks (all mocked; the page-under-test only orchestrates them) ---
vi.mock('../../hooks/useSystemTelemetry', () => ({ useSystemTelemetry: vi.fn() }));
vi.mock('../../hooks/useSmartData', () => ({ useSmartData: vi.fn() }));
vi.mock('../../hooks/useRaidStatus', () => ({ useRaidStatus: vi.fn() }));
vi.mock('../../hooks/useSmartMode', () => ({ useSmartMode: vi.fn() }));
vi.mock('../../hooks/useGpuPresence', () => ({ useGpuPresence: vi.fn() }));
vi.mock('../../hooks/useGpuCurrent', () => ({ useGpuCurrent: vi.fn() }));
vi.mock('../../hooks/useNextMaintenance', () => ({ useNextMaintenance: vi.fn() }));
vi.mock('../../hooks/useServicesSummary', () => ({ useServicesSummary: vi.fn() }));
vi.mock('../../hooks/useLiveActivities', () => ({ useLiveActivities: vi.fn() }));

// --- Child widgets that fetch their own data: render nothing so the test stays isolated ---
vi.mock('../../components/dashboard/PluginDashboardPanel', () => ({ PluginDashboardPanel: () => null }));
vi.mock('../../components/dashboard/NetworkWidget', () => ({ NetworkWidget: () => null }));
vi.mock('../../components/dashboard/ServicesPanel', () => ({ ServicesPanel: () => null }));
vi.mock('../../components/dashboard/PluginsPanel', () => ({ PluginsPanel: () => null }));
vi.mock('../../components/dashboard/ConnectedDevicesWidget', () => ({ ConnectedDevicesWidget: () => null }));
vi.mock('../../components/dashboard/NextMaintenanceWidget', () => ({ NextMaintenanceWidget: () => null }));
vi.mock('../../components/dashboard/ActivityFeed', () => ({ ActivityFeed: () => null }));

import { useSystemTelemetry } from '../../hooks/useSystemTelemetry';
import { useSmartData } from '../../hooks/useSmartData';
import { useRaidStatus } from '../../hooks/useRaidStatus';
import { useSmartMode } from '../../hooks/useSmartMode';
import { useGpuPresence } from '../../hooks/useGpuPresence';
import { useGpuCurrent } from '../../hooks/useGpuCurrent';
import { useNextMaintenance } from '../../hooks/useNextMaintenance';
import { useServicesSummary } from '../../hooks/useServicesSummary';
import { useLiveActivities } from '../../hooks/useLiveActivities';
import type { SystemInfoResponse } from '../../api/system';
import type { NormalisedStorageInfo, TelemetryHistory } from '../../hooks/useSystemTelemetry';
import type { SmartDevice, SmartStatusResponse } from '../../api/smart';
import Dashboard from '../../pages/Dashboard';

const systemInfo: SystemInfoResponse = {
  cpu: { usage: 12, cores: 8, frequency_mhz: 3600, model: 'Test CPU', temperature_celsius: 45 },
  memory: { total: 16_000_000_000, used: 8_000_000_000, free: 8_000_000_000, speed_mts: 3200, type: 'DDR4' },
  disk: { total: 1_000_000_000_000, used: 500_000_000_000, free: 500_000_000_000 },
  uptime: 3600,
  system_uptime: 7200,
  dev_mode: true,
};

const storageInfo: NormalisedStorageInfo = {
  filesystem: 'ext4',
  total: 1_000_000_000_000,
  used: 500_000_000_000,
  available: 500_000_000_000,
  use_percent: '50%',
  mount_point: '/mnt',
  percent: 50,
};

const history: TelemetryHistory = { cpu: [], memory: [], network: [] };

const smartDevice = (over: Partial<SmartDevice> = {}): SmartDevice => ({
  name: '/dev/sda',
  model: 'Disk A',
  serial: 'SER-A',
  temperature: 38,
  status: 'PASSED',
  capacity_bytes: 1_000_000_000_000,
  used_bytes: 500_000_000_000,
  used_percent: 50,
  mount_point: '/mnt/a',
  raid_member_of: null,
  last_self_test: null,
  attributes: [],
  ...over,
});

const smartResponse = (devices: SmartDevice[]): SmartStatusResponse => ({
  checked_at: '2026-01-01T00:00:00Z',
  devices,
});

function mockPage(smartData: SmartStatusResponse) {
  (useSystemTelemetry as any).mockReturnValue({
    system: systemInfo,
    storage: storageInfo,
    loading: false,
    refreshing: false,
    error: null,
    lastUpdated: new Date('2026-01-01T00:00:00Z'),
    history,
  });
  (useSmartData as any).mockReturnValue({
    smartData,
    loading: false,
    error: null,
    lastUpdated: null,
    refetch: vi.fn(),
  });
  (useRaidStatus as any).mockReturnValue({
    raidData: { arrays: [] },
    raidLoading: false,
    error: null,
    lastUpdated: null,
    refetch: vi.fn(),
  });
  (useSmartMode as any).mockReturnValue({
    smartMode: null,
    isDevMode: false,
    toggle: vi.fn(),
    isToggling: false,
  });
  (useGpuPresence as any).mockReturnValue({ present: false, info: null, loading: false });
  (useGpuCurrent as any).mockReturnValue(null);
  (useNextMaintenance as any).mockReturnValue({
    nextMaintenance: null,
    allSchedulers: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
  (useServicesSummary as any).mockReturnValue({
    summary: { running: 0, stopped: 0, error: 0, disabled: 0, total: 0 },
    services: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
  (useLiveActivities as any).mockReturnValue({ activities: [] });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Dashboard (page orchestration — F2/#301 integration)', () => {
  it('renders the dashboard with a quick-stat value and the SMART panel', () => {
    mockPage(smartResponse([smartDevice({ model: 'Disk A', status: 'PASSED' })]));
    renderWithQueryClient(<Dashboard />);

    expect(screen.getByText('title')).toBeInTheDocument();       // header i18n key
    expect(screen.getByText('Disk A')).toBeInTheDocument();      // SMART panel device model
  });

  it('surfaces a critical alert when a SMART device has FAILED', () => {
    mockPage(smartResponse([smartDevice({ model: 'Disk A', status: 'FAILED' })]));
    renderWithQueryClient(<Dashboard />);

    expect(screen.getByText('alerts.smartFailure.title')).toBeInTheDocument();
  });
});
