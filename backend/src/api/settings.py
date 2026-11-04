from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.app_config import AppConfig
from src.schemas.settings import SettingsUpdate, SettingsResponse

router = APIRouter(prefix="/settings", tags=["settings"])

SECRET_KEYS = ("gemini_api_key", "anthropic_api_key", "s2_api_key")
MASK = "••••"


def get_config_value(db: Session, key: str, default: str = "") -> str:
    conf = db.query(AppConfig).filter(AppConfig.key == key).first()
    return conf.value if conf else default


def mask_secret(value: str) -> str:
    """Never return a stored API key to the browser; show only enough to recognise it."""
    if not value:
        return ""
    if len(value) <= 8:
        return MASK
    return f"{value[:4]}{MASK}{value[-4:]}"


def is_masked(value: str) -> bool:
    return MASK in value


@router.get("/", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    return {
        "gemini_api_key": mask_secret(get_config_value(db, "gemini_api_key", "")),
        "anthropic_api_key": mask_secret(get_config_value(db, "anthropic_api_key", "")),
        "s2_api_key": mask_secret(get_config_value(db, "s2_api_key", "")),
        "anthropic_budget_limit": float(get_config_value(db, "anthropic_budget_limit", "5.0")),
        "enable_llm_reranking": get_config_value(db, "enable_llm_reranking", "true") == "true",
        "reranking_mode": get_config_value(db, "reranking_mode", "llm"),
        "last_synced_at": get_config_value(db, "last_synced_at", None),
    }


@router.post("/", response_model=SettingsResponse)
def update_settings(settings: SettingsUpdate, db: Session = Depends(get_db)):
    def set_config(key: str, value: str):
        conf = db.query(AppConfig).filter(AppConfig.key == key).first()
        if conf:
            conf.value = value
        else:
            db.add(AppConfig(key=key, value=value))

    for key in SECRET_KEYS:
        value = getattr(settings, key)
        # The UI echoes the masked value back when the user did not touch the field.
        if value is not None and not is_masked(value):
            set_config(key, value.strip())
    if settings.anthropic_budget_limit is not None:
        set_config("anthropic_budget_limit", str(settings.anthropic_budget_limit))
    if settings.enable_llm_reranking is not None:
        set_config("enable_llm_reranking", "true" if settings.enable_llm_reranking else "false")
    if settings.reranking_mode is not None:
        set_config("reranking_mode", settings.reranking_mode)

    db.commit()
    return get_settings(db=db)
