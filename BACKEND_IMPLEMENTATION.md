# Backend Implementation

FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic V2. The canonical reference for patterns is `~/repos/tallied/backend/`. Read that first.

## Entry Point: `app/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.config import settings
from app.db.session import engine
from app.routers import auth, cycles, tasks, health
from app.services.seed import ensure_test_user

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await ensure_test_user()
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(
    title="Cycle Todo",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.ENABLE_DOCS else None,
    openapi_url="/api/openapi.json" if settings.ENABLE_DOCS else None,
)

# API routes
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(cycles.router, prefix="/api/cycles", tags=["cycles"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])

# Static files (production build of Vue app)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Any non-API path returns index.html for Vue Router to handle
        return FileResponse(static_dir / "index.html")
```

## Configuration: `app/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime
    ENV: str = "development"
    ENABLE_DOCS: bool = True

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host:5432/db

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # True in prod
    COOKIE_DOMAIN: str | None = None

    # Test user (bootstrapped on startup if set)
    TEST_USER_EMAIL: str | None = None
    TEST_USER_PASSWORD: str | None = None

    # Google OAuth (not wired yet)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

## DB Session: `app/db/session.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

## Base Model: `app/db/base.py`

```python
from sqlalchemy.orm import DeclarativeBase, declared_attr
import re

class Base(DeclarativeBase):
    @declared_attr.directive
    def __tablename__(cls) -> str:
        # CamelCase -> snake_case plural
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        return name if name.endswith('s') else name + 's'
```

## Models — example: `app/models/task.py`

```python
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, CheckConstraint, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.db.base import Base

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    persistent_task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    display_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False)
    previous_task_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cycle: Mapped["Cycle"] = relationship(back_populates="tasks")

    __table_args__ = (
        CheckConstraint("status IN ('open','completed','canceled')", name="ck_tasks_status"),
        UniqueConstraint("user_id", "display_id", name="uq_tasks_user_display_id"),
        Index("ix_tasks_cycle_filter", "cycle_id", "deleted_at", "status", "position"),
        Index("ix_tasks_lineage", "user_id", "persistent_task_id"),
    )
```

Similar structure for `User` and `Cycle`. Follow Tallied's conventions for any ambiguity.

## Pydantic Schemas — example: `app/schemas/task.py`

```python
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    notes: str | None = None

class TaskCreate(TaskBase):
    category: Literal["personal", "professional"]

class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    notes: str | None = None
    status: Literal["open", "completed", "canceled"] | None = None
    position: int | None = Field(None, ge=0)

class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    persistent_task_id: UUID
    display_id: int
    cycle_id: UUID
    previous_task_id: UUID | None
    status: Literal["open", "completed", "canceled"]
    position: int
    push_forward_count: int   # derived, injected by service layer
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    canceled_at: datetime | None
```

## Auth: `app/core/security.py`

```python
from datetime import datetime, timedelta, timezone
from uuid import UUID
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_ctx.verify(password, hashed)

def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> UUID | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        return None
```

## Dependencies: `app/dependencies.py`

```python
from fastapi import Depends, HTTPException, status, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.db.session import get_db
from app.core.security import decode_access_token
from app.models.user import User

async def get_current_user(
    session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_access_token(session)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
```

## Routers — example: `app/routers/tasks.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut
from app.services import task_service

router = APIRouter()

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await task_service.create_task(db, user, payload)
    return {"task": task}

@router.patch("/{task_id}", response_model=dict)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await task_service.update_task(db, user, task_id, payload)
    return {"task": task}

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await task_service.soft_delete_lineage(db, user, task_id)

