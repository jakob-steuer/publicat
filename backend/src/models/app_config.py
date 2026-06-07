from sqlalchemy import Column, String, Float
from .base import Base

class AppConfig(Base):
    __tablename__ = "app_config"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)

class BudgetTracker(Base):
    __tablename__ = "budget_tracker"
    
    id = Column(String, primary_key=True) # e.g. 'anthropic_2026-06'
    month = Column(String, nullable=False, index=True) # e.g. '2026-06'
    provider = Column(String, nullable=False) # e.g. 'anthropic'
    total_cost_usd = Column(Float, nullable=False, default=0.0)
