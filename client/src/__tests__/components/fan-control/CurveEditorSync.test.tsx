import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CurveEditorSync from '../../../components/fan-control/CurveEditorSync';
import type { FanInfo } from '../../../api/fan-control';

// `t` gibt den Schluessel zurueck -- dieselbe Bauform wie in den uebrigen
// fan-control-Tests, damit keine echten Locale-Dateien geladen werden.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function fan(over: Partial<FanInfo> & { fan_id: string }): FanInfo {
  return {
    name: over.fan_id,
    rpm: 800,
    pwm_percent: 40,
    temperature_celsius: 45,
    mode: 'auto',
    min_pwm_percent: 0,
    max_pwm_percent: 100,
    emergency_temp_celsius: 85,
    temp_sensor_id: 'hwmon:x',
    curve_points: [],
    is_active: true,
    ownership: 'owned',
    ...over,
  } as FanInfo;
}

function renderMit(fans: FanInfo[]) {
  return render(
    <CurveEditorSync
      allFans={fans}
      currentFanId="self"
      syncFanId={null}
      onChange={() => {}}
    />,
  );
}

const SELBST = fan({ fan_id: 'self' });

describe('CurveEditorSync: Quellen, die BaluHost nicht regelt', () => {
  it('behaelt einen an das Board zurueckgegebenen Luefter, kennzeichnet ihn aber', () => {
    // Ausblenden waere die einfachere Loesung und die schlechtere: eine
    // BESTEHENDE Sync-Kurve, deren Quelle gerade freigegeben wurde,
    // verschwaende dann aus der Liste, und das Feld zeigte einen leeren Wert
    // bei intakter Konfiguration (#582).
    renderMit([SELBST, fan({ fan_id: 'nct6798:pwm2', ownership: 'released' })]);

    const option = screen.getByRole('option', { name: /nct6798:pwm2/ });
    expect(option).toHaveValue('nct6798:pwm2');
    expect(option.textContent).toContain(
      'system:fanControl.curveTypes.sourceReleased',
    );
  });

  it('kennzeichnet einen aufgegebenen Luefter anders als einen freigegebenen', () => {
    // Der Unterschied ist keine Wortklauberei: bei `released` gibt die
    // Board-Automatik einen echten, lebenden Wert vor. Bei `abandoned`
    // regelt niemand -- der Wert steht seit der Freigabe still, und eine
    // Sync-Kurve darauf friert mit ein.
    renderMit([SELBST, fan({ fan_id: 'nct6798:pwm3', ownership: 'abandoned' })]);

    const option = screen.getByRole('option', { name: /nct6798:pwm3/ });
    expect(option.textContent).toContain(
      'system:fanControl.curveTypes.sourceAbandoned',
    );
  });

  it('laesst einen firmware-verwalteten Luefter weiterhin verschwinden', () => {
    // Regressionswache fuer #480: dort ist die Karte dauerhaft nicht von
    // BaluHost regelbar, und die Option zu zeigen hiesse, eine Quelle
    // anzubieten, die es nie geben wird. Nicht dasselbe wie eine Freigabe,
    // die auf Knopfdruck zurueckgeht.
    renderMit([
      SELBST,
      fan({ fan_id: 'amdgpu:pwm1', pwm_control: 'firmware_managed' }),
    ]);

    expect(screen.queryByRole('option', { name: /amdgpu:pwm1/ })).toBeNull();
  });

  it('laesst einen selbst geregelten Luefter unbeschriftet', () => {
    renderMit([SELBST, fan({ fan_id: 'nct6798:pwm7' })]);

    const option = screen.getByRole('option', { name: /nct6798:pwm7/ });
    expect(option.textContent).toBe('nct6798:pwm7');
  });
});
