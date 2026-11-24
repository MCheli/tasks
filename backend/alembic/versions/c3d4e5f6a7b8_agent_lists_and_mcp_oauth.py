"""agent lists (task owner, agent fields, notes log) and MCP OAuth storage

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-11-23 18:00:00.000000

Every existing task becomes owner='human' (the column's default), so nothing created
through the existing API or UI changes meaning. No rows are touched otherwise.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- tasks: owner dimension + agent fields -------------------------------------------
    op.add_column(
        "tasks",
        sa.Column("owner", sa.String(length=10), server_default="human", nullable=False),
    )
    op.add_column("tasks", sa.Column("source", sa.String(length=200), nullable=True))
    op.add_column("tasks", sa.Column("link", sa.String(length=2000), nullable=True))
    op.add_column("tasks", sa.Column("agent_status", sa.String(length=20), nullable=True))
    op.create_check_constraint("ck_tasks_owner", "tasks", "owner IN ('human','agent')")
    op.create_check_constraint(
        "ck_tasks_agent_status",
        "tasks",
        "agent_status IS NULL OR agent_status IN ('open','in_progress','blocked','done')",
    )
    op.create_index(
        "ix_tasks_cycle_owner", "tasks", ["cycle_id", "owner", "deleted_at", "status"], unique=False
    )

    # --- task_notes: timestamped log per lineage -----------------------------------------
    op.create_table(
        "task_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("persistent_task_id", sa.UUID(), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_notes_lineage",
        "task_notes",
        ["user_id", "persistent_task_id", "created_at"],
        unique=False,
    )

    # --- MCP connector OAuth storage -----------------------------------------------------
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_name", sa.String(length=200), nullable=True),
        sa.Column("info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("client_id"),
    )
    op.create_table(
        "mcp_oauth_codes",
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.String(length=200), nullable=False),
        sa.Column("scopes", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_hash"),
    )
    op.create_table(
        "mcp_oauth_tokens",
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("pair_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("scopes", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_mcp_oauth_tokens_pair", "mcp_oauth_tokens", ["pair_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mcp_oauth_tokens_pair", table_name="mcp_oauth_tokens")
    op.drop_table("mcp_oauth_tokens")
    op.drop_table("mcp_oauth_codes")
    op.drop_table("mcp_oauth_clients")
    op.drop_index("ix_task_notes_lineage", table_name="task_notes")
    op.drop_table("task_notes")
    op.drop_index("ix_tasks_cycle_owner", table_name="tasks")
    op.drop_constraint("ck_tasks_agent_status", "tasks", type_="check")
    op.drop_constraint("ck_tasks_owner", "tasks", type_="check")
    op.drop_column("tasks", "agent_status")
    op.drop_column("tasks", "link")
    op.drop_column("tasks", "source")
    op.drop_column("tasks", "owner")
