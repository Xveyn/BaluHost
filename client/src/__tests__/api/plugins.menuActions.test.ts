import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: { post: vi.fn() },
}));

import { apiClient } from '../../lib/api';
import { runPluginMenuAction } from '../../api/plugins';

describe('runPluginMenuAction', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts to the namespaced menu-action endpoint', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ok: true, message_key: 'menu_gaming_mode_started', message_text: 'Gaming mode started' },
    });

    const result = await runPluginMenuAction('steam_gaming', 'gaming_mode');

    expect(apiClient.post).toHaveBeenCalledWith('/api/plugins/steam_gaming/menu-actions/gaming_mode');
    expect(result.ok).toBe(true);
    expect(result.message_key).toBe('menu_gaming_mode_started');
  });

  it('returns the failure result unchanged', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { ok: false, message_key: 'menu_steam_failed', message_text: 'Steam did not start' },
    });

    expect((await runPluginMenuAction('steam_gaming', 'gaming_mode')).ok).toBe(false);
  });
});
