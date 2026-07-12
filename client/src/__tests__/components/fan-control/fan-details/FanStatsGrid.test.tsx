import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { FanInfo } from '../../../../api/fan-control';
import FanStatsGrid from '../../../../components/fan-control/fan-details/FanStatsGrid';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const fan = (over: Partial<FanInfo> = {}): FanInfo => ({
  fan_id: 'fan1', name: 'CPU Fan', rpm: 1200, pwm_percent: 50, temperature_celsius: 45,
  mode: 'auto', is_active: true, min_pwm_percent: 30, max_pwm_percent: 100,
  emergency_temp_celsius: 90, temp_sensor_id: 'hwmon0_temp1', hysteresis_celsius: 3,
  curve_points: [], ...over,
} as FanInfo);

const base = {
  fan: fan(), canEdit: true, hysteresis: 3, isUpdatingHysteresis: false,
  hysteresisChanged: false, onHysteresisChange: vi.fn(), onHysteresisSave: vi.fn(),
};

describe('FanStatsGrid', () => {
  it('renders min/max pwm and emergency temp', () => {
    render(<FanStatsGrid {...base} />);
    expect(screen.getByText('30%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('90°C')).toBeInTheDocument();
  });

  it('saves hysteresis on blur when editable', () => {
    const onHysteresisSave = vi.fn();
    render(<FanStatsGrid {...base} onHysteresisSave={onHysteresisSave} />);
    fireEvent.blur(screen.getByRole('spinbutton'));
    expect(onHysteresisSave).toHaveBeenCalled();
  });

  it('renders read-only hysteresis when not editable', () => {
    render(<FanStatsGrid {...base} canEdit={false} />);
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('3°C')).toBeInTheDocument();
  });
});
