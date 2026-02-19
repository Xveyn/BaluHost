import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  timeout: 30_000,
  testDir: './tests/e2e',
  use: {
    // Allow overriding baseURL via PLAYWRIGHT_BASE_URL env var for local runs
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173',
    headless: true,
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    actionTimeout: 10_000,
    locale: 'en-US',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
