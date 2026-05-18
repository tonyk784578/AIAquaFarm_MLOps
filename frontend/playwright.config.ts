/**
 * Playwright config — runs end-to-end smoke against a live stack.
 *
 * Local: bring the full compose stack up (`make up && make seed`) so the
 * backend is reachable at http://localhost:8000 and the dashboard at
 * http://localhost:3000 (or the Nginx gateway on :80 in production builds).
 *
 * CI: the workflow boots the compose stack as a job step before running
 * Playwright (see `.github/workflows/ci.yml :: e2e`).
 *
 * Tests live in `frontend/e2e/`. They are isolated from the Vitest suite
 * — different runner, different config, no shared setup. Vitest only runs
 * jsdom unit tests under `src/**`.
 */
import { defineConfig, devices } from '@playwright/test'

const PORT = Number(process.env.E2E_PORT ?? 3000)
const HOST = process.env.E2E_HOST ?? 'http://localhost'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,             // login state mutates the cookie jar — keep tests serial
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,                       // single worker — same reason as above
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',

  use: {
    baseURL: `${HOST}:${PORT}`,
    headless: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
