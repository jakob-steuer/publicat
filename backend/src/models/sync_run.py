import datetime
import uuid

from sqlalchemy import JSON, Column, DateTime, Integer, String

from .base import Base


class SyncRun(Base):
    """One row per sync job: what ran, how long, what it found, whether it was complete."""

    __tablename__ = "sync_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job = Column(String, nullable=False)
    status = Column(String, nullable=False, default="running")  # running | complete | partial | aborted | error
    days_back = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    errors = Column(Integer, nullable=False, default=0)
    counters = Column(JSON, nullable=False, default=dict)
    message = Column(String, nullable=True)