@router.post("/{task_id}/reorder", response_model=dict)
async def reorder_task(
    task_id: UUID,
    new_position: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tasks = await task_service.reorder_task(db, user, task_id, new_position)
    return {"tasks": tasks}

@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await task_service.get_task_with_lineage(db, user, task_id)
```

## Service Layer Pattern

Services contain all business logic. Routers are thin translators. Example signatures from `app/services/task_service.py`:

```python
async def create_task(db: AsyncSession, user: User, payload: TaskCreate) -> TaskOut: ...
async def update_task(db: AsyncSession, user: User, task_id: UUID, payload: TaskUpdate) -> TaskOut: ...
async def soft_delete_lineage(db: AsyncSession, user: User, task_id: UUID) -> None: ...
async def reorder_task(db: AsyncSession, user: User, task_id: UUID, new_position: int) -> list[TaskOut]: ...
async def get_task_with_lineage(db: AsyncSession, user: User, task_id: UUID) -> dict: ...
async def calculate_push_forward_count(db: AsyncSession, user_id: UUID, persistent_task_id: UUID) -> int: ...
```

And from `app/services/cycle_service.py`:

```python
async def get_or_create_current_cycle(db: AsyncSession, user: User, category: str) -> Cycle: ...
async def transition_cycle(db: AsyncSession, user: User, cycle_id: UUID, actions: list[TransitionAction]) -> dict: ...
async def list_cycles(db: AsyncSession, user: User, category: str, limit: int, offset: int) -> dict: ...
```

### `create_task` implementation outline

```python
async def create_task(db: AsyncSession, user: User, payload: TaskCreate) -> TaskOut:
    cycle = await get_or_create_current_cycle(db, user, payload.category)
    display_id = await allocate_display_id(db, user.id)

    # Compute next position
    max_pos = await db.scalar(
        select(func.coalesce(func.max(Task.position), -1))
        .where(Task.cycle_id == cycle.id, Task.deleted_at.is_(None), Task.status == "open")
    )

    task = Task(
        persistent_task_id=uuid4(),
        display_id=display_id,
        user_id=user.id,
        cycle_id=cycle.id,
        title=payload.title,
        notes=payload.notes,
        status="open",
        position=max_pos + 1,
    )
    db.add(task)
    await db.flush()
    return await to_task_out(db, task)
```

### Display ID allocation

```python
async def allocate_display_id(db: AsyncSession, user_id: UUID) -> int:
    # Upsert + atomic increment
    stmt = text("""
        INSERT INTO display_id_sequences (user_id, next_value)
        VALUES (:user_id, 2)
        ON CONFLICT (user_id) DO UPDATE
          SET next_value = display_id_sequences.next_value + 1
        RETURNING next_value - 1 AS allocated
    """)
    result = await db.execute(stmt, {"user_id": user_id})
    return result.scalar_one()
```

### `transition_cycle` implementation outline

```python
async def transition_cycle(db: AsyncSession, user: User, cycle_id: UUID, actions: list[TransitionAction]) -> dict:
    # 1. Load old cycle with its open tasks, verify ownership and active status
    old_cycle = await db.scalar(
        select(Cycle).where(Cycle.id == cycle_id, Cycle.user_id == user.id, Cycle.ended_at.is_(None))
    )
    if not old_cycle:
        raise HTTPException(404, "Active cycle not found")

    open_tasks = await db.scalars(
        select(Task).where(
            Task.cycle_id == cycle_id,
            Task.deleted_at.is_(None),
            Task.status == "open",
        )
    )
    open_tasks = list(open_tasks)

    # 2. Validate actions cover all open tasks
    action_map = {a.persistent_task_id: a.action for a in actions}
    for t in open_tasks:
        if t.persistent_task_id not in action_map:
            raise HTTPException(400, f"Missing action for task {t.display_id}")

    now = datetime.now(timezone.utc)

    # 3. Apply complete/cancel to old cycle rows
    for t in open_tasks:
        action = action_map[t.persistent_task_id]
        if action == "complete":
            t.status = "completed"
            t.completed_at = now
        elif action == "cancel":
            t.status = "canceled"
            t.canceled_at = now

    # 4. Create new cycle
    new_cycle = Cycle(
        user_id=user.id,
        category=old_cycle.category,
        started_at=now,
    )
    db.add(new_cycle)
    await db.flush()

    # 5. Close old cycle
    old_cycle.ended_at = now
    old_cycle.next_cycle_id = new_cycle.id

    # 6. Create forwarded task rows
    forwarded_tasks = []
    for t in open_tasks:
        if action_map[t.persistent_task_id] == "forward":
            new_task = Task(
                persistent_task_id=t.persistent_task_id,  # SAME persistent ID
                display_id=t.display_id,                  # same display ID
                user_id=user.id,
                cycle_id=new_cycle.id,
                previous_task_id=t.id,
                title=t.title,
                notes=t.notes,
                status="open",
                position=t.position,
            )
            db.add(new_task)
            forwarded_tasks.append(new_task)

    await db.flush()
    return {
        "old_cycle": old_cycle,
        "new_cycle": new_cycle,
        "new_cycle_tasks": forwarded_tasks,
    }
```

## Seeding: `app/services/seed.py`

```python
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.core.security import hash_password
from app.config import settings

async def ensure_test_user():
    if not (settings.TEST_USER_EMAIL and settings.TEST_USER_PASSWORD):
        return
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == settings.TEST_USER_EMAIL))
        if existing:
            return
        user = User(
            email=settings.TEST_USER_EMAIL,
            hashed_password=hash_password(settings.TEST_USER_PASSWORD),
        )
        db.add(user)
        await db.commit()
```

## Alembic Setup

`backend/alembic.ini` — standard, with `sqlalchemy.url` left empty (read from env in `env.py`).

`backend/alembic/env.py` — async-friendly setup:

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from app.config import settings
from app.db.base import Base
from app.models import user, cycle, task  # ensure all models are imported

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

Generate initial migration:
```bash
cd backend
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

## Dependencies: `backend/requirements.txt`

```
fastapi>=0.110
uvicorn[standard]>=0.27
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
alembic>=1.13
pydantic>=2.5
pydantic-settings>=2.1
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7.4
bcrypt>=4.1
httpx>=0.25

# Dev
pytest>=7.4
pytest-asyncio>=0.23
pytest-cov>=4.1
ruff>=0.1
black>=24.1
```

Keep it minimal. Don't add packages unless required.

## Error Handling

Use FastAPI's `HTTPException` with specific status codes. Don't catch and rewrap unless adding useful context. Let Pydantic's 422 flow through for validation errors — don't mask them.

Add an exception handler for uncaught exceptions that logs and returns a sanitized 500:

```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
```

## Logging

Standard Python `logging` configured in `main.py`. In prod, log JSON; in dev, log human-readable. Log every auth failure, every 500, every cycle transition.
