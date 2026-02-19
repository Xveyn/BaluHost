import { test, expect } from './fixtures/auth.fixture';
import { mockFileManagerRoutes } from './fixtures/auth.fixture';

test.describe('File Manager', () => {
  test('shows file list with folders and files', async ({ authenticatedContext }) => {
    await mockFileManagerRoutes(authenticatedContext);
    const page = await authenticatedContext.newPage();

    await page.goto('/files');
    await page.waitForLoadState('networkidle');

    // Mock file list items should be visible
    await expect(page.locator('text=Documents').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Photos').first()).toBeVisible();
    await expect(page.locator('text=readme.txt').first()).toBeVisible();
  });

  test('navigating into a folder shows sub-content', async ({ authenticatedContext }) => {
    await mockFileManagerRoutes(authenticatedContext);
    const page = await authenticatedContext.newPage();

    await page.goto('/files');
    await page.waitForLoadState('networkidle');

    // Click on the Documents folder row in the table
    await page.locator('td:has-text("Documents")').first().click();

    // Should show the Documents sub-contents
    await expect(page.locator('text=report.pdf').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=notes.md').first()).toBeVisible();
  });

  test('storage selector shows mountpoint name', async ({ authenticatedContext }) => {
    await mockFileManagerRoutes(authenticatedContext);
    const page = await authenticatedContext.newPage();

    await page.goto('/files');
    await page.waitForLoadState('networkidle');

    // The mountpoint name from mock data should be visible
    await expect(page.locator('text=Primary Storage').first()).toBeVisible({ timeout: 10000 });
  });
});
