"""Monthly spend tracking for cloud LLM providers (estimate from token counts)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.models.app_config import BudgetTracker

# USD per million tokens (input, output). Update when switching models.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "anthropic": (0.10, 0.50),  # claude-haiku-5-5
    "gemini": (0.30, 2.50),  # gemini-2.5-flash (approximate)
    "ollama": (0.0, 0.0),
}


def month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def cost_usd(provider: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES_PER_MTOK.get(provider, (0.0, 0.0))
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000.0


def record_spend(db: Session, provider: str, input_tokens: int, output_tokens: int) -> float:
    """Add this usage to the provider's running total for the current month. Returns the new total."""
    amount = cost_usd(provider, input_tokens, output_tokens)
    key = f"{provider}_{month_key()}"
    row = db.get(BudgetTracker, key)
    if row is None:
        row = BudgetTracker(id=key, month=month_key(), provider=provider, total_cost_usd=0.0)
        db.add(row)
    row.total_cost_usd = (row.total_cost_usd or 0.0) + amount
    db.commit()
    return row.total_cost_usd


def month_spend(db: Session, provider: str | None = None) -> float:
    q = db.query(BudgetTracker).filter(BudgetTracker.month == month_key())
    if provider:
        q = q.filter(BudgetTracker.provider == provider)
    return float(sum(r.total_cost_usd or 0.0 for r in q.all()))


def over_budget(db: Session, provider: str, limit_usd: float) -> bool:
    if limit_usd <= 0 or provider == "ollama":
        return False
    return month_spend(db, provider) >= limit_usd
