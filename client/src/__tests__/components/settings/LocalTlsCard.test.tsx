import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'count' in opts ? `${key}:${opts.count}` : key,
  }),
}));
vi.mock('react-hot-toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from 'react-hot-toast';
vi.mock('../../../api/localTls', async () => {
  const actual = await vi.importActual<typeof import('../../../api/localTls')>('../../../api/localTls');
  return {
    ...actual,
    getLocalTlsStatus: vi.fn(),
    setLocalTlsToken: vi.fn(),
    clearLocalTlsToken: vi.fn(),
    renewLocalTls: vi.fn(),
    updateLocalTlsDns: vi.fn(),
  };
});
vi.mock('../../../api/plugins', () => ({
  getPluginConfig: vi.fn(),
}));

import * as api from '../../../api/localTls';
import { getPluginConfig } from '../../../api/plugins';
import LocalTlsCard from '../../../components/settings/LocalTlsCard';

const NOW = new Date('2026-11-25T12:00:00Z');
const inDays = (d: number) => new Date(NOW.getTime() + d * 86400_000).toISOString();

const base: api.LocalTlsStatus = {
  configured: true, lego: 'ok', lego_version: '4.35.0', current_ip: '192.168.1.5',
  last_ip: '192.168.1.5', last_ip_set_at: inDays(-1),
  last_dns_at: inDays(-1), last_dns_ok: true, last_dns_reason: null, cert_not_after: inDays(60),
  cert_fingerprint: 'AA', served_matches: true, last_renew_at: inDays(-3),
  last_renew_ok: true, last_renew_reason: null, running: false, token_set: false, nginx_hint: null,
};

function renderCard(over: Partial<api.LocalTlsStatus> = {}) {
  (getPluginConfig as any).mockResolvedValue({ name: 'local_tls', config: { domain: 'nas.example.org' } });
  (api.getLocalTlsStatus as any).mockResolvedValue({ ...base, ...over });
  return render(<MemoryRouter><LocalTlsCard /></MemoryRouter>);
}

describe('<LocalTlsCard>', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('zeigt Domain und Ablaufdatum', async () => {
    renderCard();
    expect(await screen.findByText('nas.example.org')).toBeTruthy();
    expect(screen.getByTestId('cert-expiry')).toBeTruthy();
  });

  it.each([
    [6, 'red'], [7, 'yellow'], [20, 'yellow'], [21, 'green'],
  ])('Ablauf in %i Tagen ist %s', async (days, color) => {
    renderCard({ cert_not_after: new Date(NOW.getTime() + days * 86400_000 + 3600_000).toISOString() });
    const el = await screen.findByTestId('cert-expiry');
    expect(el.getAttribute('data-severity')).toBe(color);
  });

  it('Einstellungen-Link fuehrt zur Plugin-Verwaltung', async () => {
    renderCard();
    const link = await screen.findByText('settings');
    expect(link.closest('a')?.getAttribute('href')).toBe('/plugins');
  });

  it('abgelaufenes Zertifikat zeigt expired statt negativer Tage', async () => {
    renderCard({ cert_not_after: inDays(-3) });
    const el = await screen.findByTestId('cert-expiry');
    expect(el.textContent).toContain('cert.expired');
    expect(el.textContent).not.toContain('daysLeft');
    expect(el.getAttribute('data-severity')).toBe('red');
  });

  it('lego fehlt: Installationsbefehl sichtbar', async () => {
    renderCard({ lego: 'missing', lego_version: null });
    expect(await screen.findByText('sudo apt install -t trixie-backports lego')).toBeTruthy();
  });

  it('lego ok: kein Installationsbefehl', async () => {
    renderCard();
    await screen.findByTestId('cert-expiry');
    expect(screen.queryByText('sudo apt install -t trixie-backports lego')).toBeNull();
  });

  it('Token-Feld leert sich nach dem Speichern und zeigt den Wert nie', async () => {
    (api.setLocalTlsToken as any).mockResolvedValue(undefined);
    renderCard();
    const input = (await screen.findByTestId('token-input')) as HTMLInputElement;
    expect(input.type).toBe('password');
    fireEvent.change(input, { target: { value: 'geheim-token' } });
    fireEvent.click(screen.getByText('token.save'));
    await waitFor(() => expect(api.setLocalTlsToken).toHaveBeenCalledWith('geheim-token'));
    await waitFor(() => expect(input.value).toBe(''));
    expect(screen.queryByText('geheim-token')).toBeNull();
  });

  it('409 bei Jetzt erneuern zeigt Hinweis', async () => {
    (api.renewLocalTls as any).mockRejectedValue({ response: { status: 409, data: { error: 'already_running' } } });
    renderCard();
    fireEvent.click(await screen.findByText('actions.renew'));
    expect(await screen.findByText('error.already_running')).toBeTruthy();
  });

  it('nginx_hint: Block sichtbar', async () => {
    renderCard({ nginx_hint: 'server_name nas.example.org;' });
    expect(await screen.findByText('server_name nas.example.org;')).toBeTruthy();
    expect(screen.getByText('actions.copy')).toBeTruthy();
  });

  it('ohne nginx_hint kein Block', async () => {
    renderCard();
    await screen.findByTestId('cert-expiry');
    expect(screen.queryByText('actions.copy')).toBeNull();
  });

  it('zeigt das letzte DNS-Ergebnis samt Grund', async () => {
    renderCard({ last_dns_ok: false, last_dns_reason: 'duckdns rejected the update' });
    const el = await screen.findByTestId('dns-result');
    expect(el.textContent).toContain('dns.failed');
    expect(el.textContent).toContain('duckdns rejected the update');
  });

  it('DNS jetzt aktualisieren: Fehlschlag meldet den Grund statt Erfolg', async () => {
    (api.updateLocalTlsDns as any).mockResolvedValue({
      ...base, last_dns_ok: false, last_dns_reason: 'duckdns rejected the update',
    });
    renderCard();
    fireEvent.click(await screen.findByText('actions.updateDns'));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('actions.dnsFailed');
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });

  it('DNS jetzt aktualisieren: Erfolg meldet Erfolg', async () => {
    (api.updateLocalTlsDns as any).mockResolvedValue({ ...base });
    renderCard();
    fireEvent.click(await screen.findByText('actions.updateDns'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('actions.dnsDone'));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('Jetzt erneuern: Fehlschlag meldet den Grund statt Erfolg', async () => {
    (api.renewLocalTls as any).mockResolvedValue({
      ...base, last_renew_ok: false, last_renew_reason: 'acme: error 429',
    });
    renderCard();
    fireEvent.click(await screen.findByText('actions.renew'));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('lego unlesbar: eigener Text und Pruefbefehl statt Installationsbefehl', async () => {
    renderCard({ lego: 'unreadable', lego_version: null });
    expect(await screen.findByText('lego.unreadable')).toBeTruthy();
    expect(screen.getByText('lego --version')).toBeTruthy();
    expect(screen.queryByText('sudo apt install -t trixie-backports lego')).toBeNull();
  });

  it('Token wird getrimmt gespeichert', async () => {
    (api.setLocalTlsToken as any).mockResolvedValue(undefined);
    renderCard();
    const input = (await screen.findByTestId('token-input')) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '  geheim-token\n' } });
    fireEvent.click(screen.getByText('token.save'));
    await waitFor(() => expect(api.setLocalTlsToken).toHaveBeenCalledWith('geheim-token'));
  });

  it('nur Leerzeichen: Speichern bleibt gesperrt', async () => {
    renderCard();
    const input = (await screen.findByTestId('token-input')) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '   ' } });
    expect((screen.getByText('token.save') as HTMLButtonElement).disabled).toBe(true);
  });

  it('leere Domain zeigt notConfigured', async () => {
    (getPluginConfig as any).mockResolvedValue({ name: 'local_tls', config: { domain: '' } });
    (api.getLocalTlsStatus as any).mockResolvedValue({ ...base, configured: false });
    render(<MemoryRouter><LocalTlsCard /></MemoryRouter>);
    expect(await screen.findByText('notConfigured')).toBeTruthy();
  });

  it('nicht konfiguriert: Laeufe gesperrt', async () => {
    renderCard({ configured: false });
    const renew = (await screen.findByText('actions.renew')).closest('button') as HTMLButtonElement;
    const dns = screen.getByText('actions.updateDns').closest('button') as HTMLButtonElement;
    expect(renew.disabled).toBe(true);
    expect(dns.disabled).toBe(true);
  });

  it('laufender Lauf wird angezeigt', async () => {
    renderCard({ running: true });
    expect(await screen.findByText('running')).toBeTruthy();
  });

  it.each([
    [true, 'served.yes'], [false, 'served.no'], [null, 'served.unknown'],
  ])('Ausgeliefert von nginx (%s)', async (value, key) => {
    renderCard({ served_matches: value as boolean | null });
    const el = await screen.findByTestId('served');
    expect(el.textContent).toContain(key);
  });

  it('bekannte Gruende werden uebersetzt, unbekannte roh gezeigt', async () => {
    renderCard({ last_renew_reason: 'installed, nginx is not serving it yet' });
    expect(await screen.findByText('(reasons.notServed)', { exact: false })).toBeTruthy();
  });
});
