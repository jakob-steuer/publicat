from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.app_config import AppConfig
from src.schemas.settings import SettingsUpdate, SettingsResponse

router = APIRouter(prefix="/settings", tags=["settings"])

def get_config_value(db: Session, key: str, default: str = "") -> str:
    conf = db.query(AppConfig).filter(AppConfig.key == key).first()
    return conf.value if conf else default

@router.get("/", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    return {
        "gemini_api_key": get_config_value(db, "gemini_api_key", ""),
        "anthropic_api_key": get_config_value(db, "anthropic_api_key", ""),
        "anthropic_budget_limit": float(get_config_value(db, "anthropic_budget_limit", "5.0")),
        "last_synced_at": get_config_value(db, "last_synced_at", None)
    }

@router.post("/", response_model=SettingsResponse)
def update_settings(settings: SettingsUpdate, db: Session = Depends(get_db)):
    def set_config(key: str, value: str):
        conf = db.query(AppConfig).filter(AppConfig.key == key).first()
        if conf:
            conf.value = value
        else:
            db.add(AppConfig(key=key, value=value))
            
    if settings.gemini_api_key is not None:
        set_config("gemini_api_key", settings.gemini_api_key)
    if settings.anthropic_api_key is not None:
        set_config("anthropic_api_key", settings.anthropic_api_key)
    if settings.anthropic_budget_limit is not None:
        set_config("anthropic_budget_limit", str(settings.anthropic_budget_limit))
        
    db.commit()
    return get_settings(db=db)
