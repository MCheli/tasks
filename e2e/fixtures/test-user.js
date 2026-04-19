// Test user credentials sourced from env at test time. The CI workflow
// pipes them in from GitHub Actions secrets; locally they come from the
// project's .env (the same Claudius user as the rest of the dev setup).
export const TEST_EMAIL = process.env.TASKS_TEST_USER_EMAIL || 'admin@tallied.dev'
export const TEST_PASSWORD =
  process.env.TASKS_TEST_USER_PASSWORD || 'tallied-admin-change-me'
