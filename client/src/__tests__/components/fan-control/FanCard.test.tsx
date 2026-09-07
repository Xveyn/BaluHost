import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

  it('benennt Zero-RPM, statt eine nackte Null zu zeigen', () => {
    renderCard(fan({ pwm_control: 'firmware_managed', rpm: 0 }));
    expect(screen.getByTestId('fan-zero-rpm')).toBeTruthy();
  });

  it('zeigt den Hinweis nicht, wenn der Luefter laeuft', () => {
    renderCard(fan({ pwm_control: 'firmware_managed', rpm: 900 }));
    expect(screen.queryByTestId('fan-zero-rpm')).toBeNull();
  });

  it('zeigt ihn nicht bei einem gewoehnlichen Luefter mit 0 RPM', () => {
    // Ein stehender Gehaeuseluefter ist ein Befund, kein Zero-RPM-Modus.
    renderCard(fan({ pwm_control: 'supported', rpm: 0 }));
    expect(screen.queryByTestId('fan-zero-rpm')).toBeNull();
  });

  it('behauptet kein Zero-RPM, wenn gar kein Messwert vorliegt', () => {
    // rpm null heisst "keine Tacho-Ablesung", nicht "steht still".
    renderCard(fan({ pwm_control: 'firmware_managed', rpm: null }));
    expect(screen.queryByTestId('fan-zero-rpm')).toBeNull();
    expect(screen.getByText('—')).toBeTruthy();
  });
});

describe('FanCard bei fehlendem Schreibrecht (#568 Punkt 2)', () => {
  it('zeigt kein Badge, solange der Kanal schreibbar ist', () => {
    renderCard(fan({ pwm_control: 'supported' }));
    expect(screen.queryByTestId('fan-no-permission-badge')).toBeNull();
  });

  it('benennt den Kanal, der gerade nicht geschrieben wird', () => {
    // Vorher sagte nur ein globales Banner "readonly" -- welcher der fuenf
    // Kanaele betroffen ist, stand nirgends.
    renderCard(fan({ pwm_control: 'no_permission' }));
    expect(screen.getByTestId('fan-no-permission-badge')).toBeInTheDocument();
  });

  it('sperrt die Bedienelemente NICHT -- der Zustand ist behebbar', () => {
    // Anders als firmware_managed: BaluHost wuerde den Kanal steuern, sobald
    // es darf. Ihn zu sperren hiesse, einen voruebergehenden Laufzeit-Befund
    // wie eine dauerhafte Hardware-Eigenschaft zu behandeln -- der Nutzer
    // koennte dann nicht einmal den Modus vorbereiten.
    // mode: AUTO, sonst waere der Manual-Knopf schon deshalb gesperrt, weil er
    // der aktive Modus ist -- das haette die Zusicherung ohne Aussagekraft
    // gemacht (und tat es beim ersten Lauf).
    renderCard(fan({
      pwm_control: 'no_permission', is_gpu_fan: false, gpu_vendor: null,
      mode: FanMode.AUTO,
    }));
    const manual = screen.getByRole('button', { name: /card\.manual/ }) as HTMLButtonElement;
    const scheduled = screen.getByRole('button', { name: /card\.scheduled/ }) as HTMLButtonElement;
    expect(manual.disabled).toBe(false);
    expect(scheduled.disabled).toBe(false);
  });

  it('zeigt das Firmware-Badge nicht mit', () => {
    renderCard(fan({ pwm_control: 'no_permission' }));
    expect(screen.queryByTestId('fan-firmware-badge')).toBeNull();
  });
});

