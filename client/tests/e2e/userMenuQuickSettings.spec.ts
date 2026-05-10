import { test, expect } from './fixtures/auth.fixture';

const json = (body: unknown) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

test.describe('User Menu Quick-Settings', () => {
  test('language buttons toggle aria-pressed when clicked', async ({ authenticatedContext }) => {
    // Force a known starting language (German)
    await authenticatedContext.addInitScript(() => {
      try { window.localStorage.setItem('baluhost-language', 'de'); } catch { /* ignore */ }
    });

    const page = await authenticatedContext.newPage();
    await page.goto('/');

    const userMenuTrigger = page.getByRole('button', { name: /admin/i }).first();
    await expect(userMenuTrigger).toBeVisible({ timeout: 10000 });
    await userMenuTrigger.click();

    // Language buttons: accessible name = "<flag> Deutsch" / "<flag> English"
    const deBtn = page.getByRole('button', { name: /Deutsch/ });
    const enBtn = page.getByRole('button', { name: /English/ });
    await expect(deBtn).toBeVisible();
    await expect(enBtn).toBeVisible();

    // Initially DE is active, EN is not
    await expect(deBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(enBtn).toHaveAttribute('aria-pressed', 'false');

    // Click English → flip
    await enBtn.click();
    await expect(enBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(deBtn).toHaveAttribute('aria-pressed', 'false');

    // Click Deutsch → flip back
    await deBtn.click();
    await expect(deBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(enBtn).toHaveAttribute('aria-pressed', 'false');
  });

  test('byte-unit buttons toggle aria-pressed when clicked', async ({ authenticatedContext }) => {
    // Force binary as the starting mode
    await authenticatedContext.addInitScript(() => {
      try { window.localStorage.setItem('baluhost-byte-units', 'binary'); } catch { /* ignore */ }
      // Also force English so hint text is predictable ("binary" / "decimal")
      try { window.localStorage.setItem('baluhost-language', 'en'); } catch { /* ignore */ }
    });

    const page = await authenticatedContext.newPage();
    await page.goto('/');

    await page.getByRole('button', { name: /admin/i }).first().click();

    // Accessible names: "GiB binary" and "GB decimal" (in English)
    // Use anchored patterns to avoid "GiB binary" matching /^GB/
    const giBBtn = page.getByRole('button', { name: /^GiB/ });
    const gBBtn  = page.getByRole('button', { name: /^GB/ });

    await expect(giBBtn).toBeVisible();
    await expect(gBBtn).toBeVisible();

    // Initially binary (GiB) is active
    await expect(giBBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(gBBtn).toHaveAttribute('aria-pressed', 'false');

    // Switch to decimal (GB)
    await gBBtn.click();
    await expect(gBBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(giBBtn).toHaveAttribute('aria-pressed', 'false');

    // Switch back to binary (GiB)
    await giBBtn.click();
    await expect(giBBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(gBBtn).toHaveAttribute('aria-pressed', 'false');
  });

  test('2FA prompt visible when status returns enabled=false', async ({ authenticatedContext }) => {
    // Mock BEFORE creating the page so the route is in place on first load
    await authenticatedContext.route('**/api/auth/2fa/status', (route) =>
      route.fulfill(json({
        enabled: false,
        enabled_at: null,
        backup_codes_remaining: 0,
      })),
    );

    const page = await authenticatedContext.newPage();
    await page.goto('/');
    await page.getByRole('button', { name: /admin/i }).first().click();

    // DE: "Jetzt einrichten" | EN: "Set up now"
    const setupBtn = page.getByRole('button', { name: /Jetzt einrichten|Set up now/ });
    await expect(setupBtn).toBeVisible({ timeout: 5000 });
  });

  test('2FA prompt hidden when status returns enabled=true', async ({ authenticatedContext }) => {
    await authenticatedContext.route('**/api/auth/2fa/status', (route) =>
      route.fulfill(json({
        enabled: true,
        enabled_at: '2026-01-01T00:00:00Z',
        backup_codes_remaining: 5,
      })),
    );

    const page = await authenticatedContext.newPage();
    await page.goto('/');
    await page.getByRole('button', { name: /admin/i }).first().click();

    // Wait for the dropdown to be open and the language buttons to be visible
    // (confirming the Quick-Settings section has rendered)
    await expect(page.getByRole('button', { name: /Deutsch/ })).toBeVisible();

    // Give the async 2FA status fetch time to resolve and the section to settle
    await page.waitForTimeout(500);

    // The "Set up now" / "Jetzt einrichten" button must NOT appear when 2FA is enabled
    await expect(page.getByRole('button', { name: /Jetzt einrichten|Set up now/ })).toHaveCount(0);
  });
});
