import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String

from .base import Base


class TopicModel(Base):
    """Trained ranker weights for one topic (one row per topic)."""

    __tablename__ = "topic_models"

    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    payload = Column(JSON, nullable=False)  # serialized RankerModel
    n_pos = Column(Integer, nullable=False, default=0)
    n_neg = Column(Integer, nullable=False, default=0)
    cv_auc = Column(Float, nullable=True)  # 5-fold cross-validated AUC, None if too few labels
    version = Column(Integer, nullable=False, default=1)
    trained_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
