"""Initial schema — users, profiles, jobs, matches, applications, llm_calls, credentials, events, system_state.

Revision ID: 001
Revises:
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("google_sub", sa.String(255), nullable=False, unique=True),
        sa.Column("tier", sa.Enum("free", "pro", name="user_tier_enum"), nullable=False, server_default="pro"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_text", sa.Text, nullable=False, server_default=""),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=False, server_default=""),
        sa.Column("remote", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("ats_type", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("salary_min", sa.Integer, nullable=True),
        sa.Column("salary_max", sa.Integer, nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_job_user_hash"),
    )

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("embedding_score", sa.Float, nullable=False),
        sa.Column("llm_score", sa.Float, nullable=False),
        sa.Column("hard_requirement_score", sa.Float, nullable=False),
        sa.Column("final_score", sa.Float, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("flags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("ats_type", sa.String(64), nullable=False),
        sa.Column("submission_url", sa.Text, nullable=False, server_default=""),
        sa.Column("resume_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("cover_letter_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("form_fields_snapshot", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ats_confirmation_id", sa.String(255), nullable=True),
        sa.Column("screenshot_path", sa.Text, nullable=True),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("encrypted_blob", sa.LargeBinary, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "system_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True),
        sa.Column("paused", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("daily_application_cap", sa.Integer, nullable=False, server_default="8"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Indexes for common query patterns
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_matches_user_final_score", "matches", ["user_id", "final_score"])
    op.create_index("ix_applications_user_status", "applications", ["user_id", "status"])
    op.create_index("ix_llm_calls_user_created", "llm_calls", ["user_id", "created_at"])
    op.create_index("ix_events_user_occurred", "events", ["user_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("system_state")
    op.drop_table("events")
    op.drop_table("credentials")
    op.drop_table("llm_calls")
    op.drop_table("applications")
    op.drop_table("matches")
    op.drop_table("jobs")
    op.drop_table("profiles")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_tier_enum")
