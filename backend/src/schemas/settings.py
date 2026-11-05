from pydantic import BaseModel
from typing import Optional

class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    s2_api_key: Optional[str] = None
    anthropic_budget_limit: Optional[float] = None
    enable_llm_reranking: Optional[bool] = None
    reranking_mode: Optional[str] = None
    zotero_auto_push: Optional[bool] = None
    zotero_user_id: Optional[str] = None
    zotero_api_key: Optional[str] = None
    
class SettingsResponse(BaseModel):
    gemini_api_key: str
    anthropic_api_key: str
    s2_api_key: str
    anthropic_budget_limit: float
    enable_llm_reranking: bool
    reranking_mode: str
    zotero_auto_push: bool = False
    zotero_user_id: str = ""
    zotero_api_key: str = ""
    llm_spend_this_month: float = 0.0
    last_synced_at: Optional[str] = None
    last_complete_sync_at: Optional[str] = None
