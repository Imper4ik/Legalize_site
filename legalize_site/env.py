from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - handled by dependency management
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env(env_path: Optional[Path] = None) -> None:
    """Load environment variables from a .env file when available.

    The helper is safe to call multiple times and silently skips loading if
    ``python-dotenv`` is not installed. Render injects environment variables
    directly, but local development relies on ``.env`` for convenience.
    """

    if load_dotenv is None:
        return

    env_file = env_path or BASE_DIR / ".env"
    load_dotenv(env_file)
