// iPhone home-screen QA: WebKit at iPhone sizes against a running frontend, API stubbed in the
// browser (no backend or sign-in needed). Checks the things that make the app feel like a web
// page on a phone and saves screenshots.
//
//   npx playwright install webkit   (once)
//   node scripts/mobile-qa.mjs [tag] [base-url] [--live]
//   node scripts/mobile-qa.mjs after http://localhost:5174
//
// Screenshots go to ../.mobile-qa/<tag>-<device>-<screen>.png (git-ignored). Exit code 1 if a
// check fails. --live skips the API stub (the live site only shows its login page signed out).
import { webkit, devices } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const args = process.argv.slice(2).filter((a) => !a.startsWith('--'))
const TAG = args[0] || 'run'
const BASE = (args[1] || 'http://localhost:5174').replace(/\/$/, '')
const STUB = !process.argv.includes('--live')
const OUT = path.resolve(import.meta.dirname, '../../.mobile-qa')
mkdirSync(OUT, { recursive: true })

const now = Date.now()
const iso = (daysAgo) => new Date(now - daysAgo * 86400_000).toISOString()
let nextId = 1
function task(over = {}) {
  const id = nextId++
  return {
    id: `t${id}`,
    persistent_task_id: `p${id}`,
    display_id: id,
    category: 'personal',
    owner: 'human',
    status: 'open',
    title: `Task number ${id}`,
    notes: null,
    position: id,
    push_forward_count: 0,
    created_at: iso(3),
    updated_at: iso(1),
    completed_at: null,
    canceled_at: null,
    note_count: 0,
    ...over,
  }
}
const open = [
  task({ title: 'Renew passport before the trip, check photo requirements', notes: 'Form DS-82.' }),
  task({ title: 'Call the dentist' }),
  task({ title: 'Averyveryverylongwordwithoutanyspacesthatcouldpushtherowwiderthanthephone' }),
  ...Array.from({ length: 11 }, () => task()),
]
const completed = [task({ status: 'completed', title: 'Pay the water bill', completed_at: iso(1) })]
const agent = [
  task({
    owner: 'agent',
    agent_status: 'in_progress',
    title: 'Security sweep: bump Postgres in CI',
    source: 'weekly-security-sweep routine on the Mac mini',
    link: 'https://github.com/mcheli/tasks/pull/123456789/files#diff-averylonganchorthatgoesonandon',
    note_count: 1,
  }),
  task({ owner: 'agent', agent_status: 'blocked', title: 'Waiting on DNS change', source: 'claude.ai' }),
]

async function stub(page) {
  await page.route((u) => u.pathname.startsWith('/api/'), (route) => {
    const url = new URL(route.request().url())
    const p = url.pathname.replace(/^\/api/, '')
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (p === '/auth/config') return json({ google_configured: false, demo_mode: false, demo_url: null })
    if (p === '/auth/me')
      return page.__signedIn ? json({ id: 'u1', email: 'mark@example.com' }) : json({ detail: 'no' }, 401)
    if (p === '/cycles/current')
      return json({
        cycle: { id: 'c1', category: 'personal', started_at: iso(4), ended_at: null },
        tasks: { open: [...open, ...agent], completed, canceled: [] },
      })
    if (p === '/history')
      return json({
        cycles: [
          { id: 'c0', started_at: iso(18), ended_at: iso(4) },
          { id: 'c1', started_at: iso(4), ended_at: null },
        ],
        lineages: [],
      })
    if (p === '/api-keys') return json([])
    if (p.startsWith('/tasks/')) return json({ task: agent[0], notes_log: [] })
    return json({})
  })
}

const failures = []
const results = []
function check(device, screen, name, ok, detail = '') {
  results.push(`${ok ? 'PASS' : 'FAIL'} ${device} ${screen}: ${name}${detail ? ` — ${detail}` : ''}`)
  if (!ok) failures.push(`${device} ${screen}: ${name}`)
}

