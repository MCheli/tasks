import { test, expect } from '@playwright/test'
import { TEST_EMAIL, TEST_PASSWORD } from '../fixtures/test-user.js'

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.fill('input[type="email"]', TEST_EMAIL)
  await page.fill('input[type="password"]', TEST_PASSWORD)
  await page.click('button:has-text("Sign in")')
  await page.waitForURL(/\/cycle/)
})

test('create three tasks then transition with mixed actions', async ({ page }) => {
  const stamp = Date.now()
  for (const t of ['A', 'B', 'C']) {
    await page.fill('input[placeholder="Add a task…"]', `${t}-${stamp}`)
    await page.keyboard.press('Enter')
    await expect(page.getByText(`${t}-${stamp}`)).toBeVisible()
  }

  await page.getByRole('button', { name: /Start New Cycle/i }).click()
  await page.waitForURL(/\/cycle\/transition/)

  // Default state is all-forward. Switch B to complete (one click) and
  // C to cancel (two clicks).
  const titleB = page.getByText(`B-${stamp}`).first()
  await titleB
    .locator('xpath=ancestor::*[contains(@class,"flex")][1]//button[1]')
    .first()
    .click() // forward → complete

  const titleC = page.getByText(`C-${stamp}`).first()
  const btnC = titleC.locator(
    'xpath=ancestor::*[contains(@class,"flex")][1]//button[1]'
  ).first()
  await btnC.click() // forward → complete
  await btnC.click() // complete → cancel

  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: /Start New Cycle/i }).click()
  await page.waitForURL(/\/cycle$/)

  // Forwarded A should still appear; B and C should not be in the open list.
  await expect(page.getByText(`A-${stamp}`)).toBeVisible()
})
