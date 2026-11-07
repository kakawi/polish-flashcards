"""Text-to-speech with edge-tts, cached as mp3 files in the audio folder."""
import asyncio
import hashlib
import logging
import re
import time
from pathlib import Path

import edge_tts

log = logging.getLogger(__name__)


def safe_name(text: str) -> str:
    """Filename-safe version of the text (sentences contain ? , . etc.)."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:80]


class AudioService:
    def __init__(self, audio_dir: Path, voice: str, lang: str):
        self.audio_dir = audio_dir
        self.voice = voice
        self.lang = lang

    def key(self, text: str) -> str:
        """Short hash of voice + text: changing the voice gives new file names,
        so old audio from another voice is never reused by mistake."""
        return hashlib.md5(f"{self.voice}|{text}".encode()).hexdigest()[:10]

    def media_name(self, text: str) -> str:
        """ASCII, collision-free filename inside Anki's media folder."""
        return f"{self.lang}_{self.key(text)}.mp3"

    def validate_voice(self):
        """Fail early, with suggestions, if the configured voice doesn't exist."""
        try:
            voices = asyncio.run(edge_tts.list_voices())
        except Exception as e:  # offline etc.: don't block, synthesis will report it
            log.debug("could not fetch the voice list (%r); skipping voice check", e)
            return
        names = {v["ShortName"] for v in voices}
        if self.voice in names:
            return
        prefix = "-".join(self.voice.split("-")[:2])  # e.g. pl-PL
        similar = sorted(n for n in names if n.startswith(prefix))
        hint = (f" Voices for {prefix}: {', '.join(similar)}." if similar
                else " Run `edge-tts --list-voices` to see all voices.")
        raise SystemExit(
            f"TTS voice {self.voice!r} is not available in edge-tts.{hint}")

    def get(self, text: str) -> Path:
        """Path to an mp3 of the text, generating it if needed."""
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        # reuse a file made by another tool, if one exists under a matching name
        for name in (text, safe_name(text)):
            existing = self.audio_dir / f"{name}.mp3"
            if existing.exists():
                log.debug("audio: reusing %s", existing)
                return existing
        # otherwise generate one; the hash keeps long sentences from clashing
        path = self.audio_dir / f"{self.key(text)}.mp3"
        if path.exists():
            log.debug("audio: cached %s", path)
        else:
            start = time.monotonic()
            asyncio.run(edge_tts.Communicate(text, self.voice).save(str(path)))
            log.debug("audio: generated %s (%.2fs)", path, time.monotonic() - start)
        return path
