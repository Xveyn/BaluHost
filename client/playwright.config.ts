import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  timeout: 30_000,
  testDir: './tests/e2e',
  testIgnore: ['**/*.live.spec.ts'],
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    actionTimeout: 10_000,
    locale: 'en-US',
  },
  // Zwei Engines, damit engine-spezifische Layout-/API-Unterschiede auffallen (#545).
  // Beide Device-Profile bringen 1280x720 mit und ueberschreiben damit `use.viewport`
  // oben — der Viewport ist bewusst identisch, hier geht es nur um die Engine.
  // Ein zusaetzlicher Viewport folgt separat; 1920x1080 waere wirkungslos (zwischen
  // 1280 und 1920 unterscheiden sich genau drei `2xl:`-Utilities in CpuTab.tsx,
  // die keine Spec anfasst) — die ungetestete Flaeche liegt unter 640px.
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  ],
  webServer: {
    command: 'npm run dev -- --port 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
