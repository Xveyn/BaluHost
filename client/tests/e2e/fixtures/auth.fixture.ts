/**
 * Shared Playwright fixtures for authenticated and unauthenticated test contexts.
 *
 * Usage:
 *   import { test, expect } from './fixtures/auth.fixture';
 *   test('my test', async ({ authenticatedPage }) => { ... });
 */
import { test as base, expect, type Page, type BrowserContext } from '@playwright/test';
import {
  MOCK_ADMIN_USER,
  MOCK_REGULAR_USER,
  MOCK_HEALTH,
  MOCK_SYSTEM_INFO,
  MOCK_STORAGE_AGGREGATED,
  MOCK_TELEMETRY_HISTORY,
  MOCK_SMART_STATUS,
  MOCK_SMART_MODE,
  MOCK_RAID_STATUS,
  MOCK_SCHEDULERS,
  MOCK_VERSION,
  MOCK_FAN_STATUS,
  MOCK_POWER_STATUS,
  MOCK_ADMIN_DEBUG,
  MOCK_SYSTEM_MODE,
  MOCK_PLUGINS,
  MOCK_PLUGINS_MANIFEST,
  MOCK_NETWORK_CURRENT,
  MOCK_DEVICES_ALL,
  MOCK_FILE_ACCESS_LOGS,
  MOCK_TAPO_POWER_HISTORY,
  MOCK_MOUNTPOINTS,
  MOCK_FILE_LIST,
  MOCK_FILE_LIST_DOCUMENTS,
  MOCK_USERS_LIST,
  MOCK_VCL_QUOTA,
} from './mock-data';

const FAKE_TOKEN = 'fake-jwt-token-for-e2e';

interface Fixtures {
  authenticatedPage: Page;
  authenticatedContext: BrowserContext;
  regularUserPage: Page;
  unauthenticatedPage: Page;
}

/** Inject a JWT token into localStorage before any page JS runs. */
async function injectToken(context: BrowserContext, token: string) {
  await context.addInitScript((t) => {
    try { window.localStorage.setItem('token', t); } catch {}
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch {}
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch {}
  }, token);
}

/** JSON route helper */
function json(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(data),
  };
}

/**
 * Mock all API routes needed for the app shell to render
 * (health gate, auth, version, plugins, system mode).
 */
async function mockCoreRoutes(context: BrowserContext, user: typeof MOCK_ADMIN_USER) {
  // Health gate
  await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));

  // Auth - me endpoint
  await context.route('**/api/auth/me', (r) => r.fulfill(json({ user })));

  // Version & system mode (used by Login + Layout)
  await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
  await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));

  // Plugins (loaded by PluginProvider)
  await context.route('**/api/plugins', (r) => r.fulfill(json(MOCK_PLUGINS)));
  await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json(MOCK_PLUGINS_MANIFEST)));
}

/**
 * Mock all Dashboard-related API routes.
 */
async function mockDashboardRoutes(context: BrowserContext) {
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
}

/**
 * Mock File-Manager-specific endpoints.
 * Exported so individual tests can call it when needed.
 */
export async function mockFileManagerRoutes(context: BrowserContext) {
  await context.route('**/api/files/mountpoints', (r) => r.fulfill(json(MOCK_MOUNTPOINTS)));
  await context.route('**/api/files/list**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.searchParams.get('path') || '';
    if (path.includes('Documents')) {
      await route.fulfill(json(MOCK_FILE_LIST_DOCUMENTS));
    } else {
      await route.fulfill(json(MOCK_FILE_LIST));
    }
  });
  await context.route('**/api/users', (r) => r.fulfill(json(MOCK_USERS_LIST)));
  await context.route('**/api/files/vcl/quota', (r) => r.fulfill(json(MOCK_VCL_QUOTA)));
}

export const test = base.extend<Fixtures>({
  /**
   * Fully authenticated admin page with all core + dashboard routes mocked.
   */
  authenticatedPage: async ({ browser }, use) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await injectToken(context, FAKE_TOKEN);
    await mockCoreRoutes(context, MOCK_ADMIN_USER);
    await mockDashboardRoutes(context);

    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  /**
   * The browser context backing authenticatedPage, for adding extra route mocks.
   */
  authenticatedContext: async ({ browser }, use) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await injectToken(context, FAKE_TOKEN);
    await mockCoreRoutes(context, MOCK_ADMIN_USER);
    await mockDashboardRoutes(context);

    await use(context);
    await context.close();
  },

  /**
   * Authenticated as a regular (non-admin) user.
   */
  regularUserPage: async ({ browser }, use) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await injectToken(context, FAKE_TOKEN);
    await mockCoreRoutes(context, MOCK_REGULAR_USER);
    await mockDashboardRoutes(context);

    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  /**
   * No token injected — simulates an unauthenticated visitor.
   * Only health and system mode are mocked (needed for the app shell / login page).
   */
  unauthenticatedPage: async ({ browser }, use) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));
    await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));
    await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
    // Auth/me should fail for unauthenticated users
    await context.route('**/api/auth/me', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) }));

    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { expect };
