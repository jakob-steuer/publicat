from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict

class ItemBase(BaseModel):
    source: str
    source_native_id: str
    title: str
    authors: List[str]
    abstract: str
    published_at: datetime
    url: str
    doi: Optional[str] = None
    venue: Optional[str] = None
    citation_count: Optional[int] = None
    raw_metadata_json: Dict[str, Any]

class ItemCreate(ItemBase):
    pass

class ItemResponse(ItemBase):
    id: str
    is_acknowledged: bool
    is_starred: bool
    is_hidden: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
