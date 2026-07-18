import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useLayoutNav } from '../../hooks/useLayoutNav';

const authState = vi.hoisted(() => ({ isAdmin: true }));
const featureState = vi.hoisted(() => ({ isPi: false }));
const pluginState = vi.hoisted(() => ({
  pluginNavItems: [] as Array<{ path: string; label: string; admin_only: boolean }>,
}));

vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => authState }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: () => pluginState }));
vi.mock('../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../lib/pluginI18n', () => ({
  resolvePluginString: (_t: unknown, _k: string, fallback: string) => fallback,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeEach(() => {
  authState.isAdmin = true;
  featureState.isPi = false;
  pluginState.pluginNavItems = [];
});

describe('useLayoutNav', () => {
  it('Admin: 16 Items, adminStartIndex zeigt aufs erste Admin-Item', () => {
    const { result } = renderHook(() => useLayoutNav());
    expect(result.current.allNavItems).toHaveLength(16);
    // 9 Nicht-Admin-Items vorweg: dashboard, files, shares, system, devices,
    // smart-devices, settings, manual, cloud-import
    expect(result.current.adminStartIndex).toBe(9);
    expect(result.current.allNavItems[9].path).toBe('/admin/system-control');
    expect(result.current.allNavItems[9].adminOnly).toBe(true);
  });

  it('User: nur die 9 Nicht-Admin-Items, adminStartIndex -1', () => {
    authState.isAdmin = false;
    const { result } = renderHook(() => useLayoutNav());
    expect(result.current.allNavItems).toHaveLength(9);
    expect(result.current.allNavItems.every((i) => !i.adminOnly)).toBe(true);
    expect(result.current.adminStartIndex).toBe(-1);
  });

  it('Pi: nur / und /system, keine Plugins, adminStartIndex -1', () => {
    featureState.isPi = true;
    pluginState.pluginNavItems = [{ path: 'x', label: 'X', admin_only: false }];
    const { result } = renderHook(() => useLayoutNav());
    expect(result.current.allNavItems.map((i) => i.path)).toEqual(['/', '/system']);
    expect(result.current.adminStartIndex).toBe(-1);
  });

  it('Plugin-Items werden angehängt; admin_only für User gefiltert', () => {
    authState.isAdmin = false;
    pluginState.pluginNavItems = [
      { path: 'demo', label: 'Demo', admin_only: false },
      { path: 'secret', label: 'Secret', admin_only: true },
    ];
    const { result } = renderHook(() => useLayoutNav());
    const last = result.current.allNavItems[result.current.allNavItems.length - 1];
    expect(last).toMatchObject({ path: '/plugins/demo', label: 'Demo', isPlugin: true });
    expect(result.current.allNavItems.some((i) => i.label === 'Secret')).toBe(false);
  });
});
