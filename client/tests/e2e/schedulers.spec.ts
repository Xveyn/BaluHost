import { test, expect } from '@playwright/test';

// E2E: Mock backend API calls so tests run without a live backend
test('schedulers: mock API + trigger SMART and RAID scrub', async ({ browser }) => {
  const fakeToken = 'fake-token-for-e2e';

  // Create browser context, inject token and mock API routes
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await context.addInitScript((t) => {
    // Set both localStorage token (legacy) and sessionStorage secure token used in web mode
    try { window.localStorage.setItem('token', t); } catch (e) {}
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch (e) {}
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch (e) {}
  }, fakeToken);

  // Mock API responses for the page so we don't depend on backend
  await context.route('**/api/system/smart/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ devices: [{ name: '/dev/sda', model: 'MockDisk', serial: 'MOCK123', state: 'OK', attributes: [], capacity_bytes: 50 * 1024 * 1024 * 1024, used_bytes: 0 }] }),
    });
  });

  await context.route('**/api/system/raid/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ arrays: [{ name: 'md0', level: '1', status: 'optimal', devices: [{ name: '/dev/sda', state: 'active' }], size_bytes: 5 * 1024 * 1024 * 1024 }] }),
    });
  });

  // Mock system info and storage endpoints used by Dashboard
  await context.route('**/api/system/info', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ cpu: { usage: 5, cores: 4 }, memory: { total: 8 * 1024 ** 3, used: 3 * 1024 ** 3 }, uptime: 3600 }),
    });
  });

  await context.route('**/api/system/storage/aggregated', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ used: 10 * 1024 * 1024 * 1024, total: 50 * 1024 * 1024 * 1024 }),
    });
  });

  await context.route('**/api/system/telemetry/history', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ cpu: [], memory: [], network: [] }),
    });
  });

  await context.route('**/api/system/smart/test', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Simulated short SMART test started for /dev/sda' }),
    });
  });

  await context.route('**/api/system/raid/scrub', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'RAID configuration updated (dev mode)' }),
    });
  });

  await context.route('**/api/system/smart/mode', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ mode: 'active', message: 'SMART active' }),
    });
  });

  const page = await context.newPage();
  page.on('console', (m) => console.log('[PAGE CONSOLE]', m.text()));
  page.on('pageerror', (err) => console.log('[PAGE ERROR]', err.message));
  await page.goto('/schedulers');

  // Wait for initial API calls and the schedulers route to settle
  await page.waitForResponse((resp) => resp.url().includes('/api/system/raid/status'), { timeout: 10000 }).catch(() => {});
  await page.waitForLoadState('networkidle');

  // Ensure buttons/text appear (loose match to avoid role/label issues)
  await page.waitForSelector('text=SMART', { timeout: 15000 });
  await page.waitForSelector('text=RAID', { timeout: 15000 });

  const smartBtn = page.locator('button:has-text("SMART")').first();
  const raidBtn = page.locator('button:has-text("RAID")').first();

  // Run SMART short
  await page.waitForSelector('button:has-text("SMART")', { timeout: 10000 });
  await smartBtn.click();
  await expect(page.locator('text=Simulated short SMART test started').first()).toBeVisible({ timeout: 10000 });

  // Trigger RAID scrub
  await page.waitForSelector('button:has-text("RAID")', { timeout: 10000 });
  await raidBtn.click();
  await expect(page.locator('text=RAID configuration updated').first()).toBeVisible({ timeout: 10000 });

  // Take final screenshot
  await page.screenshot({ path: 'e2e-schedulers-result.png', fullPage: true });

  await context.close();
});
