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

  it('laesst Auto erreichbar — sonst sperrt sich der Nutzer im Modus ein', () => {
    // Haelt die Absicht des Vorgaengertests fest: es muss einen Weg zurueck
    // geben. Auto ist der neutrale Modus -- BaluHost haelt den Luefter dann
    // nicht von Hand, was fuer einen firmware-verwalteten Kanal ohnehin gilt.
    renderCard(fan({ pwm_control: 'firmware_managed', mode: FanMode.MANUAL }));
    const auto = screen.getByRole('button', { name: /card\.auto/ }) as HTMLButtonElement;
    expect(auto.disabled).toBe(false);
  });

  it('sperrt Manual und Schedule — beide versprechen eine Steuerung, die nicht stattfindet', () => {
    renderCard(fan({ pwm_control: 'firmware_managed', mode: FanMode.AUTO }));
    const manual = screen.getByRole('button', { name: /card\.manual/ }) as HTMLButtonElement;
    const scheduled = screen.getByRole('button', { name: /card\.scheduled/ }) as HTMLButtonElement;
    expect(manual.disabled).toBe(true);
    expect(scheduled.disabled).toBe(true);
  });

  it('nennt den Grund, statt nur zu sperren', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    expect(screen.getByTestId('fan-uncontrollable-hint')).toBeTruthy();
  });

  it('laesst einen steuerbaren Luefter unangetastet', () => {
    renderCard(fan({ pwm_control: 'supported', mode: FanMode.AUTO }));
    const manual = screen.getByRole('button', { name: /card\.manual/ }) as HTMLButtonElement;
    const scheduled = screen.getByRole('button', { name: /card\.scheduled/ }) as HTMLButtonElement;
    expect(manual.disabled).toBe(false);
    expect(scheduled.disabled).toBe(false);
    expect(screen.queryByTestId('fan-uncontrollable-hint')).toBeNull();
  });
});
