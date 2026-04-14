"""Shared utilities for all model modules."""

import uuid

# Common imports re-exported for convenience in model files
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def gen_uuid():
    return str(uuid.uuid4())
