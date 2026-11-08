"""Thin client for the AnkiConnect add-on."""
import html
import logging
import re
import time

import requests

log = logging.getLogger(__name__)


def escape(s: str) -> str:
    """Escape text for use inside a quoted Anki search term."""
    return re.sub(r'([\\"*_:])', r"\\\1", s)


def plain(value: str) -> str:
    """Field value -> comparable text: drop [sound:] tags and HTML, unescape."""
    value = re.sub(r"\[sound:[^\]]*\]", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip().casefold()


class AnkiClient:
    def __init__(self, url: str):
        self.url = url

    def invoke(self, action, **params):
        start = time.monotonic()
        try:
            resp = requests.post(
                self.url,
                json={"action": action, "version": 6, "params": params},
                timeout=30,
            ).json()
        except requests.ConnectionError:
            raise SystemExit(
                f"Cannot reach AnkiConnect at {self.url}. "
                "Is Anki open with the AnkiConnect add-on installed?"
            )
        log.debug("anki %s -> error=%r (%.2fs)", action, resp["error"],
                  time.monotonic() - start)
        if resp["error"]:
            raise RuntimeError(resp["error"])
        return resp["result"]

    def version(self):
        return self.invoke("version")

    def deck_names(self) -> list:
        return self.invoke("deckNames")

    def create_deck(self, deck: str):
        self.invoke("createDeck", deck=deck)

    def delete_deck(self, deck: str):
        """Delete a deck with its cards and subdecks."""
        self.invoke("deleteDecks", decks=[deck], cardsToo=True)

    def card_count(self, deck: str) -> int:
        return len(self.invoke("findCards", query=f'"deck:{escape(deck)}"'))

    def deck_notes(self, deck: str) -> list:
        """notesInfo for every note directly in the deck (not its subdecks)."""
        d = escape(deck)
        ids = self.invoke("findNotes", query=f'"deck:{d}" -"deck:{d}::*"')
        return self.invoke("notesInfo", notes=ids) if ids else []

    def update_note(self, note_id: int, fields: dict, audio: list):
        """Replace the note's fields; audio [sound:] tags are appended again."""
        self.invoke("updateNoteFields",
                    note={"id": note_id, "fields": fields, "audio": audio})

    def add_tags(self, note_ids: list, tags: list):
        if note_ids and tags:
            self.invoke("addTags", notes=note_ids, tags=" ".join(tags))

    def remove_tags(self, note_ids: list, tags: list):
        if note_ids and tags:
            self.invoke("removeTags", notes=note_ids, tags=" ".join(tags))

    def delete_notes(self, note_ids: list):
        if note_ids:
            self.invoke("deleteNotes", notes=note_ids)

    def add_note(self, note: dict):
        return self.invoke("addNote", note=note)
