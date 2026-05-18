/**
 * MLOps page smoke — verifies the backend proxy + mlops_api round-trip.
 *
 * Logs in first so the cookie jar can authenticate /api/v1/mlops/* calls.
 * The page must render the four core sections (Production model status,
 * Registry, Drift, Audit) without throwing.
 */
import { expect, test } from '@playwright/test'

const ADMIN_USER = process.env.E2E_ADMIN_USER ?? 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS ?? 'admin'

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('admin').fill(ADMIN_USER)
  await page.locator('input[type="password"]').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '로그인' }).click()
  await page.waitForURL('**/dashboard')
})

test('mlops page sections render', async ({ page }) => {
  await page.goto('/mlops')

  await expect(page.getByText('MLOps 모델 관리')).toBeVisible()
  await expect(page.getByText('Production 모델 상태', { exact: false })).toBeVisible()
  await expect(page.getByText('MLflow 레지스트리')).toBeVisible()
  await expect(page.getByText(/드리프트 리포트/)).toBeVisible()
  await expect(page.getByText('MLOps 감사 로그')).toBeVisible()
})

test('audit log filter dropdown changes the query', async ({ page }) => {
  await page.goto('/mlops')
  await expect(page.getByText('MLOps 감사 로그')).toBeVisible()

  // Inspect the network call so we know the filter actually propagates.
  const auditRequest = page.waitForRequest((req) =>
    req.url().includes('/api/v1/mlops/audit') && req.url().includes('kind=drift'),
  )
  await page.locator('select').selectOption('drift')
  await auditRequest
})
