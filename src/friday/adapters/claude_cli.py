"""Claude CLI adapter - subprocess wrapper for Claude Code."""

import logging
import subprocess
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class ClaudeCLIService:
    """
    Claude CLI subprocess adapter.

    Implements LLMService protocol. Wraps the claude CLI tool.
    """

    def __init__(
        self,
        cwd: Path | str | None = None,
        timeout: int = 300,  # 5 minutes default
    ):
        self.cwd = Path(cwd) if cwd else None
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        """Generate text from a prompt. Returns complete response."""
        try:
            proc = subprocess.run(
                ["claude", "-p", prompt],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if proc.returncode != 0:
                logger.error(f"Claude CLI failed: {proc.stderr}")
                raise RuntimeError(f"Claude CLI failed: {proc.stderr}")
            return proc.stdout
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")

    def stream(self, prompt: str) -> Iterator[str]:
        """Stream text generation. Yields chunks as they arrive."""
        try:
            proc = subprocess.Popen(
                ["claude", "-p", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
            )

            # Write prompt to stdin
            proc.stdin.write(prompt)
            proc.stdin.close()

            # Stream stdout
            for line in proc.stdout:
                yield line

            # Check for errors
            proc.wait()
            if proc.returncode != 0:
                stderr = proc.stderr.read()
                logger.error(f"Claude CLI failed: {stderr}")
                raise RuntimeError(f"Claude CLI failed: {stderr}")

        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")

    def run_command(self, command: str) -> str:
        """
        Run a slash command (e.g., "/triage").

        Different from generate() - passes command directly without -p flag.
        """
        try:
            proc = subprocess.run(
                ["claude", "-p", command],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if proc.returncode != 0:
                logger.error(f"Claude CLI command failed: {proc.stderr}")
                raise RuntimeError(f"Claude CLI command failed: {proc.stderr}")
            return proc.stdout
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")
