#!/bin/sh
set -e

# Strip the +asyncpg driver suffix so a sync probe works.
SYNC_URL=$(echo "$TASKS_DATABASE_URL" | sed 's|postgresql+asyncpg|postgresql|')

echo "[entrypoint] waiting for database..."
i=0
until python - <<PY 2>/dev/null
import asyncio, asyncpg, os, sys
url = os.environ["TASKS_DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
async def go():
    c = await asyncpg.connect(url)
    await c.close()
asyncio.run(go())
PY
do
  i=$((i+1))
  if [ "$i" -ge 60 ]; then
    echo "[entrypoint] database not reachable after 60s; failing"
    exit 1
  fi
  sleep 1
done
echo "[entrypoint] database ready"

# Run Alembic migrations from the backend dir (where alembic.ini lives).
cd /app/backend
echo "[entrypoint] running alembic upgrade head"
alembic upgrade head

echo "[entrypoint] starting app: $*"
exec "$@"
