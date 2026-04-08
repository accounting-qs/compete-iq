"""Declarative base — no settings dependency, safe to import from migrations/env.py."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
