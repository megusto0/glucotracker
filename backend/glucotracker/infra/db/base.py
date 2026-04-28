"""SQLAlchemy declarative base shared by database models and migrations."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy 2.0 declarative models."""
