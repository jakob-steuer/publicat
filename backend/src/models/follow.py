import datetime
import uuid
from sqlalchemy import Column, String, DateTime, Float
from .base import Base

class Follow(Base):
    __tablename__ = "follows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String, nullable=False) # "author", "venue", "keyword"
    entity_value = Column(String, nullable=False) # The actual ID (e.g. S2 authorId) or name
    display_name = Column(String, nullable=True) # Human readable name
    boost_value = Column(Float, nullable=False, default=0.15)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
