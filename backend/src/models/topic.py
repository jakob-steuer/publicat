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
    # Hard filter: papers mentioning any of these (comma separated) are dropped for this topic.
    exclude_keywords = Column(String, nullable=True)
    # Local SPECTER2 embedding of the description (legacy; only a fallback now).
    embedding = Column(JSON, nullable=True)
    # Topic vector in Semantic Scholar's specter_v2 space, built from seed papers,
    # the user's positive votes, or S2 search results. This is what papers are compared to.
    prior_vector = Column(JSON, nullable=True)
    # [{"paperId": "...", "title": "..."}] papers the user picked as examples of the topic.
    seed_papers = Column(JSON, nullable=True)
    # arXiv OAI sets to harvest for this topic, e.g. ["q-bio", "cs"].
    arxiv_categories = Column(JSON, nullable=True)
    priority = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
