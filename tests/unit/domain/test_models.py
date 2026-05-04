"""Unit tests for domain models — pure Python, zero I/O."""

import uuid
from datetime import UTC, datetime

from job_agent.domain.models.application import Application, ApplicationStatus
from job_agent.domain.models.job import Job
from job_agent.domain.models.profile import Profile, StackAlignment
from job_agent.domain.models.user import User, UserTier


def _now() -> datetime:
    return datetime.now(UTC)


class TestUser:
    def test_defaults(self) -> None:
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            google_sub="sub123",
            created_at=_now(),
        )
        assert user.tier == UserTier.pro
        assert user.is_active is True

    def test_tier_enum(self) -> None:
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            google_sub="sub123",
            tier=UserTier.free,
            created_at=_now(),
        )
        assert user.tier == UserTier.free


class TestProfile:
    def test_empty_defaults(self) -> None:
        uid = uuid.uuid4()
        now = _now()
        profile = Profile(id=uuid.uuid4(), user_id=uid, created_at=now, updated_at=now)
        assert profile.skills == []
        assert profile.experience == []
        assert isinstance(profile.stack_alignment, StackAlignment)

    def test_serializes_to_json(self) -> None:
        uid = uuid.uuid4()
        now = _now()
        profile = Profile(
            id=uuid.uuid4(),
            user_id=uid,
            created_at=now,
            updated_at=now,
            full_name="Alex",
            skills=["C#", ".NET"],
        )
        data = profile.model_dump(mode="json")
        assert data["full_name"] == "Alex"
        assert "C#" in data["skills"]


class TestApplication:
    def test_default_status(self) -> None:
        uid = uuid.uuid4()
        app = Application(
            id=uuid.uuid4(),
            user_id=uid,
            job_id=uuid.uuid4(),
            ats_type="greenhouse",
            created_at=_now(),
        )
        assert app.status == ApplicationStatus.queued

    def test_all_statuses_are_strings(self) -> None:
        for status in ApplicationStatus:
            assert isinstance(status.value, str)


class TestJob:
    def test_fields(self) -> None:
        job = Job(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            source="greenhouse",
            external_id="gh-123",
            content_hash="abc123",
            title="Senior Software Engineer",
            company="Acme Corp",
            location="Remote, US",
            url="https://example.com/jobs/1",
            description="We are looking for ...",
            discovered_at=_now(),
        )
        assert job.remote is False
        assert job.ats_type == "unknown"
