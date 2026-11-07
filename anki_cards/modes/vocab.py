"""Vocabulary: one word or sentence per line, machine-translated.

    Front: source-language text + audio
    Back:  translation
An own translation can follow the text after a tab.
"""
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..errors import InputError, ProviderError, SkipEntry
from ..services import Translator
from .base import Audio, Mode, Note


@dataclass
class VocabEntry:
    text: str
    manual: str  # own translation from the file, or ""


def nfc(s: str) -> str:
    """Anki stores text as NFC; match it so lookups and duplicates work."""
    return unicodedata.normalize("NFC", s.strip())


class VocabMode(Mode):
    name = "vocab"
    help = "words/sentences, one per line, translated (text + audio -> translation)"
    suffixes = (".txt",)

    def __init__(self, settings):
        super().__init__(settings)
        self.translator = Translator(settings)  # fail fast on bad config

    @property
    def note_type(self):
        return self.settings.vocab_note_type

    def read(self, path: Path) -> list:
        try:
            # utf-8-sig also handles the BOM that some Windows editors add
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            raise InputError("not a UTF-8 text file")
        entries = []
        for line in lines:
            text, _, manual = line.strip().partition("\t")
            if text.strip():
                entries.append(VocabEntry(nfc(text), nfc(manual)))
        return entries

    def key(self, entry: VocabEntry) -> str:
        return entry.text

    def build(self, entry: VocabEntry) -> Note:
        text, translation = entry.text, entry.manual
        if not translation:
            try:
                translation = self.translator.translate(text)
            except ProviderError:
                raise
            except Exception as e:  # e.g. no translation found for this entry
                raise SkipEntry(f"translation failed: {e!r}")
            if translation.strip().casefold() == text.strip().casefold():
                raise SkipEntry(
                    "translation came back identical to the original, not "
                    "adding a card. Try another TRANSLATOR, or give your own "
                    "translation after a tab in the input file."
                )
        return Note(
            fields={"Front": text, "Back": translation},
            audio=[Audio(text, "Front")],
        )
