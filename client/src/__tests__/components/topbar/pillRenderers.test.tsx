import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PillRenderer } from '../../../components/topbar/pillRenderers';
import type { PillState } from '../../../api/statusBar';

const dict: Record<string, string> = {
  'pills.vpn.live': 'VPN',
  'pills.vpn.connected': '{{n}} connected',
  'pills.raid.live': 'RAID',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const tmpl = dict[key];
      if (tmpl === undefined) return (opts?.defaultValue as string) ?? key;
      return tmpl.replace(/\{\{(\w+)\}\}/g, (_m, k) => String(opts?.[k] ?? ''));
    },
  }),
}));

function renderPill(pill: PillState) {
  return render(<MemoryRouter><PillRenderer pill={pill} flat /></MemoryRouter>);
}

const base = { kind: 'state' as const, tone: 'info' as const, href: '/x' };

describe('PillRenderer', () => {
  it('translates label_key and value_key with params', () => {
    renderPill({ ...base, id: 'vpn', label_key: 'pills.vpn.live',
      value_key: 'pills.vpn.connected', value_params: { n: 2 } });
    expect(screen.getByText('VPN')).toBeInTheDocument();
    expect(screen.getByText('2 connected')).toBeInTheDocument();
  });

  it('falls back to raw value when value_key is unknown', () => {
    renderPill({ ...base, id: 'raid', label_key: 'pills.raid.live',
      value_key: 'pills.raid.status.weirdstate', value: 'weirdstate' });
    expect(screen.getByText('RAID')).toBeInTheDocument();
    expect(screen.getByText('weirdstate')).toBeInTheDocument();
  });

  it('renders a pure-data value verbatim when there is no value_key', () => {
    renderPill({ ...base, id: 'temp', label_key: 'pills.temp.live', value: '95°C' });
    expect(screen.getByText('95°C')).toBeInTheDocument();
  });
});

describe('PillRenderer with plugin pills', () => {
  const pluginBase = { ...base, id: 'plugin:steam_gaming:session', label_key: 'pill_label', icon: 'Gamepad2' };

  it('resolves the label from the plugin translations', () => {
    renderPill({
      ...pluginBase,
      label_text: 'Gaming Session',
      translations: { en: { pill_label: 'Gaming Session' } },
      value: 'Metro Exodus',
    });
    expect(screen.getByText('Gaming Session')).toBeInTheDocument();
    expect(screen.getByText('Metro Exodus')).toBeInTheDocument();
  });

  it('falls back to label_text when the key is missing from the translations', () => {
    renderPill({
      ...pluginBase,
      label_text: 'Gaming Session',
      translations: { en: { something_else: 'nope' } },
    });
    expect(screen.getByText('Gaming Session')).toBeInTheDocument();
  });

  it('still uses core i18n for pills without translations', () => {
    renderPill({ ...base, id: 'raid', label_key: 'pills.raid.live' });
    expect(screen.getByText('RAID')).toBeInTheDocument();
  });

  it('falls back to the raw label_key when both label_text and the translation lookup are missing', () => {
    renderPill({
      ...pluginBase,
      label_key: 'pill_label_missing',
      translations: { en: { something_else: 'nope' } },
    });
    expect(screen.getByText('pill_label_missing')).toBeInTheDocument();
  });
});