describe('FanCard bei Rueckgabe an die Board-Automatik (#534)', () => {
  function renderMitRueckweg(f: FanInfo, onReacquire = vi.fn()) {
    render(
      <FanCard
        fan={f}
        isSelected={false}
        onSelect={noop}
        onModeChange={noop}
        onPWMChange={noop}
        onReacquire={onReacquire}
        isReadOnly={false}
        isLoading={false}
        sensors={[]}
      />
    );
    return onReacquire;
  }

  it('zeigt im Normalfall kein Badge', () => {
    renderMitRueckweg(fan({ ownership: 'owned' }));
    expect(screen.queryByTestId('fan-released-badge')).toBeNull();
    expect(screen.queryByTestId('fan-abandoned-badge')).toBeNull();
    expect(screen.queryByTestId('fan-reacquire-button')).toBeNull();
  });

  it('sagt bei geglueckter Rueckgabe, dass das Board regelt', () => {
    renderMitRueckweg(fan({ ownership: 'released' }));
    expect(screen.getByTestId('fan-released-badge')).toBeInTheDocument();
    expect(screen.queryByTestId('fan-abandoned-badge')).toBeNull();
  });

  it('sagt bei gescheiterter Rueckgabe, dass NIEMAND regelt', () => {
    // Der Unterschied ist der Kern von #534: bei 'abandoned' ist die
    // Rueckgabe selbst fehlgeschlagen -- eine Karte, die auch hier "das Board
    // regelt" anzeigt, behauptet eine Regelung, die es nicht gibt.
    renderMitRueckweg(fan({ ownership: 'abandoned' }));
    expect(screen.getByTestId('fan-abandoned-badge')).toBeInTheDocument();
    expect(screen.queryByTestId('fan-released-badge')).toBeNull();
  });

  it('bietet den Rueckweg an und meldet ihn', () => {
    const onReacquire = renderMitRueckweg(fan({ ownership: 'released' }));
    fireEvent.click(screen.getByTestId('fan-reacquire-button'));
    expect(onReacquire).toHaveBeenCalledWith('hwmon2_pwm1');
  });

  it('laesst den Rueckweg auch dann erreichbar, wenn alles andere gesperrt ist', () => {
    // Der Befund, an dem der erste Anlauf haengenblieb: eine Sperre analog zu
    // firmware_managed wuerde genau das Bedienelement deaktivieren, ueber das
    // man zurueckkaeme -- ein Zustand ohne Ausgang.
    render(
      <FanCard
        fan={fan({ ownership: 'abandoned', mode: FanMode.AUTO })}
        isSelected={false}
        onSelect={noop}
        onModeChange={noop}
        onPWMChange={noop}
        onReacquire={vi.fn()}
        isReadOnly={true}
        isLoading={false}
        sensors={[]}
      />
    );
    const zurueck = screen.getByTestId('fan-reacquire-button') as HTMLButtonElement;
    expect(zurueck.disabled).toBe(false);
    const manual = screen.getByRole('button', { name: /card\.manual/ }) as HTMLButtonElement;
    expect(manual.disabled).toBe(true);
  });

  it('sperrt die Modus-Knoepfe eines freigegebenen Luefters', () => {
    // Schreiben ist ohnehin ausgesetzt -- ein bedienbarer Regler waere hier
    // dasselbe leere Versprechen wie bei firmware_managed.
    renderMitRueckweg(fan({ ownership: 'released', mode: FanMode.AUTO }));
    const manual = screen.getByRole('button', { name: /card\.manual/ }) as HTMLButtonElement;
    expect(manual.disabled).toBe(true);
  });
});

describe('FanCard benennt den Grund der Abgabe (#534 Punkt 2)', () => {
  function renderMitGrund(f: FanInfo) {
    render(
      <FanCard
        fan={f}
        isSelected={false}
        onSelect={noop}
        onModeChange={noop}
        onPWMChange={noop}
        onReacquire={vi.fn()}
        isReadOnly={false}
        isLoading={false}
        sensors={[]}
      />
    );
  }

  it('nennt fehlende Schreibrechte als Grund', () => {
    renderMitGrund(fan({ ownership: 'released', release_reason: 'not_controllable' }));
    expect(screen.getByTestId('fan-release-reason').textContent)
      .toContain('causeNotControllable');
  });

  it('nennt die tote Temperaturquelle als Grund', () => {
    // Der Unterschied zaehlt: der Nutzer muss wissen, ob er Rechte oder einen
    // Sensor reparieren soll.
    renderMitGrund(fan({ ownership: 'released', release_reason: 'no_target' }));
    expect(screen.getByTestId('fan-release-reason').textContent)
      .toContain('causeNoTarget');
  });

  it('zeigt ohne Grund keine Zeile', () => {
    renderMitGrund(fan({ ownership: 'released', release_reason: null }));
    expect(screen.queryByTestId('fan-release-reason')).toBeNull();
  });
});
