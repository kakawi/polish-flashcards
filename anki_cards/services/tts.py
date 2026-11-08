"""Text-to-speech with edge-tts, stored as audio/<deck>/<id>_<side>.mp3.

An existing file is used as it is, so audio from anywhere else can be put
under that name. Each deck folder keeps a .generated.json recording which
files were generated, from which text and voice: a generated file is made
again when its text or voice changes, a file put there by hand never is.
"""
import asyncio
import hashlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path

import edge_tts

log = logging.getLogger(__name__)

# Voice used for a bare language code in a deck file.
DEFAULT_VOICES = {
    "pl": "pl-PL-ZofiaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "uk": "uk-UA-PolinaNeural",
    "en": "en-US-AriaNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "it": "it-IT-ElsaNeural",
}


def safe_name(text: str) -> str:
    """'Co jesz na śniadanie?' -> 'Co_jesz_na_śniadanie': characters that
    file systems or Anki's media folder reject become _, the length is
    capped below file system limits."""
    name = unicodedata.normalize("NFC", text)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f\s]+', "_", name)
    return name.strip("_.")[:120] or "_"


def is_voice_name(spec: str) -> bool:
    """'pl-PL-MarekNeural' is a voice; 'pl' or 'pt-BR' is a language code."""
    return spec.count("-") >= 2


def resolve_voice(spec: str) -> str:
    """Language code or voice name -> voice name. Raises KeyError for a
    language with no default voice."""
    return spec if is_voice_name(spec) else DEFAULT_VOICES[spec.lower()]


class AudioService:
    MANIFEST = ".generated.json"

    def __init__(self, audio_dir: Path):
        self.audio_dir = audio_dir
        self._manifests = {}  # deck folder -> {filename: {text, voice, md5}}

    def path(self, deck: str, card_id: str, side: str) -> Path:
        return self.audio_dir / safe_name(deck) / f"{card_id}_{side}.mp3"

    @staticmethod
    def media_name(deck: str, card_id: str, side: str) -> str:
        """Filename inside Anki's media folder, which all decks share,
        e.g. Zwierzęta_cat_front.mp3."""
        return f"{safe_name(deck)}_{card_id}_{side}.mp3"

    @staticmethod
    def digest(path: Path) -> str:
        """Fingerprint of the file's content, so a replaced file is noticed."""
        return hashlib.md5(path.read_bytes()).hexdigest()[:10]

    @staticmethod
    def validate_voices(voices):
        """Fail early, with suggestions, if a voice doesn't exist."""
        try:
            available = {v["ShortName"] for v in asyncio.run(edge_tts.list_voices())}
        except Exception as e:  # offline etc.: don't block, synthesis will report it
            log.debug("could not fetch the voice list (%r); skipping voice check", e)
            return
        for voice in sorted(set(voices) - available):
            prefix = "-".join(voice.split("-")[:2])  # e.g. pl-PL
            similar = sorted(n for n in available if n.startswith(prefix))
            hint = (f" Voices for {prefix}: {', '.join(similar)}." if similar
                    else " Run `edge-tts --list-voices` to see all voices.")
            raise SystemExit(f"TTS voice {voice!r} is not available in edge-tts.{hint}")

    def manifest(self, folder: Path) -> dict:
        if folder not in self._manifests:
            try:
                self._manifests[folder] = json.loads(
                    (folder / self.MANIFEST).read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                self._manifests[folder] = {}
        return self._manifests[folder]

    def get(self, deck: str, card_id: str, side: str, text: str,
            voice: str) -> Path:
        """Path to the mp3 for one side of a card, generating it if needed."""
        path = self.path(deck, card_id, side)
        made = self.manifest(path.parent)
        if path.exists():
            entry = made.get(path.name)
            ours = entry and entry["md5"] == self.digest(path)
            if not ours or (entry["text"], entry["voice"]) == (text, voice):
                log.debug("audio: using %s", path)
                return path
            log.info("audio: %s is for %r (%s), regenerating", path.name,
                     entry["text"], entry["voice"])
        path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        asyncio.run(edge_tts.Communicate(text, voice).save(str(path)))
        log.debug("audio: generated %s (%.2fs)", path, time.monotonic() - start)
        made[path.name] = {"text": text, "voice": voice, "md5": self.digest(path)}
        (path.parent / self.MANIFEST).write_text(
            json.dumps(made, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8")
        return path
