"""The Tasks MCP server: tools over the two lists (personal, professional) and their two parts
(Mark's own "human" items and the agents' follow-up items).

Each tool runs in its own database session for the user the bearer token belongs to. Output
is kept compact: one flat dict per task, with the notes log only on get_task.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.mcp import db as mcp_db
from app.mcp.oauth import SCOPE, TasksAccessToken, provider, resource_url
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.services import task_service
from app.services.task_serializer import to_task_out_many

logger = logging.getLogger("tasks.mcp")

ListName = Literal["personal", "professional"]
OwnerFilter = Literal["human", "agent", "all"]
Owner = Literal["human", "agent"]
StatusFilter = Literal["open", "in_progress", "blocked", "done", "completed", "canceled"]
# What a caller may set. done/completed mean the same; canceled is for Mark's own items.
SettableStatus = Literal["open", "in_progress", "blocked", "done", "completed", "canceled"]

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)

INSTRUCTIONS = """\
Mark's Tasks app. Two lists, "personal" and "professional"; each has two parts (owner): \
"human" is Mark's own to-do list, "agent" is the follow-up list that Claude agents use to \
track their own work (security findings, work underway across threads, things not finished). \
Create agent items for work you are tracking; only add to Mark's own list when he asks. Agent \
items have a status (open, in_progress, blocked, done), a source (which routine, thread or \
session made it), an optional link, and a notes log (add_note) for timestamped progress \
entries. Tasks are referred to by their id or by their #number (display_id). Done agent items \
show as completed in the app. A new cycle starts every week or two; open agent items carry \
over automatically.\
"""


def build_auth_settings() -> AuthSettings:
    base = str(settings.PUBLIC_URL).rstrip("/")
    return AuthSettings(
        issuer_url=base,  # type: ignore[arg-type]
        resource_server_url=resource_url(),  # type: ignore[arg-type]
        # API keys are issued outside OAuth and carry no resource indicator of their own;
        # the verifier stamps the resource itself, so the middleware check isn't needed.
        validate_token_resource=False,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
        ),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=[SCOPE],
    )


mcp = MCPServer(
    name="tasks",
    title="Tasks",
    instructions=INSTRUCTIONS,
    version="1.0.0",
    auth_server_provider=provider if settings.mcp_enabled else None,
    auth=build_auth_settings() if settings.mcp_enabled else None,
    log_level="WARNING",
)


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def current_token() -> TasksAccessToken:
    tok = get_access_token()
    if not isinstance(tok, TasksAccessToken):
        raise ToolError("Not authenticated")
    return tok


async def _user(db: AsyncSession, tok: TasksAccessToken) -> User:
    user = await db.get(User, tok.user_id)
    if user is None:
        raise ToolError("The token's user no longer exists")
    return user


def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def compact(t: TaskOut) -> dict[str, Any]:
    """One task, compact. `status` is the agent status for agent items (open, in_progress,
    blocked, done; canceled if canceled), the app status for Mark's items."""
    status = t.status
    if t.owner == "agent" and t.status != "canceled":
        status = t.agent_status or ("done" if t.status == "completed" else "open")
    out = {
        "id": str(t.id),
        "number": t.display_id,
        "title": t.title,
        "list": None,  # filled by the caller (needs the cycle's category)
        "owner": t.owner,
        "status": status,
        "updated_at": _fmt(t.updated_at),
    }
    if t.owner == "agent":
        out["source"] = t.source
        out["link"] = t.link
    if t.notes:
        out["notes"] = t.notes
    if t.note_count:
        out["note_count"] = t.note_count
    if t.completed_at:
        out["completed_at"] = _fmt(t.completed_at)
    if t.push_forward_count:
        out["carried_over"] = t.push_forward_count
    return {k: v for k, v in out.items() if v is not None or k in ("list",)}


async def _category_of(db: AsyncSession, cycle_id: UUID) -> str:
    from app.models.cycle import Cycle

    cycle = await db.get(Cycle, cycle_id)
    return cycle.category if cycle else "?"


