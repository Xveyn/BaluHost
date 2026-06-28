import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PluginDocumentation from '../../../components/plugins/PluginDocumentation';
import type { PermissionInfo, ScopeInfo } from '../../../api/plugins';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { returnObjects?: boolean }) =>
      opts?.returnObjects ? {} : key,
  }),
}));

vi.mock('../../../contexts/VersionContext', () => ({
  useFormattedVersion: () => 'BaluHost v1.37.0',
}));

const SCOPES: ScopeInfo[] = [
  { key: 'read:system-info', tier: 'frontend', dangerous: false },
  { key: 'read:storage', tier: 'frontend', dangerous: false },
  { key: 'read:power', tier: 'frontend', dangerous: false },
  { key: 'storage', tier: 'frontend', dangerous: false },
  { key: 'core.system_metrics', tier: 'backend', dangerous: false },
  { key: 'core.notify', tier: 'backend', dangerous: false },
];

const PERMISSIONS: PermissionInfo[] = [
  { name: 'file:read', value: 'file:read', dangerous: false, description: 'Read files' },
  { name: 'file:write', value: 'file:write', dangerous: true, description: 'Write files' },
];

describe('PluginDocumentation two-tier', () => {
  it('renders both trust-tier cards', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={SCOPES} />);
    expect(screen.getAllByText('tiers.bundled.label').length).toBeGreaterThan(0);
    expect(screen.getAllByText('tiers.external.label').length).toBeGreaterThan(0);
  });

  it('renders every catalog scope grouped under its tier heading', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={SCOPES} />);
    for (const scope of SCOPES) {
      expect(screen.getAllByText(scope.key).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('scopeTiers.frontend')).toBeInTheDocument();
    expect(screen.getByText('scopeTiers.backend')).toBeInTheDocument();
  });

  it('shows the unavailable note when the scope catalog is empty', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={[]} />);
    expect(screen.getByText('tiers.scopesUnavailable')).toBeInTheDocument();
    expect(screen.queryByText('scopeTiers.frontend')).not.toBeInTheDocument();
  });

  it('renders the condensed bundled permission reference', () => {
    render(<PluginDocumentation permissions={PERMISSIONS} scopeCatalog={SCOPES} />);
    expect(screen.getByText('file:read')).toBeInTheDocument();
    expect(screen.getAllByText('file:write').length).toBeGreaterThan(0);
  });
});
