import { test, expect } from '@playwright/test'
import { TEST_EMAIL, TEST_PASSWORD } from '../fixtures/test-user.js'

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.fill('input[type="email"]', TEST_EMAIL)
  await page.fill('input[type="password"]', TEST_PASSWORD)
  await page.click('button:has-text("Sign in")')
  await page.waitForURL(/\/cycle/)
})

test('create a task and mark it complete', async ({ page }) => {
  const title = `Buy milk ${Date.now()}`
  await page.fill('input[placeholder="Add a task…"]', title)
  await page.keyboard.press('Enter')
  await expect(page.getByText(title)).toBeVisible()

  // Click the open-row checkbox (first matching aria-label).
  await page
    .locator(`text=${title}`)
    .first()
    .locator('xpath=ancestor::*[contains(@class,"flex")][1]//button[@aria-label="Mark complete"]')
    .first()
    .click()

  // Open the resolved-tasks toggle so we can see the count.
  await page.getByRole('button', { name: /open · .* done/i }).click()
  await expect(page.getByText(/Completed \(/)).toBeVisible()
})
