# Testing Strategy

Three layers of testing, each with a clear purpose. All three are required for full coverage.

| Layer | Tool | Purpose | Where |
|---|---|---|---|
| Unit | pytest | Business logic in services — transitions, display-ID allocation, push-forward calc | `backend/tests/unit/` |
| API | pytest + httpx | Endpoint contracts, auth scoping, HTTP semantics | `backend/tests/api/` |
| End-to-end | Playwright MCP | User flows through the real UI in a real browser | `e2e/` at repo root |

Tests run automatically in CI on every PR. Agent should run them locally before every commit.

## 1. Unit Tests

Test service-layer functions in isolation. Mock the DB only when necessary (prefer a real test DB, it's fast enough with PostgreSQL in Docker).

### Test DB Setup: `backend/tests/conftest.py`

```python
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.db.base import Base
from app.models import user, cycle, task  # force-import all models
from app.core.security import hash_password
from app.models.user import User

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/cycle_todo_test"

@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db(engine):
    """Fresh session per test, rolls back at end."""
    conn = await engine.connect()
    trans = await conn.begin()
    SessionLocal = async_sessionmaker(bind=conn, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await trans.rollback()
    await conn.close()

@pytest_asyncio.fixture
async def test_user(db):
    user = User(email="alice@test.local", hashed_password=hash_password("secret"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@pytest_asyncio.fixture
async def other_user(db):
    user = User(email="bob@test.local", hashed_password=hash_password("secret"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

### Example: `backend/tests/unit/test_display_id.py`

```python
import pytest
from app.services.task_service import allocate_display_id

@pytest.mark.asyncio
async def test_display_id_starts_at_1(db, test_user):
    assert await allocate_display_id(db, test_user.id) == 1

@pytest.mark.asyncio
async def test_display_id_increments(db, test_user):
    a = await allocate_display_id(db, test_user.id)
    b = await allocate_display_id(db, test_user.id)
    c = await allocate_display_id(db, test_user.id)
    assert [a, b, c] == [1, 2, 3]

@pytest.mark.asyncio
async def test_display_id_is_per_user(db, test_user, other_user):
    assert await allocate_display_id(db, test_user.id) == 1
    assert await allocate_display_id(db, other_user.id) == 1  # independent
    assert await allocate_display_id(db, test_user.id) == 2
```

### Example: `backend/tests/unit/test_cycle_service.py`

```python
import pytest
from app.services import cycle_service, task_service
from app.schemas.task import TaskCreate

@pytest.mark.asyncio
async def test_transition_forward(db, test_user):
    # Create a task
    t1 = await task_service.create_task(db, test_user, TaskCreate(category="personal", title="Task A"))
    cycle = await cycle_service.get_or_create_current_cycle(db, test_user, "personal")

    # Transition with forward
    result = await cycle_service.transition_cycle(
        db, test_user, cycle.id,
        [{"persistent_task_id": t1.persistent_task_id, "action": "forward"}]
    )

    # Old cycle closed
    assert result["old_cycle"].ended_at is not None
    # New cycle opened
    assert result["new_cycle"].ended_at is None
    # Forwarded task carries persistent id, new row id
    forwarded = result["new_cycle_tasks"][0]
    assert forwarded.persistent_task_id == t1.persistent_task_id
    assert forwarded.id != t1.id
    assert forwarded.previous_task_id == t1.id

@pytest.mark.asyncio
async def test_push_forward_count(db, test_user):
    # Create, forward three times, count should be 3
    ...
```

Write tests for: cycle auto-creation, transition with all three actions, transition fails if action list incomplete, soft delete removes entire lineage, reorder updates positions correctly, display ID uniqueness enforced per user.

## 2. API Tests

Test HTTP-layer behavior: auth cookies, status codes, Pydantic validation, user isolation.

### Setup: `backend/tests/api/conftest.py`

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import get_db

@pytest_asyncio.fixture
async def client(db):
    async def _get_db():
        yield db
    app.dependency_overrides[get_db] = _get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def authed_client(client, test_user):
    resp = await client.post("/api/auth/login", json={"email": test_user.email, "password": "secret"})
    assert resp.status_code == 200
    # Cookies are kept by the client automatically
    return client
```

### Example: `backend/tests/api/test_auth.py`

```python
import pytest

@pytest.mark.asyncio
async def test_login_success(client, test_user):
    resp = await client.post("/api/auth/login", json={"email": test_user.email, "password": "secret"})
    assert resp.status_code == 200
    assert "session" in resp.cookies
    assert resp.json()["user"]["email"] == test_user.email

@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    resp = await client.post("/api/auth/login", json={"email": test_user.email, "password": "nope"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_me_returns_user(authed_client, test_user):
    resp = await authed_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == test_user.email
```

### Example: `backend/tests/api/test_tasks.py`

```python
import pytest

@pytest.mark.asyncio
async def test_create_task(authed_client):
    resp = await authed_client.post("/api/tasks", json={"category": "personal", "title": "Hello"})
    assert resp.status_code == 201
    task = resp.json()["task"]
    assert task["title"] == "Hello"
    assert task["status"] == "open"
    assert task["display_id"] == 1

@pytest.mark.asyncio
async def test_cannot_see_other_users_tasks(client, test_user, other_user):
    # Log in as test_user, create a task
    await client.post("/api/auth/login", json={"email": test_user.email, "password": "secret"})
    task_resp = await client.post("/api/tasks", json={"category": "personal", "title": "Mine"})
    task_id = task_resp.json()["task"]["id"]

    # Log out, log in as other_user
    await client.post("/api/auth/logout")
    await client.post("/api/auth/login", json={"email": other_user.email, "password": "secret"})

    # Try to access the first user's task
    resp = await client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_cycle_transition_full_flow(authed_client):
    # Create three tasks
    t1 = (await authed_client.post("/api/tasks", json={"category": "personal", "title": "A"})).json()["task"]
    t2 = (await authed_client.post("/api/tasks", json={"category": "personal", "title": "B"})).json()["task"]
    t3 = (await authed_client.post("/api/tasks", json={"category": "personal", "title": "C"})).json()["task"]

    # Get current cycle
    cycle = (await authed_client.get("/api/cycles/current", params={"category": "personal"})).json()["cycle"]

    # Transition: forward A, complete B, cancel C
    resp = await authed_client.post(f"/api/cycles/{cycle['id']}/transition", json={
        "actions": [
            {"persistent_task_id": t1["persistent_task_id"], "action": "forward"},
            {"persistent_task_id": t2["persistent_task_id"], "action": "complete"},
            {"persistent_task_id": t3["persistent_task_id"], "action": "cancel"},
        ]
    })
    assert resp.status_code == 201

    # New cycle should have 1 open task (A)
    new = (await authed_client.get("/api/cycles/current", params={"category": "personal"})).json()
    assert len(new["tasks"]["open"]) == 1
    assert new["tasks"]["open"][0]["title"] == "A"
```

Coverage expectation: every endpoint has at least a success and a failure test. Every auth-required endpoint has an unauthenticated-rejection test. Every user-scoped endpoint has a cross-user isolation test.

## 3. End-to-End Tests via Playwright MCP

**How Claude uses this:** The agent has access to Playwright MCP tooling. During implementation, the agent navigates to the running app (`http://localhost:5173` in dev, `http://localhost:8000` when serving built assets), takes screenshots, and verifies behavior through real browser interaction. **This is not a replacement for a standing test suite — it's a tool for the agent to verify its own work.**

### Setup for the Agent

The agent should install Playwright MCP per the instructions at `https://github.com/microsoft/playwright-mcp` (or equivalent — check the current recommended MCP server for browser automation). A typical `claude mcp add` command:

```bash
claude mcp add playwright npx -- @playwright/mcp
```

Verify by asking Claude Code to "navigate to localhost:5173 and take a screenshot" — it should produce an image.

### Standing E2E Suite

In addition to Claude's in-session browser use, commit a real Playwright test suite at `e2e/` that can run headless in CI.

```
e2e/
├── package.json
├── playwright.config.js
├── tests/
│   ├── auth.spec.js
│   ├── task-crud.spec.js
│   └── cycle-transition.spec.js
└── fixtures/
    └── test-user.js
```

### `e2e/package.json`

```json
{
  "name": "cycle-todo-e2e",
  "private": true,
  "scripts": {
    "test": "playwright test",
    "test:ui": "playwright test --ui",
    "test:debug": "playwright test --debug"
  },
  "devDependencies": {
    "@playwright/test": "^1.42.0"
  }
}
```

### `e2e/playwright.config.js`

```javascript
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 14'] } },
  ],
})
```

### Example: `e2e/tests/auth.spec.js`

```javascript
import { test, expect } from '@playwright/test'

test('login with test user', async ({ page }) => {
  await page.goto('/login')
  await page.fill('input[type="email"]', process.env.TEST_USER_EMAIL)
  await page.fill('input[type="password"]', process.env.TEST_USER_PASSWORD)
  await page.click('button:has-text("Sign in")')
  await expect(page).toHaveURL('/cycle')
})

test('logout clears session', async ({ page }) => {
  await page.goto('/login')
  // ... login
  await page.click('[aria-label="Logout"]')
  await expect(page).toHaveURL('/login')
})
```

### Example: `e2e/tests/task-crud.spec.js`

```javascript
import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.fill('input[type="email"]', process.env.TEST_USER_EMAIL)
  await page.fill('input[type="password"]', process.env.TEST_USER_PASSWORD)
  await page.click('button:has-text("Sign in")')
})

test('create and complete a task', async ({ page }) => {
  await page.fill('input[placeholder="Add a task…"]', 'Write tests')
  await page.keyboard.press('Enter')
  await expect(page.locator('text=Write tests')).toBeVisible()

  await page.click('button[aria-label="Mark complete"]')
  await expect(page.locator('text=Completed (1)')).toBeVisible()
})
```

### Example: `e2e/tests/cycle-transition.spec.js`

Cover the full transition workflow: create tasks, navigate to transition, toggle actions, confirm, verify new cycle state.

## Test User Credentials

All test layers reference the same test user via environment variables:

```
TEST_USER_EMAIL=claudius@markcheli.com
TEST_USER_PASSWORD=<from ~/repos/tallied/.env>
```

The exact values for the Claudius user are in Mark's Tallied `.env` — the agent should read them from `~/repos/tallied/.env` once and set them in this project's `.env` to keep consistency across both apps. Do not commit them.

## Coverage Targets

- **Backend unit + API:** ≥85% line coverage on `app/services/` and `app/routers/`. Generate coverage reports in CI.
- **E2E:** three user journeys (login, CRUD, transition) minimum. Add more for History view when it's built.

## Running Tests

Local:
```bash
# Backend
cd backend
pytest                  # all
pytest tests/unit       # just units
pytest -k "transition"  # name match

# E2E (requires app running at localhost:8000)
cd e2e
npx playwright install chromium  # first time only
npm test
```

CI: see `.github/workflows/ci.yml` in `DEPLOYMENT.md`.

## Anti-Patterns (Don't Do)

- Do not mock the database with in-memory fakes. PostgreSQL in Docker is fast enough.
- Do not write tests that assert on UI colors/padding. Test behavior, not appearance.
- Do not skip tests to make CI green. Fix the bug, fix the flake, or delete the test.
- Do not write a test after the bug ships. Tests for regressions get written with the fix, in the same commit.
