import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanCard from '../../../components/fan-control/FanCard';
import { FanMode } from '../../../api/fan-control';
import type { FanInfo } from '../../../api/fan-control';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function fan(overrides: Partial<FanInfo> = {}): FanInfo {
  return {
    fan_id: 'hwmon2_pwm1',
    name: 'RDNA3 GPU',
    rpm: 0,
    pwm_percent: 0,
    temperature_celsius: 55,
    mode: FanMode.MANUAL,
    is_active: true,
    min_pwm_percent: 30,
    max_pwm_percent: 100,
    emergency_temp_celsius: 95,
    temp_sensor_id: null,
    curve_points: [],
    hysteresis_celsius: 3,
    is_gpu_fan: true,
    gpu_vendor: 'amd',
    pwm_control: 'supported',
    ...overrides,
  };
}

const noop = vi.fn();

function renderCard(f: FanInfo) {
  return render(
    <FanCard
      fan={f}
      isSelected={false}
      onSelect={noop}
      onModeChange={noop}
      onPWMChange={noop}
      isReadOnly={false}
      isLoading={false}
      sensors={[]}
    />
  );
}

describe('FanCard bei firmware-verwalteter GPU', () => {
  it('zeigt kein Firmware-Badge bei normalem Luefter', () => {
    renderCard(fan());
    expect(screen.queryByTestId('fan-firmware-badge')).toBeNull();
  });

  it('zeigt das Firmware-Badge', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    expect(screen.getByTestId('fan-firmware-badge')).toBeTruthy();
  });

  it('sperrt den PWM-Slider', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.disabled).toBe(true);
  });

  it('laesst die Modus-Buttons bedienbar — sonst sperrt sich der Nutzer aus', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    const enabled = screen
      .getAllByRole('button')
      .filter((b) => !(b as HTMLButtonElement).disabled);
    // AUTO und SCHEDULED sind klickbar (MANUAL ist der aktive Modus)
    expect(enabled.length).toBeGreaterThanOrEqual(2);
  });
});
