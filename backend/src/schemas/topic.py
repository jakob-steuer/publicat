from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class TopicBase(BaseModel):
    name: str
    description: str
    keywords: Optional[str] = None
    priority: Optional[int] = 1
    is_active: Optional[bool] = True

class TopicCreate(TopicBase):
    pass

class TopicUpdate(TopicBase):
    name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[str] = None

class TopicResponse(TopicBase):
    id: str
    user_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
