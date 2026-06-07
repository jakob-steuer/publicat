import datetime
import uuid
from sqlalchemy import Column, String, DateTime, Boolean
from .base import Base

class RssFeed(Base):
    __tablename__ = "rss_feeds"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
