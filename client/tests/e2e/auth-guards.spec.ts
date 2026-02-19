import { test, expect } from './fixtures/auth.fixture';

test.describe('Auth Guards', () => {
  test('unauthenticated user on / is redirected to /login', async ({ unauthenticatedPage: page }) => {
    await page.goto('/');

    // Should redirect to login
    await page.waitForURL('**/login', { timeout: 10000 });
    await expect(page.locator('#username')).toBeVisible();
  });

  test('unauthenticated user on /files is redirected to /login', async ({ unauthenticatedPage: page }) => {
    await page.goto('/files');

    // Should redirect to login
    await page.waitForURL('**/login', { timeout: 10000 });
    await expect(page.locator('#username')).toBeVisible();
  });

  test('regular user on /users (admin-only) is redirected to /', async ({ regularUserPage: page }) => {
    await page.goto('/users');

    // Non-admin should be redirected to dashboard (/)
    await page.waitForURL(/\/$/, { timeout: 10000 });
    // Should NOT see user management page
    await expect(page.locator('#username')).not.toBeVisible();
  });

  test('authenticated user on /login is redirected to /', async ({ authenticatedPage: page }) => {
    await page.goto('/login');

    // Already logged in - should redirect away from login
    await page.waitForURL(/\/$/, { timeout: 10000 });
    await expect(page.locator('#username')).not.toBeVisible();
  });
});
