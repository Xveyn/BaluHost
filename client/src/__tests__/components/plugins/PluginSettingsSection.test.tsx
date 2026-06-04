import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../../api/plugins', () => ({ updatePluginConfig: vi.fn().mockResolvedValue({}) }));
vi.mock('../../../api/smart-devices', () => ({ smartDevicesApi: { list: vi.fn().mockResolvedValue({ data: { devices: [] } }) } }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
const stableT = (k: string, opts?: Record<string, unknown>) =>
  opts && 'count' in opts ? `${k}:${String(opts.count)}` : k;
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: stableT, i18n: { language: 'en' } }) }));

import { PluginSettingsSection } from '../../../components/plugins/PluginSettingsSection';
import * as pluginsApi from '../../../api/plugins';

const SCHEMA = {
  properties: {
    retention_days: {
      type: 'integer', title: 'Sample retention (days)', default: 30,
      minimum: 0, maximum: 365, 'x-presets': [7, 30, 90, 180], 'x-unlimited-value': 0,
    },
  },
};

describe('PluginSettingsSection number/retention field', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the number input and the unlimited chip', async () => {
    render(<PluginSettingsSection pluginName="tapo_smart_plug" configSchema={SCHEMA} config={{ retention_days: 30 }} />);
    expect(screen.getByRole('spinbutton')).toBeTruthy();
    expect(screen.getByText('settings.unlimited')).toBeTruthy();
  });

  it('clicking a preset sets the value and saves it', async () => {
    render(<PluginSettingsSection pluginName="tapo_smart_plug" configSchema={SCHEMA} config={{ retention_days: 30 }} />);
    fireEvent.click(screen.getByText('settings.presetDays:90'));
    fireEvent.click(screen.getByText('settings.save'));
    await waitFor(() => expect(pluginsApi.updatePluginConfig).toHaveBeenCalledWith('tapo_smart_plug', { retention_days: 90 }));
  });

  it('clicking unlimited sets the sentinel (0)', async () => {
    render(<PluginSettingsSection pluginName="tapo_smart_plug" configSchema={SCHEMA} config={{ retention_days: 30 }} />);
    fireEvent.click(screen.getByText('settings.unlimited'));
    fireEvent.click(screen.getByText('settings.save'));
    await waitFor(() => expect(pluginsApi.updatePluginConfig).toHaveBeenCalledWith('tapo_smart_plug', { retention_days: 0 }));
  });
});
