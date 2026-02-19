import { test, expect } from './fixtures/auth.fixture';
import {
  MOCK_LOGIN_SUCCESS,
  MOCK_LOGIN_FAILURE,
  MOCK_LOGIN_2FA_REQUIRED,
  MOCK_2FA_SUCCESS,
  MOCK_HEALTH,
  MOCK_SYSTEM_MODE,
  MOCK_VERSION,
  MOCK_ADMIN_USER,
  MOCK_SYSTEM_INFO,
  MOCK_STORAGE_AGGREGATED,
  MOCK_TELEMETRY_HISTORY,
  MOCK_SMART_STATUS,
  MOCK_SMART_MODE,
  MOCK_RAID_STATUS,
  MOCK_SCHEDULERS,
  MOCK_ADMIN_DEBUG,
  MOCK_FAN_STATUS,
  MOCK_POWER_STATUS,
  MOCK_PLUGINS,
  MOCK_PLUGINS_MANIFEST,
  MOCK_NETWORK_CURRENT,
  MOCK_DEVICES_ALL,
  MOCK_FILE_ACCESS_LOGS,
  MOCK_TAPO_POWER_HISTORY,
} from './fixtures/mock-data';

function json(data: unknown) {
  return { status: 200, contentType: 'application/json', body: JSON.stringify(data) };
}

