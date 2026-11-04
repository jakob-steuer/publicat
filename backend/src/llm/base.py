from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """A summariser / relevance judge. Providers count the tokens they use so the
    pipeline can enforce the monthly budget."""

    name: str = "unknown"
    is_cloud: bool = True

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.errors = 0

    def add_usage(self, input_tokens: int | None, output_tokens: int | None) -> None:
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)

    def take_usage(self) -> tuple[int, int, int]:
        """Return (calls, input_tokens, output_tokens) since the last call and reset."""
        out = (self.calls, self.input_tokens, self.output_tokens)
        self.calls = self.input_tokens = self.output_tokens = 0
        return out

    @abstractmethod
    async def summarize_brief(self, text: str, topic_desc: str) -> tuple[str, int]:
        """Returns a brief 1-2 sentence summary and a relevance score from 1-10."""

    @abstractmethod
    async def summarize_deep(self, text: str, topic_desc: str) -> tuple[str, list[str]]:
        """Returns a detailed summary and the list of tools/models the paper introduces."""

    @abstractmethod
    async def extract_keywords(self, text: str, topic_desc: str) -> list[str]:
        """Extracts only the tools/models the paper introduces."""

    @abstractmethod
    async def evaluate_relevance(self, text: str, topic_desc: str) -> tuple[int, str]:
        """Fast evaluation returning a score from 0-100 and a 1-sentence reason."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        pass
