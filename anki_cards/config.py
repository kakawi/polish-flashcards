"""Settings read from environment variables / a .env file.

Settings are built once in the CLI and passed to the services, so nothing
reads os.environ after start-up.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    anki_url: str = "http://localhost:8765"
    input_dir: Path = Path("input")
    audio_dir: Path = Path("audio")
    mymemory_email: str = None  # raises MyMemory's daily quota
    # Pause between translation requests, to stay under rate limits
    request_delay: float = 0.7
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        d = cls()
        return cls(
            anki_url=os.getenv("ANKI_URL", d.anki_url),
            input_dir=Path(os.getenv("INPUT_DIR", str(d.input_dir))),
            audio_dir=Path(os.getenv("AUDIO_DIR", str(d.audio_dir))),
            mymemory_email=os.getenv("MYMEMORY_EMAIL") or None,
            request_delay=float(os.getenv("REQUEST_DELAY", str(d.request_delay))),
            log_level=os.getenv("LOG_LEVEL", d.log_level).upper(),
        )
