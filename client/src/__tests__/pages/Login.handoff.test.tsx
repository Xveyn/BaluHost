import { StrictMode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Login from '../../pages/Login';

const auth = vi.hoisted(() => ({
  login: vi.fn(),
  user: null as { id: number; username: string } | null,
}));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('../../contexts/VersionContext', () => ({
  useVersion: () => ({ version: '1', loading: false }),
}));
vi.mock('../../lib/localApi', () => ({ localApi: { isAvailable: vi.fn(async () => false) } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, string>) => (o ? `${k}|${o.username}|${o.current}` : k),
  }),
}));

const fetchMock = vi.fn();
const target = { id: 2, username: 'bob' };

function renderLogin() {
  return render(
    <StrictMode>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </StrictMode>,
  );
}

beforeEach(() => {
  auth.login.mockClear();
  auth.user = null;
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => {
    if (String(url).includes('/handoff/redeem')) {
      return new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer', user: target }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    return new Response(JSON.stringify({}), { status: 200, headers: { 'content-type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  window.history.pushState({}, '', '/login#handoff=CODE123');
});

const redeemCalls = () => fetchMock.mock.calls.filter((c) => String(c[0]).includes('/handoff/redeem'));

describe('Login Handoff', () => {
  it('StrictMode: genau ein Redeem, Fragment vorher entfernt, Auto-Login ohne Session', async () => {
    renderLogin();
    await waitFor(() => expect(auth.login).toHaveBeenCalledWith(target, 'tok'));
    expect(redeemCalls()).toHaveLength(1);
    expect(JSON.parse(redeemCalls()[0][1].body)).toEqual({ code: 'CODE123' });
    expect(window.location.hash).toBe('');
  });

  it('gleicher Nutzer: Auto-Login ohne Rueckfrage', async () => {
    auth.user = { id: 2, username: 'bob' };
    renderLogin();
    await waitFor(() => expect(auth.login).toHaveBeenCalledWith(target, 'tok'));
    expect(screen.queryByText('handoff.confirmTitle')).not.toBeInTheDocument();
  });

  it('anderer Nutzer: Rueckfrage, login erst nach Bestaetigung', async () => {
    auth.user = { id: 1, username: 'alice' };
    renderLogin();
    await screen.findByText('handoff.confirmText|bob|alice');
    expect(redeemCalls()).toHaveLength(1);
    expect(auth.login).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /confirm|bestät|ok/i }));
    await waitFor(() => expect(auth.login).toHaveBeenCalledWith(target, 'tok'));
  });

  it('anderer Nutzer: Abbrechen verwirft den Token', async () => {
    auth.user = { id: 1, username: 'alice' };
    renderLogin();
    await screen.findByText('handoff.confirmText|bob|alice');
    fireEvent.click(screen.getByRole('button', { name: /cancel|abbrech/i }));
    await waitFor(() => expect(screen.queryByText('handoff.confirmText|bob|alice')).not.toBeInTheDocument());
    expect(auth.login).not.toHaveBeenCalled();
  });
});
