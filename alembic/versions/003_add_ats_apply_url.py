"""Add ats_apply_url to jobs table

Revision ID: 003
Revises: 002
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("ats_apply_url", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("jobs", "ats_apply_url")
