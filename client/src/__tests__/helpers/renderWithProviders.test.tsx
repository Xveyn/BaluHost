/**
 * The test helper needs tests of its own: everything built on top of it
 * inherits its bugs, and a helper that silently renders without translations
 * would make every assertion below it meaningless.
 */
import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';

import { renderWithProviders } from './renderWithProviders';
import { useAuth } from '../../contexts/AuthContext';
import { apiClient } from '../../lib/api';

function Translated() {
  const { t } = useTranslation('common');
  return <p>{t('buttons.cancel')}</p>;
}

function WhoAmI() {
  const { user, loading } = useAuth();
  return <p>{loading ? 'lädt' : (user?.username ?? 'anonym')}</p>;
}

function CallsAxios() {
  const [seen, setSeen] = useState('');
  useEffect(() => {
    apiClient
      .get('/api/system/info')
      .then((r) => setSeen(String((r.data as { hostname: string }).hostname)))
      // A component that swallows its own errors — the "misses" test renders
      // this one WITHOUT a stub on purpose, and an uncaught rejection there
      // would be noise from the test, not a finding about the helper.
      .catch(() => setSeen('fehlgeschlagen'));
  }, []);
  return <p>{seen}</p>;
}

function CallsFetch() {
  const [seen, setSeen] = useState('');
  useEffect(() => {
    fetch('/api/raw/thing')
      .then((r) => r.json())
      .then((d) => setSeen(String((d as { value: string }).value)));
  }, []);
  return <p>{seen}</p>;
}

describe('translations', () => {
  it('renders the real German string, not the key', async () => {
    renderWithProviders(<Translated />);

    // The point of the helper: this assertion fails if the translation is
    // missing, whereas asserting on 'buttons.cancel' would pass either way.
    const rendered = await screen.findByText(/./);
    expect(rendered.textContent).not.toBe('buttons.cancel');
    expect(rendered.textContent).toBeTruthy();
  });

  it('switches the whole tree to English on request', async () => {
    const { unmount } = renderWithProviders(<Translated />, { language: 'de' });
    const german = (await screen.findByText(/./)).textContent;
    unmount();

    renderWithProviders(<Translated />, { language: 'en' });
    const english = (await screen.findByText(/./)).textContent;

    expect(english).not.toBe(german);
  });
});

describe('auth', () => {
  it('signs the given user in, through the provider\'s own /api/auth/me call', async () => {
    renderWithProviders(<WhoAmI />, { auth: { username: 'sven' } });

    expect(await screen.findByText('sven')).toBeInTheDocument();
  });

  it('stays anonymous without the auth option', async () => {
    renderWithProviders(<WhoAmI />);

    expect(await screen.findByText('anonym')).toBeInTheDocument();
  });
});

describe('the api stub', () => {
  it('answers axios requests through the real interceptor chain', async () => {
    renderWithProviders(<CallsAxios />, {
      api: { '/api/system/info': { hostname: 'BaluNode' } },
    });

    expect(await screen.findByText('BaluNode')).toBeInTheDocument();
  });

  it('answers raw fetch too — AuthProvider and the upload client use it', async () => {
    renderWithProviders(<CallsFetch />, {
      api: { '/api/raw/thing': { value: 'served' } },
    });

    expect(await screen.findByText('served')).toBeInTheDocument();
  });

  it('records what was asked for, including the misses', async () => {
    const { api } = renderWithProviders(<CallsAxios />, { api: {} });

    await waitFor(() => expect(api.missed()).toHaveLength(1));
    expect(api.missed()[0]).toMatchObject({ method: 'GET', path: '/api/system/info' });
  });

  it('lets a test inspect the request body it caused', async () => {
    const { api, user } = renderWithProviders(
      <button onClick={() => void apiClient.post('/api/echo', { hello: 'world' })}>Senden</button>,
      { api: { 'POST /api/echo': { ok: true } } },
    );

    await user.click(screen.getByRole('button', { name: 'Senden' }));

    await waitFor(() => expect(api.callsTo('/api/echo', 'POST')).toHaveLength(1));
    expect(api.callsTo('/api/echo', 'POST')[0].body).toEqual({ hello: 'world' });
  });

  it('lets the caller override the auth route to simulate a rejected token', async () => {
    renderWithProviders(<WhoAmI />, {
      auth: { username: 'sven' },
      api: { '/api/auth/me': { status: 401, body: { detail: 'expired' } } },
    });

    expect(await screen.findByText('anonym')).toBeInTheDocument();
  });
});
