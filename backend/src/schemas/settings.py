from pydantic import BaseModel
from typing import Optional

class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_budget_limit: Optional[float] = None
    
class SettingsResponse(BaseModel):
    gemini_api_key: str
    anthropic_api_key: str
    anthropic_budget_limit: float
    last_synced_at: Optional[str] = None
