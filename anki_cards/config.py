"""Settings read from environment variables / a .env file.

Settings are built once in the CLI and passed to the services and modes, so
nothing reads os.environ after start-up. Command-line flags override them
with dataclasses.replace().
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() not in ("false", "0", "no")


@dataclass(frozen=True)
class Settings:
    anki_url: str = "http://localhost:8765"
    input_dir: Path = Path("input")
    audio_dir: Path = Path("audio")
    source_lang: str = "pl"
    target_lang: str = "ru"
    tts_voice: str = "pl-PL-ZofiaNeural"
    tags: tuple = ("auto",)
    vocab_note_type: str = "Basic (and reversed card)"
    qa_note_type: str = "Basic"
    # Translation provider: google (free, no key), mymemory (free, no key), deepl (key)
    translator: str = "google"
    deepl_api_key: str = field(default=None, repr=False)
    deepl_free: bool = True
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
            source_lang=os.getenv("SOURCE_LANG", d.source_lang),
            target_lang=os.getenv("TARGET_LANG", d.target_lang),
            tts_voice=os.getenv("TTS_VOICE", d.tts_voice),
            tags=tuple(t.strip() for t in os.getenv("TAGS", "auto").split(",")
                       if t.strip()),
            vocab_note_type=os.getenv("VOCAB_NOTE_TYPE", d.vocab_note_type),
            qa_note_type=os.getenv("QA_NOTE_TYPE", d.qa_note_type),
            translator=os.getenv("TRANSLATOR", d.translator).lower(),
            deepl_api_key=os.getenv("DEEPL_API_KEY") or None,
            deepl_free=_bool("DEEPL_FREE", "true"),
            mymemory_email=os.getenv("MYMEMORY_EMAIL") or None,
            request_delay=float(os.getenv("REQUEST_DELAY", str(d.request_delay))),
            log_level=os.getenv("LOG_LEVEL", d.log_level).upper(),
        )
