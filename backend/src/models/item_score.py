from sqlalchemy import Column, String, Float, JSON, ForeignKey, PrimaryKeyConstraint, Integer, DateTime
from .base import Base

class ItemScore(Base):
    __tablename__ = "item_scores"

    item_id = Column(String, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)

    # Probability from the topic prior alone (description / seed papers), 0..1.
    semantic_score = Column(Float, nullable=False, default=0.0)
    llm_relevance_score = Column(Float, nullable=True)
    follow_boost = Column(Float, nullable=False, default=0.0)
    # Probability from the learned per-topic ranker, 0..1. This orders the feed.
    final_score = Column(Float, nullable=False, default=0.0)
    user_vote = Column(Integer, nullable=True) # 2: Star, 1: Up, 0: Neutral, -1: Down
    voted_at = Column(DateTime(timezone=True), nullable=True)

    reasons = Column(JSON, nullable=False, default=list)

    __table_args__ = (
        PrimaryKeyConstraint('item_id', 'topic_id'),
    )
