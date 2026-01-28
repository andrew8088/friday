"""LLM service interface."""

from typing import Iterator, Protocol


class LLMService(Protocol):
    """Interface for LLM text generation."""

    def generate(self, prompt: str) -> str:
        """Generate text from a prompt. Returns complete response."""
        ...

    def stream(self, prompt: str) -> Iterator[str]:
        """Stream text generation. Yields chunks as they arrive."""
        ...
