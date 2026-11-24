// Screenshots of the agent list UI against a local instance, at phone and desktop widths.
//
//   BASE=http://localhost:8010 EMAIL=... PASSWORD=... OUT=../docs/screenshots/agent-lists \
//     node scripts/agent-lists-shots.mjs
//
// Signs in with the password form, seeds a few personal tasks (Mark's and agents') through the
// API, then captures: Mine tab, Agents tab, an expanded agent item with its notes log, the
// transition screen's carry-over note and the Settings reference. Exits 1 on page errors.
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const BASE = (process.env.BASE || "http://localhost:8010").replace(/\/$/, "");
const OUT = process.env.OUT || "shots-out";
const EMAIL = process.env.EMAIL;
const PASSWORD = process.env.PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error("EMAIL and PASSWORD are required");
  process.exit(2);
}
mkdirSync(OUT, { recursive: true });

const problems = [];
const notes = [];
const browser = await chromium.launch({
  channel: process.env.CHANNEL || "chrome",
  headless: true,
});

async function api(ctx, method, path, body) {
  const r = await ctx.request.fetch(`${BASE}/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    data: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok())
    problems.push(`${method} ${path} -> ${r.status()} ${await r.text()}`);
  return r.ok() ? r.json() : null;
}

async function seed(ctx) {
  // Personal list only (the professional list is Mark's work list and is never touched here).
  const current = await api(
    ctx,
    "GET",
    "/cycles/current?category=personal&owner=all",
  );
  const have = [
    ...current.tasks.open,
    ...current.tasks.completed,
    ...current.tasks.canceled,
  ];
  if (have.length) {
    notes.push(`cycle already holds ${have.length} task(s); not seeding again`);
    return;
  }
  for (const title of [
    "Book dentist appointment",
    "Replace furnace filter",
    "Plan weekend hike",
  ]) {
    await api(ctx, "POST", "/tasks", { category: "personal", title });
  }
  const a1 = await api(ctx, "POST", "/tasks", {
    category: "personal",
    title: "Bump postgres image after the Nov security release",
    owner: "agent",
    source: "weekly-security-sweep",
    link: "https://github.com/MCheli/83rr-poweredge/pull/66",
    notes: "CVE-2026-xxxx in libpq; the pinned digest is behind.",
  });
  await api(ctx, "PATCH", `/tasks/${a1.task.id}`, {
    agent_status: "in_progress",
  });
  await api(ctx, "POST", `/tasks/${a1.task.id}/notes`, {
    body: "Opened PR #66 with the new digest; CI running.",
    author: "weekly-security-sweep",
  });
  await api(ctx, "POST", `/tasks/${a1.task.id}/notes`, {
    body: "CI green. Waiting for the Monday maintenance window to deploy.",
    author: "weekly-security-sweep",
  });
  const a2 = await api(ctx, "POST", "/tasks", {
    category: "personal",
    title: "Ambient display: show all four lists",
    owner: "agent",
    source: "claude.ai thread",
    link: "https://github.com/MCheli/ambient-display",
  });
  await api(ctx, "PATCH", `/tasks/${a2.task.id}`, { agent_status: "blocked" });
  await api(ctx, "POST", `/tasks/${a2.task.id}/notes`, {
    body: "Blocked until the Tasks API exposes the agent list (this PR).",
    author: "claude.ai thread",
  });
  await api(ctx, "POST", "/tasks", {
    category: "personal",
    title: "Rotate the Seafile read-only token",
    owner: "agent",
    source: "homelab-weekly-check",
  });
  const done = await api(ctx, "POST", "/tasks", {
    category: "personal",
    title: "Connector test (safe to delete)",
    owner: "agent",
    source: "tasks-agent-lists-mcp",
  });
  await api(ctx, "PATCH", `/tasks/${done.task.id}`, { agent_status: "done" });
  notes.push("seeded 3 human + 4 agent items on the personal list");
}

function watch(page, label) {
  page.on("pageerror", (e) =>
    problems.push(`[${label}] page error: ${e.message}`),
  );
  page.on("console", (m) => {
    // An anonymous /auth/me 401 on the login page is how the app learns it's signed out.
    if (m.type() === "error" && !/status of 4\d\d/.test(m.text()))
      problems.push(`[${label}] console: ${m.text()}`);
  });
  page.on("response", (r) => {
    if (
      r.status() >= 400 &&
      r.url().includes("/api/") &&
      !r.url().endsWith("/api/auth/me")
    ) {
      problems.push(`[${label}] ${r.status()} ${r.url()}`);
    }
  });
}

async function settle(page) {
  await page
    .waitForLoadState("networkidle", { timeout: 30000 })
    .catch(() => {});
  await page.waitForTimeout(400);
}

async function login(page) {
  await page.goto(`${BASE}/login`);
  await settle(page);
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/cycle/, { timeout: 20000 });
  await settle(page);
}

async function shots(label, opts) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  watch(page, label);
  await login(page);
  await seed(ctx);
  await page.goto(`${BASE}/cycle`); // the list was loaded before the seed
  await settle(page);

  await page.getByRole("tab", { name: "Personal" }).first().click();
  await page.getByTestId("owner-human").click();
  await settle(page);
  await page.screenshot({ path: `${OUT}/${label}-mine.png`, fullPage: true });

  await page.getByTestId("owner-agent").click();
  await settle(page);
  const badge = await page
    .getByTestId("agent-open-count")
    .textContent()
    .catch(() => null);
  notes.push(`[${label}] agents badge: ${badge}`);
  const chips = await page.getByTestId("status-chip").allTextContents();
  notes.push(`[${label}] status chips: ${chips.join(", ")}`);
  await page.screenshot({ path: `${OUT}/${label}-agents.png`, fullPage: true });

  // Expand the first agent item: notes log + controls.
  await page
    .getByTestId("agent-task")
    .first()
    .locator("div.cursor-pointer")
    .click();
  await page
    .waitForSelector('[data-testid="notes-log"]', { timeout: 10000 })
    .catch(() => problems.push(`[${label}] notes log did not load`));
  await settle(page);
  await page.screenshot({
    path: `${OUT}/${label}-agents-expanded.png`,
    fullPage: true,
  });

  // Done items shown.
  if ((await page.locator('h2:has-text("Done")').count()) === 0) {
    await page.locator('button:has-text("open ·")').click();
    await settle(page);
  }
  await page.screenshot({
    path: `${OUT}/${label}-agents-done.png`,
    fullPage: true,
  });

  await page.goto(`${BASE}/cycle/transition`);
  await settle(page);
  const carry = await page
    .getByTestId("agent-carryover")
    .textContent()
    .catch(() => null);
  notes.push(`[${label}] transition carry-over note: ${carry?.trim()}`);
  await page.screenshot({
    path: `${OUT}/${label}-transition.png`,
    fullPage: true,
  });

  await page.goto(`${BASE}/settings`);
  await settle(page);
  await page.click('button:has-text("API Reference")');
  await settle(page);
  await page.getByTestId("mcp-reference").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${OUT}/${label}-settings-reference.png`,
    fullPage: true,
  });
  await ctx.close();
}

await shots("phone-390", {
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
  deviceScaleFactor: 2,
});
await shots("desktop-1280", { viewport: { width: 1280, height: 900 } });
await browser.close();

writeFileSync(
  `${OUT}/report.json`,
  JSON.stringify({ base: BASE, notes, problems }, null, 2),
);
for (const n of notes) console.log(n);
console.log(
  problems.length
    ? `\n${problems.length} problem(s):\n${problems.join("\n")}`
    : "\nNo problems.",
);
process.exit(problems.length ? 1 : 0);