async def _with_list(db: AsyncSession, outs: list[TaskOut]) -> list[dict]:
    cats: dict[UUID, str] = {}
    result = []
    for t in outs:
        if t.cycle_id not in cats:
            cats[t.cycle_id] = await _category_of(db, t.cycle_id)
        d = compact(t)
        d["list"] = cats[t.cycle_id]
        result.append(d)
    return result


async def _resolve(db: AsyncSession, user: User, task: str):
    """A task by UUID or by #number (with or without the #)."""
    ref = task.strip().lstrip("#")
    try:
        return await task_service._get_user_task(db, user, UUID(ref))
    except ValueError:
        pass
    if ref.isdigit():
        return await task_service.find_by_display_id(db, user, int(ref))
    raise ToolError(f"'{task}' is neither a task id nor a #number")


def _http_to_tool(exc: HTTPException) -> ToolError:
    return ToolError(str(exc.detail))


def _map_status(status: str | None, owner: str) -> TaskUpdate:
    """Translate the caller's status word into the app's fields."""
    upd = TaskUpdate()
    if status is None:
        return upd
    if owner == "agent":
        if status in ("done", "completed"):
            upd.agent_status = "done"
        elif status == "canceled":
            upd.status = "canceled"
        elif status in ("open", "in_progress", "blocked"):
            upd.agent_status = status  # type: ignore[assignment]
        return upd
    if status in ("done", "completed"):
        upd.status = "completed"
    elif status in ("open", "canceled"):
        upd.status = status  # type: ignore[assignment]
    else:
        raise ToolError("Mark's own items only take open, completed or canceled")
    return upd


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def list_tasks(
    list: ListName | None = None,
    owner: OwnerFilter = "all",
    status: StatusFilter | None = None,
    query: str | None = None,
    include_done: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """List tasks in the current cycle(s).

    list: "personal" or "professional"; omit for both. owner: "human" (Mark's own list),
    "agent" (the agents' follow-up list) or "all" (default). status: open, in_progress,
    blocked, done (agent statuses; done = completed) or completed / canceled. query matches
    title, notes, source and link. Done and canceled items are left out unless include_done is
    true or status asks for them. Returns compact rows: id, number, title, list, owner, status,
    source/link (agent items), notes, note_count, updated_at.
    """
    tok = current_token()
    async with mcp_db.session() as db:
        user = await _user(db, tok)
        try:
            rows = await task_service.list_tasks(
                db,
                user,
                category=list,
                owner=owner,
                status_filter=status,
                query=query,
                include_done=include_done,
                limit=max(1, min(limit, 200)),
            )
        except HTTPException as exc:
            raise _http_to_tool(exc) from exc
        outs = await to_task_out_many(db, user, rows)
        items = await _with_list(db, outs)
    return {"count": len(items), "tasks": items}


@mcp.tool(annotations=READ_ONLY)
async def get_task(task: str) -> dict[str, Any]:
    """One task in full, by id or #number: all fields plus its notes log (timestamped entries
    with author) and how many cycles it has been carried over."""
    tok = current_token()
    async with mcp_db.session() as db:
        user = await _user(db, tok)
        try:
            row = await _resolve(db, user, task)
            detail = await task_service.get_task_with_lineage(db, user, row.id)
        except HTTPException as exc:
            raise _http_to_tool(exc) from exc
        d = (await _with_list(db, [detail.task]))[0]
    d["created_at"] = _fmt(detail.task.created_at)
    d["notes_log"] = [
        {"at": _fmt(n.created_at), "author": n.author, "body": n.body} for n in detail.notes_log
    ]
    return d


@mcp.tool(annotations=WRITES)
async def create_task(
    title: str,
    list: ListName,
    owner: Owner = "agent",
    status: Literal["open", "in_progress", "blocked", "done"] = "open",
    source: str | None = None,
    link: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a task in the current cycle of a list.

    owner defaults to "agent": an item on the agents' follow-up list, which is where work you
    are tracking belongs. Use owner "human" only when Mark asked for something on his own list.
    source: which routine, thread or session this comes from (defaults to the connector's
    name). link: a PR, repo or URL. notes: free text description. status applies to agent
    items. The app has no due dates.
    """
    tok = current_token()
    payload = TaskCreate(
        category=list,
        title=title.strip(),
        notes=notes,
        owner=owner,
        source=(source or tok.label) if owner == "agent" else source,
        link=link,
        agent_status=status if owner == "agent" else None,
    )
    async with mcp_db.session() as db:
        user = await _user(db, tok)
        try:
            out = await task_service.create_task(db, user, payload)
        except HTTPException as exc:
            raise _http_to_tool(exc) from exc
        await db.commit()
        d = (await _with_list(db, [out]))[0]
    return d


@mcp.tool(annotations=WRITES)
async def update_task(
    task: str,
    title: str | None = None,
    status: SettableStatus | None = None,
    source: str | None = None,
    link: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Change a task's fields, by id or #number. Only the fields given are changed.

    status for agent items: open, in_progress, blocked or done (done completes it; any other
    value reopens a done item). For Mark's own items: open, completed or canceled. notes
    replaces the free-text description; use add_note for a log entry instead.
    """
    tok = current_token()
    async with mcp_db.session() as db:
        user = await _user(db, tok)
        try:
            row = await _resolve(db, user, task)
            upd = _map_status(status, row.owner)
            upd.title = title.strip() if title else None
            upd.source = source
            upd.link = link
            upd.notes = notes
            out = await task_service.update_task(db, user, row.id, upd)
        except HTTPException as exc:
            raise _http_to_tool(exc) from exc
        await db.commit()
        d = (await _with_list(db, [out]))[0]
    return d


async def _complete_or_reopen(task: str, note: str | None, reopen: bool) -> dict[str, Any]:
    tok = current_token()
    async with mcp_db.session() as db:
        user = await _user(db, tok)
        try:
            row = await _resolve(db, user, task)
            if row.owner == "agent":
                upd = TaskUpdate(agent_status="open" if reopen else "done")
            else:
                upd = TaskUpdate(status="open" if reopen else "completed")
            out = await task_service.update_task(db, user, row.id, upd)
            if note and note.strip():
                _, out = await task_service.add_note(db, user, row.id, note.strip(), tok.label)
        except HTTPException as exc:
            raise _http_to_tool(exc) from exc
        await db.commit()
        d = (await _with_list(db, [out]))[0]
    return d


@mcp.tool(annotations=WRITES)
async def complete_task(task: str, note: str | None = None) -> dict[str, Any]:
    """Mark a task done (agent items: status done; Mark's items: completed), by id or #number.
    An optional note is appended to the notes log."""
    return await _complete_or_reopen(task, note, reopen=False)


@mcp.tool(annotations=WRITES)
async def reopen_task(task: str, note: str | None = None) -> dict[str, Any]:
    """Reopen a done, completed or canceled task, by id or #number. Agent items go back to
    status open. An optional note is appended to the notes log."""
    return await _complete_or_reopen(task, note, reopen=True)


@mcp.tool(annotations=WRITES)
async def add_note(task: str, body: str, author: str | None = None) -> dict[str, Any]:
    """Append a timestamped entry to a task's notes log, by id or #number. author defaults to
    the connector's name; pass the routine, thread or session name when you have one. Returns
    the task with its full notes log."""
    tok = current_token()
    if not body.strip():
        raise ToolError("body is empty")
    async with mcp_db.session() as db:
        user = await _user(db, tok)
        try:
            row = await _resolve(db, user, task)
            _, out = await task_service.add_note(
                db, user, row.id, body.strip(), author or tok.label
            )
            notes_log = await task_service.list_notes(db, user, row.persistent_task_id)
        except HTTPException as exc:
            raise _http_to_tool(exc) from exc
        await db.commit()
        d = (await _with_list(db, [out]))[0]
    d["notes_log"] = [
        {"at": _fmt(n.created_at), "author": n.author, "body": n.body} for n in notes_log
    ]
    return d
