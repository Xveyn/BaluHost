import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../../helpers/queryClient';

// --- i18n: identity `t`, stable `i18n.language` ---
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

// --- Deterministic numeric formatting (dot decimals, no locale dependency) ---
vi.mock('../../../lib/formatters', async (importActual) => {
  const actual = await importActual<typeof import('../../../lib/formatters')>();
  return { ...actual, formatNumber: (v: number, d: number) => v.toFixed(d) };
});

// --- PluginContext: PowerTab's data hook is mocked, but guard defensively ---
vi.mock('../../../contexts/PluginContext', () => ({
  usePlugins: () => ({ plugins: [] }),
}));

// --- The two data hooks the orchestrator delegates to ---
vi.mock('../../../hooks/usePowerTabData', () => ({ usePowerTabData: vi.fn() }));
vi.mock('../../../hooks/useEnergyPrice', () => ({ useEnergyPrice: vi.fn() }));

import { usePowerTabData } from '../../../hooks/usePowerTabData';
import type { UsePowerTabDataResult } from '../../../hooks/usePowerTabData';
import { useEnergyPrice } from '../../../hooks/useEnergyPrice';
import type { UseEnergyPriceResult } from '../../../hooks/useEnergyPrice';
import type { SmartDevice } from '../../../api/smart-devices';
import type { CumulativeEnergyResponse, EnergyPriceConfig } from '../../../api/energy';
import { PowerTab } from '../../../components/system-monitor/PowerTab';

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const plugDevice: SmartDevice = {
  id: 1,
  name: 'Plug',
  plugin_name: 'tapo',
  device_type_id: 'tapo-p110',
  address: '127.0.0.1',
  mac_address: null,
  capabilities: ['power_monitor'],
  is_active: true,
  is_online: true,
  last_seen: null,
  last_error: null,
  state: { power_monitor: { watts: 42, voltage: 230, current: 0.18, energy_today_kwh: 0.5 } },
  created_at: '',
  updated_at: '',
};

const cumulativeData: CumulativeEnergyResponse = {
  device_id: 1,
  device_name: 'Plug',
  period: 'today',
  cost_per_kwh: 0.4,
  currency: 'EUR',
  total_kwh: 0.684,
  total_cost: 0.27,
  data_points: [
    { timestamp: '2026-07-11T00:00:00', cumulative_kwh: 0.0, cumulative_cost: 0.0, instant_watts: 25.0 },
    { timestamp: '2026-07-11T01:00:00', cumulative_kwh: 0.1, cumulative_cost: 0.04, instant_watts: 42.0 },
  ],
};

const priceConfig: EnergyPriceConfig = {
  id: 1,
  cost_per_kwh: 0.4,
  currency: 'EUR',
  updated_at: '',
  updated_by_user_id: null,
};

function powerData(overrides: Partial<UsePowerTabDataResult> = {}): UsePowerTabDataResult {
  return {
    devices: [plugDevice],
    powerSummary: { total_watts: 42, device_count: 1, devices: [{ device_id: 1, name: 'Plug', watts: 42 }] },
    loading: false,
    error: null,
    cumulativeData,
    cumulativeLoading: false,
    cumulativeReady: true,
    totalCurrentPower: 42,
    powerPluginName: 'Tapo',
    cumulativeKeyArgs: { period: 'today', start: null, end: null },
    ...overrides,
  };
}

const energyPrice: UseEnergyPriceResult = {
  priceConfig,
  editingPrice: false,
  setEditingPrice: vi.fn(),
  priceInput: '0.4',
  setPriceInput: vi.fn(),
  savingPrice: false,
  savePrice: vi.fn(),
};

describe('PowerTab', () => {
  beforeEach(() => {
    vi.mocked(useEnergyPrice).mockReturnValue(energyPrice);
  });

  it('renders stat cards, a device card and the chart toolbar', () => {
    vi.mocked(usePowerTabData).mockReturnValue(powerData());

    render(<PowerTab />, { wrapper });

    // Current-power stat value (formatNumber(42, 1)) — appears in the summary
    // card and the device card, so assert at least one match.
    expect(screen.getAllByText('42.0').length).toBeGreaterThan(0);
    // Device name renders (device card + chart tab)
    expect(screen.getAllByText('Plug').length).toBeGreaterThan(0);
  });

  it('shows the empty state when there are no devices', () => {
    vi.mocked(usePowerTabData).mockReturnValue(powerData({ devices: [], totalCurrentPower: 0 }));

    render(<PowerTab />, { wrapper });

    expect(screen.getByRole('link')).toHaveAttribute('href', '/smart-devices');
  });
});