test.describe('Login Page', () => {
  test('shows login form with username, password and submit button', async ({ unauthenticatedPage: page }) => {
    await page.goto('/login');

    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toContainText('Access System');
  });

  test('successful login redirects to dashboard', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Mock health + system mode for app shell
    await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));
    await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));
    await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
    // Before login: no token, so /api/auth/me returns 401
    await context.route('**/api/auth/me', (r) => r.fulfill(json(MOCK_ADMIN_USER)));
    // Mock login endpoint
    await context.route('**/api/auth/login', (r) => r.fulfill(json(MOCK_LOGIN_SUCCESS)));
    // Mock plugins
    await context.route('**/api/plugins', (r) => r.fulfill(json(MOCK_PLUGINS)));
    await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json(MOCK_PLUGINS_MANIFEST)));
    // Mock dashboard endpoints (needed after redirect)
    await context.route('**/api/system/info', (r) => r.fulfill(json(MOCK_SYSTEM_INFO)));
    await context.route('**/api/system/storage/aggregated', (r) => r.fulfill(json(MOCK_STORAGE_AGGREGATED)));
    await context.route('**/api/system/telemetry/history', (r) => r.fulfill(json(MOCK_TELEMETRY_HISTORY)));
    await context.route('**/api/system/smart/status', (r) => r.fulfill(json(MOCK_SMART_STATUS)));
    await context.route('**/api/system/smart/mode', (r) => r.fulfill(json(MOCK_SMART_MODE)));
    await context.route('**/api/system/raid/status', (r) => r.fulfill(json(MOCK_RAID_STATUS)));
    await context.route('**/api/schedulers', (r) => r.fulfill(json(MOCK_SCHEDULERS)));
    await context.route('**/api/admin/debug', (r) => r.fulfill(json(MOCK_ADMIN_DEBUG)));
    await context.route('**/api/fans/status', (r) => r.fulfill(json(MOCK_FAN_STATUS)));
    await context.route('**/api/power/status', (r) => r.fulfill(json(MOCK_POWER_STATUS)));
    await context.route('**/api/monitoring/network/current', (r) => r.fulfill(json(MOCK_NETWORK_CURRENT)));
    await context.route('**/api/devices/all', (r) => r.fulfill(json(MOCK_DEVICES_ALL)));
    await context.route('**/api/logging/file-access**', (r) => r.fulfill(json(MOCK_FILE_ACCESS_LOGS)));
    await context.route('**/api/tapo/power/history**', (r) => r.fulfill(json(MOCK_TAPO_POWER_HISTORY)));

    const page = await context.newPage();
    await page.goto('/login');

    await page.fill('#username', 'admin');
    await page.fill('#password', 'DevMode2024');
    await page.click('button[type="submit"]');

    // Should redirect to dashboard (URL becomes /)
    await page.waitForURL('**/');
    // Dashboard should be visible - verify we're no longer on login
    await expect(page.locator('#username')).not.toBeVisible();

    await context.close();
  });

  test('invalid credentials shows error message', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));
    await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));
    await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
    await context.route('**/api/auth/me', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) }));
    await context.route('**/api/auth/login', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify(MOCK_LOGIN_FAILURE) }));
    await context.route('**/api/plugins', (r) => r.fulfill(json(MOCK_PLUGINS)));
    await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json(MOCK_PLUGINS_MANIFEST)));

    const page = await context.newPage();
    await page.goto('/login');

    await page.fill('#username', 'admin');
    await page.fill('#password', 'wrongpassword');
    await page.click('button[type="submit"]');

    // Error message should appear
    const errorEl = page.locator('.text-rose-200');
    await expect(errorEl).toBeVisible({ timeout: 5000 });
    await expect(errorEl).toContainText('Invalid username or password');

    await context.close();
  });

  test('2FA flow: shows code input and verifies successfully', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));
    await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));
    await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
    await context.route('**/api/auth/me', (r) => r.fulfill(json(MOCK_ADMIN_USER)));
    await context.route('**/api/auth/login', (r) => r.fulfill(json(MOCK_LOGIN_2FA_REQUIRED)));
    await context.route('**/api/auth/verify-2fa', (r) => r.fulfill(json(MOCK_2FA_SUCCESS)));
    await context.route('**/api/plugins', (r) => r.fulfill(json(MOCK_PLUGINS)));
    await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json(MOCK_PLUGINS_MANIFEST)));
    // Dashboard endpoints for after login
    await context.route('**/api/system/info', (r) => r.fulfill(json(MOCK_SYSTEM_INFO)));
    await context.route('**/api/system/storage/aggregated', (r) => r.fulfill(json(MOCK_STORAGE_AGGREGATED)));
    await context.route('**/api/system/telemetry/history', (r) => r.fulfill(json(MOCK_TELEMETRY_HISTORY)));
    await context.route('**/api/system/smart/status', (r) => r.fulfill(json(MOCK_SMART_STATUS)));
    await context.route('**/api/system/smart/mode', (r) => r.fulfill(json(MOCK_SMART_MODE)));
    await context.route('**/api/system/raid/status', (r) => r.fulfill(json(MOCK_RAID_STATUS)));
    await context.route('**/api/schedulers', (r) => r.fulfill(json(MOCK_SCHEDULERS)));
    await context.route('**/api/admin/debug', (r) => r.fulfill(json(MOCK_ADMIN_DEBUG)));
    await context.route('**/api/fans/status', (r) => r.fulfill(json(MOCK_FAN_STATUS)));
    await context.route('**/api/power/status', (r) => r.fulfill(json(MOCK_POWER_STATUS)));
    await context.route('**/api/monitoring/network/current', (r) => r.fulfill(json(MOCK_NETWORK_CURRENT)));
    await context.route('**/api/devices/all', (r) => r.fulfill(json(MOCK_DEVICES_ALL)));
    await context.route('**/api/logging/file-access**', (r) => r.fulfill(json(MOCK_FILE_ACCESS_LOGS)));
    await context.route('**/api/tapo/power/history**', (r) => r.fulfill(json(MOCK_TAPO_POWER_HISTORY)));

    const page = await context.newPage();
    await page.goto('/login');

    // Submit login - should trigger 2FA
    await page.fill('#username', 'admin');
    await page.fill('#password', 'DevMode2024');
    await page.click('button[type="submit"]');

    // 2FA code input should appear
    await expect(page.locator('#totp-code')).toBeVisible({ timeout: 5000 });

    // Enter 2FA code and verify
    await page.fill('#totp-code', '123456');
    await page.click('button[type="submit"]');

    // Should redirect to dashboard
    await page.waitForURL('**/');
    await expect(page.locator('#totp-code')).not.toBeVisible();

    await context.close();
  });

  test('2FA "Back to login" returns to normal login form', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));
    await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));
    await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
    await context.route('**/api/auth/me', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) }));
    await context.route('**/api/auth/login', (r) => r.fulfill(json(MOCK_LOGIN_2FA_REQUIRED)));
    await context.route('**/api/plugins', (r) => r.fulfill(json(MOCK_PLUGINS)));
    await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json(MOCK_PLUGINS_MANIFEST)));

    const page = await context.newPage();
    await page.goto('/login');

    // Submit login to trigger 2FA
    await page.fill('#username', 'admin');
    await page.fill('#password', 'DevMode2024');
    await page.click('button[type="submit"]');

    // Wait for 2FA view
    await expect(page.locator('#totp-code')).toBeVisible({ timeout: 5000 });

    // Click "Back to login"
    await page.click('text=Back to login');

    // Should see the normal login form again
    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('#totp-code')).not.toBeVisible();

    await context.close();
  });
});
