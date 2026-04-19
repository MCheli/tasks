import { test, expect } from '@playwright/test'
import { TEST_EMAIL, TEST_PASSWORD } from '../fixtures/test-user.js'

test.describe('auth', () => {
  test('login with the test user lands on /cycle', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', TEST_EMAIL)
    await page.fill('input[type="password"]', TEST_PASSWORD)
    await page.click('button:has-text("Sign in")')
    await expect(page).toHaveURL(/\/cycle/)
    await expect(page.getByText(TEST_EMAIL)).toBeVisible()
  })

  test('wrong password shows inline error', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', TEST_EMAIL)
    await page.fill('input[type="password"]', 'definitely-wrong')
    await page.click('button:has-text("Sign in")')
    await expect(page.getByText(/Invalid email or password/i)).toBeVisible()
  })

  test('sign-out returns to /login', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', TEST_EMAIL)
    await page.fill('input[type="password"]', TEST_PASSWORD)
    await page.click('button:has-text("Sign in")')
    await page.waitForURL(/\/cycle/)
    await page.getByRole('button', { name: /sign out/i }).click()
    await expect(page).toHaveURL(/\/login/)
  })
})
