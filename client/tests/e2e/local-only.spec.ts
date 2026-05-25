/**
 * E2E: channel-status disables destructive buttons.
 *
 * Verifies the LocalOnlyAction wrapper around the RAID Management
 * "Delete Array" button: when the backend reports channel=remote (i.e. the
 * request did not come through the Tauri Companion app's Unix socket), the
 * button must render disabled with a Lock icon next to it. When the channel
 * is local, the button must be enabled.
 *
 * Backend remains the authoritative gate (403 on remote); this is a UX
 * regression test for the frontend wiring of useChannelStatus +
 * LocalOnlyAction inside RaidArrayCard.
 */
import { test, expect, type BrowserContext } from '@playwright/test';
import {
  MOCK_ADMIN_USER,
  MOCK_HEALTH,
  MOCK_VERSION,
  MOCK_SYSTEM_MODE,
  MOCK_PLUGINS,
  MOCK_PLUGINS_MANIFEST,
  MOCK_RAID_STATUS,
  MOCK_SYSTEM_INFO,
} from './fixtures/mock-data';

const FAKE_TOKEN = 'fake-jwt-token-for-e2e';

function json(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(data),
  };
}

/**
 * Mock the minimum endpoints needed to render the RAID Management tab.
 * channelOverride controls the value returned by /api/system/channel-status.
 */
async function mockRaidPageRoutes(context: BrowserContext, channel: 'local' | 'remote') {
  // The destructive-button gate under test
  await context.route('**/api/system/channel-status', (r) => r.fulfill(json({ channel })));

  // App shell
  await context.route('**/api/health', (r) => r.fulfill(json(MOCK_HEALTH)));
  await context.route('**/api/auth/me', (r) => r.fulfill(json({ user: MOCK_ADMIN_USER })));
  await context.route('**/api/updates/version', (r) => r.fulfill(json(MOCK_VERSION)));
  await context.route('**/api/system/mode', (r) => r.fulfill(json(MOCK_SYSTEM_MODE)));
  await context.route('**/api/plugins', (r) => r.fulfill(json(MOCK_PLUGINS)));
  await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json(MOCK_PLUGINS_MANIFEST)));

  // RAID page data
  await context.route('**/api/system/raid/status', (r) => r.fulfill(json(MOCK_RAID_STATUS)));
  await context.route('**/api/system/raid/available-disks', (r) =>
    r.fulfill(json({ disks: [] }))
  );
  await context.route('**/api/system/info', (r) => r.fulfill(json(MOCK_SYSTEM_INFO)));

  // Notifications poll runs in the background; stub it so we don't get noisy errors
  await context.route('**/api/notifications/**', (r) =>
    r.fulfill(json({ notifications: [], total: 0 }))
  );
  await context.route('**/api/notifications?**', (r) =>
    r.fulfill(json({ notifications: [], total: 0 }))
  );
}

async function injectToken(context: BrowserContext) {
  await context.addInitScript((t) => {
    try { window.localStorage.setItem('token', t); } catch {}
  }, FAKE_TOKEN);
}

test.describe('local-only action gating (RAID delete-array)', () => {
  test('delete-array button is disabled when channel is remote', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await injectToken(context);
    await mockRaidPageRoutes(context, 'remote');

    const page = await context.newPage();
    await page.goto('/admin/system-control?tab=raid');

    // Wait for the RAID array card to render (md0 from MOCK_RAID_STATUS)
    await expect(page.locator('text=md0').first()).toBeVisible({ timeout: 10_000 });

    // The "Delete Array" button on the array card should be disabled.
    // The desktop label is "Delete Array"; the mobile label is just "Delete".
    // playwright's viewport is 1280x800 (desktop), so the long label is shown.
    const deleteBtn = page.getByRole('button', { name: 'Delete Array' });
    await expect(deleteBtn).toBeDisabled();

    await context.close();
  });

  test('delete-array button is enabled when channel is local', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await injectToken(context);
    await mockRaidPageRoutes(context, 'local');

    const page = await context.newPage();
    await page.goto('/admin/system-control?tab=raid');

    await expect(page.locator('text=md0').first()).toBeVisible({ timeout: 10_000 });

    const deleteBtn = page.getByRole('button', { name: 'Delete Array' });
    await expect(deleteBtn).toBeEnabled();

    await context.close();
  });
});
