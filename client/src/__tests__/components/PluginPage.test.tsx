import { describe, it, expect, vi, beforeEach } from 'vitest';
// ?raw (typed by vite/client) instead of node:fs - the test TS project that
// `npm run build` checks has no Node types.
import pluginPageSource from '../../components/PluginPage.tsx?raw';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { PluginUIInfo } from '../../api/plugins';
import en from '../../i18n/locales/en/plugins.json';
import de from '../../i18n/locales/de/plugins.json';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'admin' } }) }));

let enabledPlugins: PluginUIInfo[] = [];
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => ({ enabledPlugins }) }));
vi.mock('../../components/plugins/PluginSandboxHost', () => ({
  default: ({ pluginName }: { pluginName: string }) => <div data-testid="sandbox-host">{pluginName}</div>,
}));

import PluginPage from '../../components/PluginPage';

function plugin(overrides: Partial<PluginUIInfo>): PluginUIInfo {
  return {
    name: 'demo', display_name: 'Demo', nav_items: [], menu_items: [],
    bundle_path: 'ui/bundle.js', dashboard_widgets: [], granted_api_scopes: [],
    ...overrides,
  };
}

function renderAt(name: string) {
  return render(
    <MemoryRouter initialEntries={[`/plugins/${name}`]}>
      <Routes>
        <Route path="/plugins/:pluginName/*" element={<PluginPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PluginPage (#454)', () => {
  beforeEach(() => { enabledPlugins = []; });

  it('does not frame a sandbox host for a plugin without its own page', () => {
    enabledPlugins = [plugin({ name: 'audio_control', display_name: 'Audio', has_page: false })];
    renderAt('audio_control');

    expect(screen.queryByTestId('sandbox-host')).not.toBeInTheDocument();
    expect(screen.getByText('page.noOwnPageTitle')).toBeInTheDocument();
    expect(screen.getByText('page.goToDashboard')).toBeInTheDocument();
  });

  it('frames the sandbox host when the plugin has a page', () => {
    enabledPlugins = [plugin({ name: 'optical_drive', has_page: true })];
    renderAt('optical_drive');

    expect(screen.getByTestId('sandbox-host')).toHaveTextContent('optical_drive');
  });

  it('keeps the old behaviour when the backend does not send has_page', () => {
    enabledPlugins = [plugin({ name: 'legacy' })];
    renderAt('legacy');

    expect(screen.getByTestId('sandbox-host')).toBeInTheDocument();
  });

  it('shows translated keys, not raw ones, for a plugin that is not enabled (#674)', () => {
    renderAt('ghost_plugin');

    expect(screen.queryByTestId('sandbox-host')).not.toBeInTheDocument();
    expect(screen.getByText('page.notFoundTitle')).toBeInTheDocument();
    expect(screen.getByText('page.notFoundDesc')).toBeInTheDocument();
    expect(screen.getByText('page.goToDashboard')).toBeInTheDocument();
    // The old branch hardcoded an English sentence next to two raw keys.
    expect(screen.queryByText(/is not enabled or does not exist/)).not.toBeInTheDocument();
  });

  it('uses only keys that exist in both plugins.json locales (#674)', () => {
    // The mock echoes keys, so a missing key looks fine in every render test.
    // Read the component source and check each literal t('...') key.
    const keys = [...pluginPageSource.matchAll(/\bt\(\s*'([^']+)'/g)].map((m) => m[1]);
    expect(keys.length).toBeGreaterThan(0);

    const lookup = (locale: Record<string, unknown>, key: string) =>
      key.split('.').reduce<unknown>(
        (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
        locale,
      );
    for (const locale of [en, de]) {
      const missing = keys.filter((k) => typeof lookup(locale, k) !== 'string');
      expect(missing).toEqual([]);
    }
    for (const locale of [en, de]) {
      expect(locale.page.notFoundDesc).toContain('{{name}}');
    }
  });

  it('ships the new strings in both locales, with the name placeholder', () => {
    // The react-i18next mock echoes keys, so only the JSON itself proves they exist.
    for (const locale of [en, de]) {
      expect(locale.page.noOwnPageTitle).toBeTruthy();
      expect(locale.page.goToDashboard).toBeTruthy();
      expect(locale.page.noOwnPageDesc).toContain('{{name}}');
    }
  });
});
