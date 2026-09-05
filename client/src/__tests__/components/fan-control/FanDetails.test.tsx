import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FanDetails from '../../../components/fan-control/FanDetails';
import { FanMode } from '../../../api/fan-control';
import type { FanInfo, FanCurveProfile } from '../../../api/fan-control';

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
    mode: FanMode.AUTO,
    is_active: true,
    min_pwm_percent: 30,
    max_pwm_percent: 100,
    emergency_temp_celsius: 95,
    temp_sensor_id: null,
    curve_points: [
      { temp: 30, pwm: 30 },
      { temp: 80, pwm: 100 },
    ],
    hysteresis_celsius: 3,
    is_gpu_fan: true,
    gpu_vendor: 'amd',
    curve_type: 'graph',
    pwm_control: 'supported',
    ...overrides,
  };
}

const profile: FanCurveProfile = {
  id: 1,
  name: 'silent',
  is_system: true,
  curve_points: [{ temp: 30, pwm: 30 }],
};

function renderDetails(f: FanInfo) {
  return render(
    <FanDetails
      fan={f}
      onCurveUpdate={vi.fn()}
      isReadOnly={false}
      profiles={[profile]}
      allFans={[f]}
    />
  );
}

describe('FanDetails bei firmware-verwalteter GPU', () => {
  it('zeigt Preset/Profil-Buttons bei normalem Luefter', () => {
    renderDetails(fan());
    expect(screen.getByText('Silent')).toBeTruthy();
  });

  it('versteckt Preset/Profil-Buttons, obwohl die Seite isReadOnly=false meldet', () => {
    renderDetails(fan({ pwm_control: 'firmware_managed' }));
    expect(screen.queryByText('Silent')).toBeNull();
  });

  it('sperrt den Kurventyp-Umschalter', () => {
    renderDetails(fan({ pwm_control: 'firmware_managed' }));
    const graphBtn = screen.getByText('system:fanControl.curveTypes.graph') as HTMLButtonElement;
    expect(graphBtn.disabled).toBe(true);
  });

  it('sperrt die Tabellen-Kurvenbearbeitung ueber editor.canEdit (Hook bekommt editingLocked)', () => {
    renderDetails(fan({ pwm_control: 'firmware_managed' }));
    fireEvent.click(screen.getByText('system:fanControl.curve.table'));
    expect(screen.queryByText('system:fanControl.curve.addPoint')).toBeNull();
  });

  it('zeigt das Firmware-Erklaerpanel statt des manuellen GPU-Toggles', () => {
    renderDetails(fan({ pwm_control: 'firmware_managed' }));
    expect(screen.getByText('system:fanControl.gpu.firmware.title')).toBeTruthy();
    expect(screen.queryByText('system:fanControl.gpu.manualMode.title')).toBeNull();
  });
});
