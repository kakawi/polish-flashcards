"""Questions and answers in the source language, no translation.

    Front: question + audio
    Back:  answer + audio

Input is a JSON array of objects:
    [{"question": "Co jesz na śniadanie?", "answer": "Jem jajka."}]
"""
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..errors import InputError
from .base import Audio, Mode, Note


@dataclass
class QAEntry:
    question: str
    answer: str


def text_field(item: dict, name: str, n: int) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"item {n}: {name!r} must be a non-empty string")
    # Anki stores text as NFC; match it so lookups and duplicates work
    return unicodedata.normalize("NFC", value.strip())


class QAMode(Mode):
    name = "qa"
    help = "question/answer pairs from JSON, no translation (question + audio -> answer + audio)"
    suffixes = (".json",)

    @property
    def note_type(self):
        return self.settings.qa_note_type

    def read(self, path: Path) -> list:
        # A broken file is rejected as a whole, so a deck is never half-built
        # from it.
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except UnicodeDecodeError:
            raise InputError("not a UTF-8 text file")
        except json.JSONDecodeError as e:
            raise InputError(f"invalid JSON: {e}")
        if not isinstance(data, list):
            raise InputError("expected a JSON array of objects")
        entries = []
        for n, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise InputError(f"item {n}: expected an object")
            entries.append(QAEntry(text_field(item, "question", n),
                                   text_field(item, "answer", n)))
        return entries

    def key(self, entry: QAEntry) -> str:
        return entry.question

    def build(self, entry: QAEntry) -> Note:
        return Note(
            fields={"Front": entry.question, "Back": entry.answer},
            audio=[Audio(entry.question, "Front"), Audio(entry.answer, "Back")],
        )
