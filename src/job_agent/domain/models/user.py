from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr


class UserTier(str, Enum):
    free = "free"
    pro = "pro"


class User(BaseModel):
    """Authenticated user. Multi-tenant root — every domain object references this id."""

    id: uuid.UUID
    email: EmailStr
    google_sub: str
    tier: UserTier = UserTier.pro
    is_active: bool = True
    created_at: datetime
