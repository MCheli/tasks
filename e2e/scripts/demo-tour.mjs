// Visit the public demo like a stranger would, in headless Chrome.
//
//   BASE=http://localhost:5175 OUT=/tmp/tour node scripts/demo-tour.mjs          # the demo
//   BASE=https://tasks.markcheli.com MODE=real node scripts/demo-tour.mjs         # real login page
//
// Records page errors, console errors and API responses >= 400; takes full-height screenshots;
// tries writes from the page and expects 403s. Exits 1 if anything unexpected happened.
import { chromium } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'

const BASE = (process.env.BASE || 'http://localhost:5175').replace(/\/$/, '')
const OUT = process.env.OUT || 'tour-out'
const MODE = process.env.MODE || 'demo'
mkdirSync(OUT, { recursive: true })

const problems = []
const notes = []
const browser = await chromium.launch({ channel: process.env.CHANNEL || 'chrome', headless: true })

function watch(page, label) {
  page.on('pageerror', (e) => problems.push(`[${label}] page error: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/status of 4\d\d/.test(m.text())) problems.push(`[${label}] console: ${m.text()}`)
  })
  page.on('response', (r) => {
    if (r.status() >= 400 && r.url().includes('/api/') && !page._expect403) {
      // An anonymous /auth/me 401 on the login page is how the app learns it's signed out.
      if (!(r.status() === 401 && r.url().endsWith('/api/auth/me'))) problems.push(`[${label}] ${r.status()} ${r.url()}`)
    }
  })
}

async function settle(page) {
  await page.waitForLoadState('networkidle', { timeout: 45000 }).catch(() => {})
  // Wait out any "Loading…" placeholders: the server can be slow.
  await page.waitForFunction(() => !document.body.innerText.includes('Loading…'), null, { timeout: 45000 }).catch(() =>
    problems.push(`still loading after 45s: ${page.url()}`),
  )
  await page.waitForTimeout(1200) // let the hero/Gantt animations finish
}

async function loginShots() {
  for (const [name, opts] of [
    ['login-light', { viewport: { width: 1440, height: 900 }, colorScheme: 'light' }],
    ['login-dark', { viewport: { width: 1440, height: 900 }, colorScheme: 'dark' }],
    ['login-390', { viewport: { width: 390, height: 844 }, colorScheme: 'light', isMobile: true, hasTouch: true }],
    ['login-390-dark', { viewport: { width: 390, height: 844 }, colorScheme: 'dark', isMobile: true, hasTouch: true }],
  ]) {
    const ctx = await browser.newContext(opts)
    const page = await ctx.newPage()
    watch(page, name)
    await page.goto(`${BASE}/login`)
    await settle(page)
    const target = MODE === 'demo' ? '[data-testid="enter-demo"]' : 'button:has-text("Google"), button[type="submit"]'
    const box = await page.locator(target).first().boundingBox()
    if (!box) problems.push(`[${name}] sign-in control not found`)
    else if (box.y + box.height > opts.viewport.height) problems.push(`[${name}] sign-in control below the first screen (y=${Math.round(box.y)})`)
    else notes.push(`[${name}] sign-in control at y=${Math.round(box.y)}..${Math.round(box.y + box.height)}`)
    if (MODE === 'real') {
      const link = await page.locator('[data-testid="demo-link"]').count()
      notes.push(`[${name}] demo card ${link ? 'present' : 'MISSING'}`)
      if (!link) problems.push(`[${name}] no "Try the live demo" card`)
    }
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
    await ctx.close()
  }
}

async function demoTour() {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  watch(page, 'tour')
  await page.goto(`${BASE}/login`)
  await settle(page)
  await page.click('[data-testid="enter-demo"]')
  await page.waitForURL(/\/cycle/, { timeout: 30000 })

  const visit = async (name, path, before) => {
    if (path) await page.goto(`${BASE}${path}`)
    if (before) await before()
    await settle(page)
    const locked = await page.locator('.demo-locked').count()
    const banner = await page.locator('[data-testid="demo-banner"]').count()
    if (!banner) problems.push(`[${name}] no demo banner`)
    notes.push(`[${name}] ${page.url().replace(BASE, '')}: ${locked} locked controls`)
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
  }
  const tab = (label) => () => page.getByRole('tab', { name: label }).first().click()

  await visit('cycle-personal', '/cycle', tab('Personal'))
  await visit('cycle-personal-resolved', null, async () => {
    if ((await page.locator('h2:has-text("Completed")').count()) === 0) await page.locator('button:has-text("open ·")').click()
    await page.locator('div.cursor-pointer').first().click() // expand the first task
  })
  await visit('cycle-professional', null, tab('Professional'))
  await visit('transition-professional', '/cycle/transition', async () => {
    await page.waitForSelector('button[aria-label^="Action for task"]', { timeout: 15000 })
    const toggles = page.locator('button[aria-label^="Action for task"]')
    await toggles.nth(0).click() // forward → complete: a preview, nothing is sent
    await toggles.nth(1).click()
    await toggles.nth(1).click() // → cancel
  })
  await visit('history-professional', '/history')
  await visit('history-personal', null, tab('Personal'))
  await visit('settings-keys', '/settings')
  await visit('settings-reference', null, () => page.click('button:has-text("API Reference")'))

  // Writes from the page itself, with the demo cookie: every one must be refused.
  page._expect403 = true
  const results = await page.evaluate(async () => {
    const tries = [
      ['POST', '/api/tasks', { category: 'personal', title: 'x' }],
      ['POST', '/api/api-keys', { name: 'x' }],
      ['POST', '/api/auth/login', { email: 'claudius@tasks.dev', password: 'x' }],
      ['DELETE', '/api/tasks/00000000-0000-0000-0000-000000000001', null],
    ]
    const out = []
    for (const [method, url, body] of tries) {
      const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body && JSON.stringify(body) })
      out.push({ method, url, status: r.status, body: await r.json().catch(() => null) })
    }
    return out
  })
  page._expect403 = false
  for (const r of results) {
    const ok = r.status === 403 && r.body?.demo === true
    notes.push(`[write] ${r.method} ${r.url} → ${r.status}${ok ? ' (refused, demo)' : ''}`)
    if (!ok) problems.push(`[write] ${r.method} ${r.url} was not refused: ${r.status}`)
  }
  const cfg = await page.evaluate(() => fetch('/api/auth/config').then((r) => r.json()))
  notes.push(`[config] ${JSON.stringify(cfg)}`)
  if (cfg.demo_mode !== true) problems.push('auth/config does not say demo_mode')
  await ctx.close()
}

await loginShots()
if (MODE === 'demo') await demoTour()
await browser.close()

writeFileSync(`${OUT}/report.json`, JSON.stringify({ base: BASE, mode: MODE, notes, problems }, null, 2))
for (const n of notes) console.log(n)
console.log(problems.length ? `\n${problems.length} problem(s):\n${problems.join('\n')}` : '\nNo problems.')
process.exit(problems.length ? 1 : 0)
