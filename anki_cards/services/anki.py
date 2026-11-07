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

    def note_exists(self, deck: str, note_type: str, field: str, text: str) -> bool:
        """True if a note in the deck has this text in the given field.

        We search the deck ourselves instead of relying on Anki's duplicate
        rule, because the stored field also contains a [sound:...] tag.
        """
        query = (
            f'"deck:{escape(deck)}" "note:{escape(note_type)}" '
            f'"{escape(field)}:{escape(html.escape(text))}*"'
        )
        ids = self.invoke("findNotes", query=query)
        log.debug("existing-note search %s -> %d candidate(s)", query, len(ids))
        if not ids:
            return False
        wanted = text.strip().casefold()
        return any(
            plain(info["fields"][field]["value"]) == wanted
            for info in self.invoke("notesInfo", notes=ids)
        )

    def add_note(self, note: dict):
        return self.invoke("addNote", note=note)
