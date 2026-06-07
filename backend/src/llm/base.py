from abc import ABC, abstractmethod

class LLMProvider(ABC):
    
    @abstractmethod
    async def summarize_brief(self, text: str, topic_desc: str) -> tuple[str, int]:
        """
        Returns a brief 1-2 sentence summary and a relevance score from 1-10.
        Returns: (summary, relevance_score)
        """
        pass
        
    @abstractmethod
    async def summarize_deep(self, text: str, topic_desc: str) -> str:
        """
        Returns a detailed 'why you must read this' summary.
        """
        pass
        
    @abstractmethod
    async def extract_keywords(self, text: str, topic_desc: str) -> list[str]:
        """
        Extracts only the broad keywords and concepts, without generating a summary.
        """
        pass

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        pass
