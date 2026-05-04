"""Add user_resumes table

Revision ID: 002
Revises: 001
Create Date: 2026-05-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("file_ext", sa.String(16), nullable=False, server_default=".docx"),
        sa.Column("file_data", sa.LargeBinary, nullable=False),
        sa.Column("resume_text", sa.Text, nullable=False, server_default=""),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_resumes_user_id", "user_resumes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_resumes_user_id", "user_resumes")
    op.drop_table("user_resumes")
