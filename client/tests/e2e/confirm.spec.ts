import { test, expect } from '@playwright/test';

// E2E: Mock the confirmation request and execute endpoints and ensure the modal appears
test('confirmation request -> execute flow (mocked)', async ({ browser }) => {
  const fakeToken = 'e2e-fake-token-xyz';

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await context.addInitScript((t) => {
    try { window.localStorage.setItem('token', t); } catch (e) {}
    try { window.sessionStorage.setItem('baludesk-api-token', t); } catch (e) {}
  }, fakeToken);

  // Mock raid status to render an array with Delete button
  await context.route('**/api/system/raid/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ arrays: [{ name: 'md0', level: '1', status: 'optimal', devices: [{ name: '/dev/sda', state: 'active' }], size_bytes: 5 * 1024 * 1024 * 1024 }] }),
    });
  });

  // When requesting confirmation, return a token
  await context.route('**/api/system/raid/confirm/request', async (route, request) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token: fakeToken, expires_at: Math.floor(Date.now() / 1000) + 3600 }),
    });
  });

  // When executing confirmation, return success message
  await context.route('**/api/system/raid/confirm/execute', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Array deleted (simulated)' }),
    });
  });

  const page = await context.newPage();
  await page.goto('/schedulers');

  // Wait for delete button and click it
  await page.waitForSelector('button:has-text("Delete")', { timeout: 10000 });
  await page.click('button:has-text("Delete")');

  // Expect modal to show token
  await page.waitForSelector('text=Token', { timeout: 5000 });
  await expect(page.locator('text=Token')).toBeVisible();
  await expect(page.locator(`text=${fakeToken}`)).toBeVisible();

  // Click Confirm Execute
  await page.click('button:has-text("Confirm Execute")');

  // Expect success toast/message
  await page.waitForSelector('text=Array deleted (simulated)', { timeout: 5000 });

  await context.close();
});
