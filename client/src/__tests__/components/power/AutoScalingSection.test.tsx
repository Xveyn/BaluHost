import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/power-management', async () => {
  const actual = await vi.importActual<typeof import('../../../api/power-management')>('../../../api/power-management');
  return { ...actual, updateAutoScalingConfig: vi.fn() };
});

import { updateAutoScalingConfig } from '../../../api/power-management';
import { AutoScalingSection } from '../../../components/power/AutoScalingSection';

const cfg = {
  enabled: true,
  cpu_surge_threshold: 90, cpu_medium_threshold: 60, cpu_low_threshold: 30,
  cooldown_seconds: 15, use_cpu_monitoring: true,
} as never;

function renderSection() {
  const onRefresh = vi.fn();
  const onBusyChange = vi.fn();
  const { container } = render(
    <AutoScalingSection
      autoScaling={cfg}
      dimmed={false}
      busy={false}
      onBusyChange={onBusyChange}
      onRefresh={onRefresh}
    />,
  );
  return { onRefresh, onBusyChange, container };
}

describe('AutoScalingSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the config card in display mode', () => {
    const { container } = renderSection();
    expect(container.querySelector('[data-testid="auto-scaling-section"]')).not.toBeNull();
  });

  it('blocks save on an invalid threshold ordering (no API call)', async () => {
    (updateAutoScalingConfig as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    renderSection();
    fireEvent.click(screen.getByTestId('auto-scaling-edit'));
    // surge (10) below medium (60) → invalid ordering
    fireEvent.change(screen.getByTestId('auto-scaling-input-surge'), { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('auto-scaling-save'));
    await waitFor(() => {});
    expect(updateAutoScalingConfig).not.toHaveBeenCalled();
  });

  it('saves a valid edit: calls the API and onRefresh', async () => {
    (updateAutoScalingConfig as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const { onRefresh } = renderSection();
    fireEvent.click(screen.getByTestId('auto-scaling-edit'));
    fireEvent.click(screen.getByTestId('auto-scaling-save'));
    await waitFor(() => expect(updateAutoScalingConfig).toHaveBeenCalledTimes(1));
    expect(onRefresh).toHaveBeenCalled();
  });
});
