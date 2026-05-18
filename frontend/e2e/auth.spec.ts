/**
 * Authentication smoke — login form → dashboard transition.
 *
 * Depends on:
 *   - backend at http://localhost:8000 (rate limiter set to 10/min)
 *   - a seeded admin user (created by `make seed` once REGISTRATION_OPEN=true)
 *
 * Credentials come from env so the same spec runs locally (./.env) and in CI
 * (job-level env block).
 */
import { expect, test } from '@playwright/test'

const ADMIN_USER = process.env.E2E_ADMIN_USER ?? 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS ?? 'admin'

test('login → dashboard renders successfully', async ({ page }) => {
  await page.goto('/login')

  // Page shell loaded.
  await expect(page.locator('h1', { hasText: 'AIAquafarm' })).toBeVisible()

  // The form has no name= attributes, so target by placeholder + type.
  await page.getByPlaceholder('admin').fill(ADMIN_USER)
  await page.locator('input[type="password"]').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '로그인' }).click()

  // Dashboard route renders the System Flow panel and KPI grid.
  await page.waitForURL('**/dashboard', { timeout: 15_000 })
  await expect(page.locator('h1, h2', { hasText: /대시보드|Dashboard/i })).toBeVisible({
    timeout: 10_000,
  })
})

test('invalid credentials surface error message', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('admin').fill('definitely-not-a-user')
  await page.locator('input[type="password"]').fill('wrong-password')
  await page.getByRole('button', { name: '로그인' }).click()

  await expect(
    page.getByText('아이디 또는 비밀번호가 올바르지 않습니다.'),
  ).toBeVisible({ timeout: 10_000 })
  // URL must NOT have transitioned away from /login
  expect(page.url()).toContain('/login')
})

test('unauthenticated /dashboard redirects to /login', async ({ page, context }) => {
  await context.clearCookies()
  await page.goto('/dashboard')
  await page.waitForURL('**/login', { timeout: 10_000 })
})
