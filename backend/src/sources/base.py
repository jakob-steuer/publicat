from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from src.schemas.item import ItemCreate

class Source(ABC):
    """
    Abstract base class for data ingestion sources.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Internal name of the source (e.g., 'arxiv', 'github_releases')"""
        pass

    @abstractmethod
    async def fetch_recent(self, since: datetime, followed_authors: List[str] = None) -> List[ItemCreate]:
        """
        Fetches items from the source published after `since`.
        Must be idempotent and aggressively cached (where applicable).
        Returns a list of Pydantic models for creation.
        """
        pass
