"""Claude CLI adapter - subprocess wrapper for Claude Code."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_FALLBACK_PATH = Path.home() / ".local" / "bin" / "claude"


def find_claude_binary() -> str:
    """Find the claude binary, checking PATH then known install locations."""
    found = shutil.which("claude")
    if found:
        return found
    if CLAUDE_FALLBACK_PATH.exists():
        return str(CLAUDE_FALLBACK_PATH)
    return "claude"  # let FileNotFoundError propagate


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
        self._claude = find_claude_binary()

    def generate(self, prompt: str) -> str:
        """Generate text from a prompt. Returns complete response."""
        try:
            proc = subprocess.run(
                [self._claude, "-p", prompt],
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

    def run_command(self, command: str) -> str:
        """
        Run a slash command (e.g., "/triage").

        Different from generate() - passes command directly without -p flag.
        """
        try:
            proc = subprocess.run(
                [self._claude, "-p", command],
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
