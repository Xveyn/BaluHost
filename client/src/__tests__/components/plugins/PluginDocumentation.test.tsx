/**
 * #288: i18next treats ':' as its namespace separator, so
 * `t(\`permissionDescriptions.${perm.value}\`)` mis-parses keys like
 * "file:read" and silently falls back to the English API description for
 * German users. `returnObjects: true` alone does NOT fix this -- i18next
 * re-parses each nested key against nsSeparator while building the returned
 * object too, so `t('scopeDescriptions', { returnObjects: true })` with a
 * key like "read:system-info" still collapses to just "system-info" (the
 * whole {label, description} object replaced by a string). Both lookups
 * need `nsSeparator: false` as well. This must be tested against a REAL
 * i18next instance (unlike sibling component tests, which mock
 * react-i18next's t() entirely) -- a mocked t() never reproduces either bug.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18next from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import PluginDocumentation from '../../../components/plugins/PluginDocumentation';
import type { PermissionInfo, ScopeInfo } from '../../../api/plugins';

vi.mock('../../../contexts/VersionContext', () => ({
  useFormattedVersion: () => 'BaluHost v1.0.0',
}));

const PERMISSIONS: PermissionInfo[] = [
  { name: 'Read files', value: 'file:read', dangerous: false, description: 'Read files from storage' },
];

const SCOPE_CATALOG: ScopeInfo[] = [
  { key: 'read:system-info', tier: 'backend', dangerous: false },
];

async function makeI18n() {
  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    lng: 'de',
    fallbackLng: 'de',
    ns: ['plugins'],
    defaultNS: 'plugins',
    resources: {
      de: {
        plugins: {
          categories: { file: 'Datei' },
          docs: { permissions: 'Berechtigungen', available: 'verfügbar', permissionsDescription: '' },
          permissionDescriptions: { 'file:read': 'Dateien lesen (DE)' },
          scopeDescriptions: {
            'read:system-info': { label: 'System-Info lesen (DE)', description: 'Liest System-Informationen (DE)' },
          },
        },
      },
    },
    interpolation: { escapeValue: false },
  });
  return instance;
}

describe('PluginDocumentation separator-safe i18n lookups (#288)', () => {
  it('shows the localized description for a colon-containing permission key, not the English API fallback', async () => {
    const i18n = await makeI18n();
    render(
      <I18nextProvider i18n={i18n}>
        <PluginDocumentation permissions={PERMISSIONS} scopeCatalog={[]} />
      </I18nextProvider>
    );

    expect(screen.getByText('Dateien lesen (DE)')).toBeTruthy();
    expect(screen.queryByText('Read files from storage')).toBeNull();
  });

  it('shows the localized label and description for a colon-containing scope key, not the raw key', async () => {
    const i18n = await makeI18n();
    render(
      <I18nextProvider i18n={i18n}>
        <PluginDocumentation permissions={[]} scopeCatalog={SCOPE_CATALOG} />
      </I18nextProvider>
    );

    expect(screen.getByText('System-Info lesen (DE)')).toBeTruthy();
    expect(screen.getByText('Liest System-Informationen (DE)')).toBeTruthy();
  });
});
