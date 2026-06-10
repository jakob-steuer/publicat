from sqlalchemy import Column, String, Float, JSON, ForeignKey, PrimaryKeyConstraint, Integer
from .base import Base

class ItemScore(Base):
    __tablename__ = "item_scores"

    item_id = Column(String, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    
    semantic_score = Column(Float, nullable=False, default=0.0)
    llm_relevance_score = Column(Float, nullable=True)
    follow_boost = Column(Float, nullable=False, default=0.0)
    final_score = Column(Float, nullable=False, default=0.0)
    user_vote = Column(Integer, nullable=True) # 2: Star, 1: Up, 0: Neutral, -1: Down
    
    reasons = Column(JSON, nullable=False, default=list)

    __table_args__ = (
        PrimaryKeyConstraint('item_id', 'topic_id'),
    )
