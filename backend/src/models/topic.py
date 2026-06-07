import uuid
import datetime
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer
from .base import Base

class Topic(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, default="1", index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    keywords = Column(String, nullable=True)
    embedding = Column(JSON, nullable=True) # Storing as JSON list of floats
    priority = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
