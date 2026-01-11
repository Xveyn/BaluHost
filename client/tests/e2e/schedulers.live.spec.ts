import { test, expect } from '@playwright/test';

// Live E2E: authenticate against running backend and exercise schedulers UI
test('schedulers: live backend run', async ({ browser, playwright }) => {
  // Try to login via backend API
  const apiBase = 'http://127.0.0.1:8000';
  const apiContext = await playwright.request.newContext({ baseURL: apiBase });

  const loginRes = await apiContext.post('/api/auth/login', {
    data: { username: 'admin', password: 'changeme' },
  });
  expect(loginRes.ok()).toBeTruthy();
  const loginJson = await loginRes.json();
  const token = loginJson.access_token;
  await apiContext.dispose();

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await context.addInitScript((t) => {
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch (e) {}
    try { window.sessionStorage.setItem('baludesk-username', 'admin'); } catch (e) {}
    try { window.localStorage.setItem('token', t); } catch (e) {}
  }, token);

  const page = await context.newPage();
  page.on('console', (m) => console.log('[PAGE]', m.text()));
  page.on('pageerror', (err) => console.log('[PAGE ERROR]', err.message));

  // Open the schedulers page on the dev frontend
  await page.goto('/schedulers');
  await page.waitForLoadState('networkidle');

  // Wait for RAID status to be fetched (if backend responds)
  await page.waitForResponse((r) => r.url().includes('/api/system/raid/status'), { timeout: 10000 }).catch(() => {});

  // Find action buttons
  const smartBtn = page.locator('button:has-text("SMART")').first();
  const raidBtn = page.locator('button:has-text("RAID")').first();
  await expect(smartBtn).toBeVisible({ timeout: 15000 });
  await expect(raidBtn).toBeVisible({ timeout: 15000 });

  // Run SMART short
  await smartBtn.click();
  // Wait for some toast or message indicating SMART test started
  await page.waitForSelector('text=SMART', { timeout: 15000 }).catch(() => {});

  // Trigger RAID scrub
  await raidBtn.click();
  await page.waitForSelector('text=RAID', { timeout: 15000 }).catch(() => {});

  // Screenshot for artifacts
  await page.screenshot({ path: 'e2e-schedulers-live-result.png', fullPage: true });

  await context.close();
});
