import { test, expect } from './fixtures/auth.fixture';

const json = (body: unknown) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

test.describe('Dev Impersonation', () => {
  test('admin can impersonate a user and return', async ({ authenticatedContext }) => {
    // Force English so we can assert on UI strings ("Switch to user", "Back to admin").
    await authenticatedContext.addInitScript(() => {
      try {
        window.localStorage.setItem('baluhost-language', 'en');
      } catch {
        /* ignore */
      }
    });

    type MockUser = { id: number; username: string; email: string; role: string };
    const adminUser: MockUser = {
      id: 1,
      username: 'admin',
      email: 'admin@baluhost.local',
      role: 'admin',
    };
    const targetUser: MockUser = {
      id: 2,
      username: 'testuser',
      email: 'user@baluhost.local',
      role: 'user',
    };

    // Track which user /api/auth/me should return. Starts as admin, becomes
    // target after impersonation, then flips back when we click "Back to admin".
    let currentUser: MockUser = adminUser;

    // Overrides registered after the fixture's core routes — Playwright runs
    // the most recently added matcher first, so these take precedence.
    await authenticatedContext.route('**/api/auth/me', (r) =>
      r.fulfill(json({ user: currentUser })),
    );

    await authenticatedContext.route('**/api/users/', (r) =>
      r.fulfill(
        json({
          users: [
            { id: 1, username: 'admin', role: 'admin' },
            { id: 2, username: 'testuser', role: 'user' },
          ],
          total: 2,
          active: 2,
          inactive: 0,
          admins: 1,
        }),
      ),
    );

    await authenticatedContext.route('**/api/auth/dev/impersonate/2', (r) => {
      currentUser = targetUser;
      return r.fulfill(
        json({
          access_token: 'imp-token-for-testuser',
          token_type: 'bearer',
          user: targetUser,
        }),
      );
    });

    const page = await authenticatedContext.newPage();
    await page.goto('/');

    // Topbar user menu button shows the current username.
    const userMenuButton = page.getByRole('button', { name: /admin/i }).first();
    await expect(userMenuButton).toBeVisible({ timeout: 10000 });
    await userMenuButton.click();

    // Hover "Switch to user" to reveal the submenu and trigger the users fetch.
    await page.getByText(/switch to user/i).hover();

    // Click the target user row.
    await page.getByRole('button', { name: /testuser/i }).click();

    // The banner (role="alert") should now announce the impersonated user.
    const banner = page.getByRole('alert');
    await expect(banner).toContainText(/testuser/i);

    // Prep /api/auth/me for the "Back to admin" round-trip.
    currentUser = adminUser;

    await page.getByRole('button', { name: /back to admin/i }).click();

    // Banner disappears once impersonation ends.
    await expect(page.getByRole('alert')).toHaveCount(0);
  });
});
