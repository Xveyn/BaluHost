import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { usePluginsSummary } from '../../hooks/usePluginsSummary';
import * as pluginsApi from '../../api/plugins';
import type { PluginInfo } from '../../api/plugins';

vi.mock('../../api/plugins');
const api = vi.mocked(pluginsApi);

function plugin(overrides: Partial<PluginInfo>): PluginInfo {
  return {
    name: 'p',
    version: '1.0.0',
    display_name: 'P',
    description: '',
    author: '',
    category: '',
    required_permissions: [],
    dangerous_permissions: [],
    is_enabled: true,
    has_ui: false,
    has_routes: false,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('usePluginsSummary', () => {
  it('derives the summary from the plugin list', async () => {
    const plugins = [
      plugin({ name: 'a', is_enabled: true }),
      plugin({ name: 'b', is_enabled: false }),
      plugin({ name: 'c', is_enabled: true, error: 'boom' }),
    ];
    api.listPlugins.mockResolvedValue({ plugins, total: plugins.length });

    const { result } = renderHook(() => usePluginsSummary({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.summary).toEqual({ total: 3, enabled: 2, disabled: 1, withErrors: 1 });
    expect(result.current.error).toBeNull();
  });

  it('treats a 403 as an empty (silent) result — no error surfaced', async () => {
    api.listPlugins.mockRejectedValue({ response: { status: 403 } });

    const { result } = renderHook(() => usePluginsSummary({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.plugins).toEqual([]);
    expect(result.current.summary.total).toBe(0);
    expect(result.current.error).toBeNull();
  });

  it('surfaces a non-403 error as a string', async () => {
    api.listPlugins.mockRejectedValue(new Error('plugins boom'));

    const { result } = renderHook(() => usePluginsSummary({ refreshInterval: 0 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('plugins boom'));
  });

  it('does not fetch when disabled', () => {
    api.listPlugins.mockResolvedValue({ plugins: [], total: 0 });

    const { result } = renderHook(() => usePluginsSummary({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(api.listPlugins).not.toHaveBeenCalled();
  });
});
