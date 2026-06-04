import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../../api/monitoring', () => ({
  getRetentionConfig: vi.fn(),
  updateRetentionConfig: vi.fn(),
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
const stableT = (k: string, opts?: Record<string, unknown>) =>
  opts && 'count' in opts ? `${k}:${String(opts.count)}` : k;
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}));

import RetentionSettings from '../../../components/admin/RetentionSettings';
import * as api from '../../../api/monitoring';

const CONFIGS = {
  configs: [
    { metric_type: 'cpu', retention_hours: 168, db_persist_interval: 12, is_enabled: true, samples_cleaned: 0 },
    { metric_type: 'gpu', retention_hours: 168, db_persist_interval: 12, is_enabled: true, samples_cleaned: 0 },
  ],
};

describe('RetentionSettings', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders one row per managed metric and no power row', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());
    expect(screen.getByTestId('retention-input-gpu')).toBeTruthy();
    expect(screen.queryByTestId('retention-input-power')).toBeNull();
  });

  it('applies a preset value to the input', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());
    fireEvent.click(screen.getByTestId('retention-preset-cpu-720'));
    expect((screen.getByTestId('retention-input-cpu') as HTMLInputElement).value).toBe('720');
  });

  it('saves only the changed metrics', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    (api.updateRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());

    fireEvent.change(screen.getByTestId('retention-input-cpu'), { target: { value: '24' } });
    fireEvent.click(screen.getByTestId('retention-save'));

    await waitFor(() => expect(api.updateRetentionConfig).toHaveBeenCalledTimes(1));
    expect(api.updateRetentionConfig).toHaveBeenCalledWith('cpu', 24);
  });

  it('disables save when the value is out of range', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());
    fireEvent.change(screen.getByTestId('retention-input-cpu'), { target: { value: '99999' } });
    expect((screen.getByTestId('retention-save') as HTMLButtonElement).disabled).toBe(true);
  });
});
