from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class SeedPaper(BaseModel):
    paperId: str
    title: Optional[str] = None


class TopicBase(BaseModel):
    name: str
    description: str
    keywords: Optional[str] = None
    exclude_keywords: Optional[str] = None
    seed_papers: Optional[list[SeedPaper]] = None
    arxiv_categories: Optional[list[str]] = None
    priority: Optional[int] = 1
    is_active: Optional[bool] = True


class TopicCreate(TopicBase):
    pass


class TopicUpdate(TopicBase):
    name: Optional[str] = None
    description: Optional[str] = None


class TopicResponse(TopicBase):
    id: str
    user_id: str
    created_at: datetime
    has_prior_vector: bool = False

    model_config = ConfigDict(from_attributes=True)


class TopicModelStats(BaseModel):
    topic_id: str
    trained: bool
    n_pos: int = 0
    n_neg: int = 0
    cv_auc: Optional[float] = None
    trained_at: Optional[datetime] = None
    prior_source: Optional[str] = None
    extra: dict[str, Any] = {}