/** Every visible field's computed font-size, the page's horizontal overflow, small tap targets. */
async function measure(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const r = el.getBoundingClientRect()
      return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'
    }
    const fields = [...document.querySelectorAll('input, textarea, select, [contenteditable]')]
      .filter(visible)
      .map((el) => ({
        what: `${el.tagName.toLowerCase()}${el.placeholder ? ` "${el.placeholder}"` : ''}`,
        size: parseFloat(getComputedStyle(el).fontSize),
      }))
    const small = [
      ...document.querySelectorAll('button, a[href], [role="tab"], [role="radio"], .drag-handle'),
    ]
      .filter(visible)
      .map((el) => {
        const r = el.getBoundingClientRect()
        return { what: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30), w: r.width, h: r.height }
      })
      .filter((t) => t.w < 44 || t.h < 44)
      // Inline text links inside prose are fine at text size.
      .filter((t) => t.what)
    const wide = [...document.querySelectorAll('body *')]
      .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].slice(0, 3).join('.')}`)
    return {
      fields,
      small,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      wide,
    }
  })
}

async function commonChecks(page, device, screen) {
  const m = await measure(page)
  const tiny = m.fields.filter((f) => f.size < 16)
  check(device, screen, 'fields >= 16px', !tiny.length, tiny.map((f) => `${f.what}=${f.size}px`).join(', '))
  check(
    device,
    screen,
    'no horizontal overflow',
    m.scrollWidth <= m.innerWidth,
    `scrollWidth ${m.scrollWidth} vs ${m.innerWidth}${m.wide.length ? `; wide: ${m.wide.join(', ')}` : ''}`
  )
  if (m.small.length)
    results.push(
      `INFO ${device} ${screen}: tap targets < 44px: ${m.small.map((t) => `${t.what} ${Math.round(t.w)}x${Math.round(t.h)}`).join('; ')}`
    )
}

async function shot(page, device, screen, opts = {}) {
  await page.screenshot({ path: path.join(OUT, `${TAG}-${device}-${screen}.png`), ...opts })
}

async function run(deviceName) {
  const short = deviceName.replace(/^iPhone /, '').replace(/\s+/g, '')
  const browser = await webkit.launch()
  const context = await browser.newContext({ ...devices[deviceName], isMobile: true, hasTouch: true })
  const page = await context.newPage()
  page.on('pageerror', (e) => results.push(`ERROR ${short}: ${e.message}`))
  if (STUB) await stub(page)

  // Static setup: viewport meta, manifest, Apple tags.
  await page.goto(`${BASE}/login`)
  await page.waitForLoadState('networkidle')
  const head = await page.evaluate(() => ({
    viewport: document.querySelector('meta[name=viewport]')?.content || '',
    manifest: document.querySelector('link[rel=manifest]')?.href || '',
    capable: document.querySelector('meta[name=apple-mobile-web-app-capable]')?.content || '',
    mobileCapable: document.querySelector('meta[name=mobile-web-app-capable]')?.content || '',
    statusBar: document.querySelector('meta[name=apple-mobile-web-app-status-bar-style]')?.content || '',
    touchIcon: document.querySelector('link[rel=apple-touch-icon]')?.href || '',
  }))
  for (const want of ['width=device-width', 'initial-scale=1', 'viewport-fit=cover', 'maximum-scale=1'])
    check(short, 'head', `viewport has ${want}`, head.viewport.replace(/\s/g, '').includes(want), head.viewport)
  check(short, 'head', 'apple-mobile-web-app-capable=yes', head.capable === 'yes')
  check(short, 'head', 'mobile-web-app-capable=yes', head.mobileCapable === 'yes')
  check(short, 'head', 'status-bar-style set', !!head.statusBar, head.statusBar)
  check(short, 'head', 'apple-touch-icon', !!head.touchIcon)
  if (head.manifest) {
    const man = await (await page.request.get(head.manifest)).json()
    check(short, 'head', 'manifest standalone', man.display === 'standalone')
    check(short, 'head', 'manifest icons 192+512', ['192x192', '512x512'].every((s) => man.icons?.some((i) => i.sizes === s)))
  } else check(short, 'head', 'manifest link', false)

  const htmlStyle = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement)
    return {
      touch: cs.touchAction,
      overscroll: cs.overscrollBehaviorY || cs.overscrollBehavior,
      sizeAdjust: cs.webkitTextSizeAdjust || cs.textSizeAdjust,
    }
  })
  check(short, 'head', 'html touch-action manipulation', htmlStyle.touch === 'manipulation', htmlStyle.touch)
  check(short, 'head', 'html overscroll-behavior none', htmlStyle.overscroll === 'none', htmlStyle.overscroll)

  await commonChecks(page, short, 'login')
  await shot(page, short, 'login')

  if (!STUB) {
    await browser.close()
    return
  }

  // Signed in from here on.
  page.__signedIn = true
  await page.goto(`${BASE}/cycle`)
  await page.getByText('Call the dentist').waitFor()
  await commonChecks(page, short, 'cycle')
  await shot(page, short, 'cycle')

  // Header icons.
  const headerBtns = await page.evaluate(() =>
    ['History', 'Settings', 'Sign out'].map((l) => {
      const r = document.querySelector(`header button[aria-label="${l}"]`).getBoundingClientRect()
      return { l, w: r.width, h: r.height }
    })
  )
  for (const b of headerBtns)
    check(short, 'cycle', `header ${b.l} >= 44px`, b.w >= 44 && b.h >= 44, `${Math.round(b.w)}x${Math.round(b.h)}`)
  // The checkbox stays 20px to look at; a tap anywhere in the 44px square around it must hit it.
  const cbHit = await page.evaluate(() => {
    const el = document.querySelectorAll('button[aria-label="Mark complete"]')[1]
    const r = el.getBoundingClientRect()
    const cx = r.left + r.width / 2
    const cy = r.top + r.height / 2
    const pts = [[-21, -21], [21, -21], [-21, 21], [21, 21], [0, -21], [0, 21], [-21, 0], [21, 0]]
    return pts
      .map(([dx, dy]) => [dx, dy, document.elementFromPoint(cx + dx, cy + dy)])
      .filter(([, , hit]) => !el.contains(hit))
      .map(([dx, dy, hit]) => `(${dx},${dy}) hit ${hit?.tagName.toLowerCase()}.${hit?.classList[0] || ''}`)
  })
  check(short, 'cycle', 'row checkbox tap area >= 44px', !cbHit.length, cbHit.join(', '))

  // Last row vs the floating Start New Cycle button.
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await page.waitForTimeout(400)
  const overlap = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(
      (b) => b.textContent.trim() === 'Start New Cycle' && b.getBoundingClientRect().width > 0
    )
    const rows = [...document.querySelectorAll('main .group')]
    const last = rows[rows.length - 1].getBoundingClientRect()
    const b = btn.getBoundingClientRect()
    return { lastBottom: last.bottom, btnTop: b.top }
  })
  check(
    short,
    'cycle-bottom',
    'Start New Cycle does not cover the last row',
    overlap.lastBottom <= overlap.btnTop,
    `last row bottom ${Math.round(overlap.lastBottom)}, button top ${Math.round(overlap.btnTop)}`
  )
  await shot(page, short, 'cycle-bottom')
  await page.evaluate(() => window.scrollTo(0, 0))

  // Add-a-task input focused: hint hidden on touch, fields big enough.
  await page.locator('input[placeholder="Add a task…"]').tap()
  await page.waitForTimeout(300)
  const hintVisible = await page.getByText('Enter to save', { exact: false }).isVisible()
  check(short, 'cycle-input', 'keyboard hint hidden on touch', !hintVisible)
  const scale = await page.evaluate(() => window.visualViewport?.scale ?? 1)
  check(short, 'cycle-input', 'no zoom on focus', scale === 1, `scale ${scale}`)
  await commonChecks(page, short, 'cycle-input')
  await shot(page, short, 'cycle-input')
  await page.locator('main').getByRole('button', { name: 'Cancel', exact: true }).tap()

  // A task expanded and in edit mode.
  await page.getByText('Renew passport').tap()
  await page.getByRole('button', { name: 'Edit', exact: true }).tap()
  await commonChecks(page, short, 'task-edit')
  await shot(page, short, 'task-edit')
  await page.getByRole('button', { name: 'Cancel', exact: true }).first().tap()

  // Agents tab with an item expanded (notes box).
  await page.getByTestId('owner-agent').tap()
  await page.getByText('Security sweep').tap()
  await page.locator('textarea[placeholder="Add a note…"]').waitFor()
  await commonChecks(page, short, 'agents')
  await shot(page, short, 'agents')

  for (const screen of ['history', 'settings', 'cycle/transition']) {
    await page.goto(`${BASE}/${screen}`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(300)
    const name = screen.replace('cycle/', '')
    await commonChecks(page, short, name)
    await shot(page, short, name)
  }
  await browser.close()
}

for (const d of ['iPhone 15 Pro', 'iPhone SE']) {
  try {
    await run(d)
  } catch (e) {
    failures.push(`${d}: crashed: ${e.message.split('\n')[0]}`)
  }
}
console.log(results.join('\n'))
console.log(failures.length ? `\n${failures.length} FAILED:\n${failures.join('\n')}` : '\nall checks passed')
process.exit(failures.length ? 1 : 0)
