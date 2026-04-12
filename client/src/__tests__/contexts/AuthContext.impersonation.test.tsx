import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';

vi.mock('../../api/authDev', () => ({
  impersonateUser: vi.fn(),
}));

vi.mock('../../lib/api', async (orig) => ({
  ...(await orig<typeof import('../../lib/api')>()),
  buildApiUrl: (p: string) => p,
}));

import { impersonateUser } from '../../api/authDev';

const adminUser = { id: 1, username: 'admin', role: 'admin' as const };
const targetUser = { id: 2, username: 'alice', role: 'user' as const };

function TestConsumer({ captureRef }: { captureRef: (ctx: ReturnType<typeof useAuth>) => void }) {
  const ctx = useAuth();
  captureRef(ctx);
  return null;
}

describe('AuthContext impersonation', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    localStorage.setItem('token', 'admin-token');
    global.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ user: adminUser }), { status: 200 }),
      ),
    ) as any;
  });

  it('stores origin token and swaps to impersonation token', async () => {
    (impersonateUser as any).mockResolvedValue({
      access_token: 'imp-token',
      token_type: 'bearer',
      user: targetUser,
    });

    let ctx!: ReturnType<typeof useAuth>;
    render(
      <AuthProvider>
        <TestConsumer captureRef={(c) => (ctx = c)} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx.user?.username).toBe('admin'));

    await act(async () => {
      await ctx.impersonate(targetUser.id);
    });

    expect(sessionStorage.getItem('impersonation_origin_token')).toBe('admin-token');
    expect(sessionStorage.getItem('impersonation_origin_username')).toBe('admin');
    expect(localStorage.getItem('token')).toBe('imp-token');
    expect(ctx.isImpersonating).toBe(true);
    expect(ctx.impersonationOrigin).toBe('admin');
    expect(ctx.user?.username).toBe('alice');
  });

  it('endImpersonation restores the admin token', async () => {
    (impersonateUser as any).mockResolvedValue({
      access_token: 'imp-token',
      token_type: 'bearer',
      user: targetUser,
    });

    let ctx!: ReturnType<typeof useAuth>;
    render(
      <AuthProvider>
        <TestConsumer captureRef={(c) => (ctx = c)} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx.user?.username).toBe('admin'));

    await act(async () => {
      await ctx.impersonate(targetUser.id);
    });
    expect(ctx.isImpersonating).toBe(true);

    (global.fetch as any).mockImplementationOnce(() =>
      Promise.resolve(new Response(JSON.stringify({ user: adminUser }), { status: 200 })),
    );

    await act(async () => {
      ctx.endImpersonation();
    });

    await waitFor(() => expect(ctx.isImpersonating).toBe(false));
    expect(localStorage.getItem('token')).toBe('admin-token');
    expect(sessionStorage.getItem('impersonation_origin_token')).toBeNull();
    expect(ctx.user?.username).toBe('admin');
  });
});
