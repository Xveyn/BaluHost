/**
 * E2E: Plugin sandbox isolation assertions.
 *
 * Verifies that:
 *  1. PluginSandboxHost renders the iframe with sandbox="allow-scripts" (no allow-same-origin).
 *  2. The main browsing context does NOT expose window.BaluHost (no SDK leak).
 *
 * Uses the mock-e2e harness (no live backend required).
 */
import { test, expect } from './fixtures/auth.fixture';

test(
  'plugin renders in an opaque-origin sandbox iframe and host exposes no SDK',
  async ({ authenticatedContext }) => {
    // Override the fixture's empty-manifest mock with one that includes storage_analytics.
    // Register on the context BEFORE creating the page so it fires first.
    await authenticatedContext.route('**/api/plugins/ui/manifest', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          plugins: [
            {
              name: 'storage_analytics',
              display_name: 'Storage Analytics',
              nav_items: [],
              bundle_path: '/api/plugins/storage_analytics/ui/bundle.js',
              dashboard_widgets: [],
              granted_api_scopes: [],
              min_runtime_abi: 1,
            },
          ],
        }),
      });
    });

    const page = await authenticatedContext.newPage();

    await page.goto('/plugins/storage_analytics');
    await page.waitForLoadState('domcontentloaded');

    // 1. The iframe must carry sandbox="allow-scripts" exactly.
    const frame = page.locator('iframe[title="plugin-storage_analytics"]');
    await expect(frame).toBeVisible({ timeout: 10000 });
    await expect(frame).toHaveAttribute('sandbox', 'allow-scripts');

    // 2. allow-same-origin must NOT appear in the sandbox value (opaque origin).
    const sandboxValue = await frame.getAttribute('sandbox');
    expect(sandboxValue).not.toContain('allow-same-origin');

    // 3. The main browsing context must NOT expose window.BaluHost (SDK not leaked to host).
    const hasSDK = await page.evaluate(() => 'BaluHost' in window);
    expect(hasSDK).toBe(false);
  },
);
