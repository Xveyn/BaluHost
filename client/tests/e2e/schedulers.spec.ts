import { test, expect } from './fixtures/auth.fixture';

// E2E: Mock backend API calls so tests run without a live backend
test('schedulers: mock API + trigger Run Now for SMART and RAID', async ({ authenticatedContext }) => {
  // Mock run-now endpoints for each scheduler
  await authenticatedContext.route('**/api/schedulers/smart_short/run-now', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, message: 'SMART Short Test started successfully' }),
    });
  });

  await authenticatedContext.route('**/api/schedulers/raid_scrub/run-now', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, message: 'RAID Scrub started successfully' }),
    });
  });

  const page = await authenticatedContext.newPage();
  await page.goto('/schedulers');
  await page.waitForLoadState('networkidle');

  // Verify scheduler cards are visible
  await expect(page.locator('text=SMART Short Test').first()).toBeVisible({ timeout: 10000 });
  await expect(page.locator('text=RAID Scrub').first()).toBeVisible();

  // Find Run Now buttons (one per scheduler card)
  const runNowButtons = page.locator('button:has-text("Run Now")');
  await expect(runNowButtons.first()).toBeVisible();

  // Click the first Run Now (SMART Short Test)
  await runNowButtons.nth(0).click();
  await expect(page.locator('text=SMART Short Test started successfully').first()).toBeVisible({ timeout: 10000 });

  // Click the second Run Now (RAID Scrub)
  await runNowButtons.nth(1).click();
  await expect(page.locator('text=RAID Scrub started successfully').first()).toBeVisible({ timeout: 10000 });
});
