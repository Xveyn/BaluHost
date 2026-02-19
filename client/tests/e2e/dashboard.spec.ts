import { test, expect } from './fixtures/auth.fixture';

test.describe('Dashboard', () => {
  test('shows CPU, Memory, Storage and Uptime widgets', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // The 4 quick-stat widgets should be visible
    await expect(page.locator('text=CPU').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Memory').first()).toBeVisible();
    await expect(page.locator('text=Total Effective Storage').first()).toBeVisible();
    await expect(page.locator('text=Uptime').first()).toBeVisible();

    // Values from mock data should render
    // CPU usage: 12.5%
    await expect(page.locator('text=12.5%').first()).toBeVisible();
    // Uptime: 86400s = 1d 0h
    await expect(page.locator('text=1d 0h').first()).toBeVisible();
  });

  test('shows SMART device info', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // SMART section with device name from mock
    await expect(page.locator('text=MockDisk SSD 500GB').first()).toBeVisible({ timeout: 10000 });
    // Status should show PASSED
    await expect(page.locator('text=PASSED').first()).toBeVisible();
  });

  test('shows RAID status', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // RAID section should show md0 array
    await expect(page.locator('text=md0').first()).toBeVisible({ timeout: 10000 });
    // Status badge should show "optimal"
    await expect(page.locator('text=optimal').first()).toBeVisible();
  });
});
