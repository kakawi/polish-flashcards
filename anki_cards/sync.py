"""Sync deck files into Anki.

One file = one deck, named after the file. Each note carries two tags:
    anki_cards::id::<id>   which card of the file it is
    anki_cards::h::<hash>  its text, note type and audio file contents
so a re-run adds new cards, updates changed ones in place (keeping study
progress), leaves unchanged ones alone, and deletes notes whose card was
removed from the file. Notes without an id tag (made by hand) are never
touched.
"""
import html
import logging
from dataclasses import dataclass
from pathlib import Path

from .deckfile import Card, content_hash, deck_name_for, read_deck
from .errors import InputError
from .services import AnkiClient, AudioService
from .services.anki import plain

log = logging.getLogger(__name__)

TAG_ROOT = "anki_cards"
ID_TAG = f"{TAG_ROOT}::id::"
HASH_TAG = f"{TAG_ROOT}::h::"


@dataclass
class Result:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    removed: int = 0


def find_input_files(path: Path) -> list:
    """A single file as given, or the .json files of a folder."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise SystemExit(f"Input folder not found: {path}")
    # skip hidden files like .DS_Store
    return sorted(
        f for f in path.iterdir()
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() == ".json"
    )


def tag_value(tags: list, prefix: str):
    """'anki_cards::id::house' -> 'house' for prefix ID_TAG."""
    for t in tags:
        if t.casefold().startswith(prefix.casefold()):
            return t[len(prefix):]
    return None


class Sync:
    def __init__(self, anki: AnkiClient, audio: AudioService):
        self.anki = anki
        self.audio = audio

    def load(self, files: list) -> list:
        """Read every file first, so voices can be checked before any change
        is made in Anki. Returns [(path, deck, cards)]."""
        jobs, seen = [], {}
        for path in files:
            deck = deck_name_for(path)
            if not deck:
                log.warning("%s: empty deck name, skipping", path.name)
                continue
            if deck.casefold() in seen:
                log.warning("%s: deck %r comes from %s already, skipping",
                            path.name, deck, seen[deck.casefold()])
                continue
            try:
                cards = read_deck(path)
            except InputError as e:
                log.error("%s: %s, skipping", path.name, e)
                continue
            seen[deck.casefold()] = path.name
            jobs.append((path, deck, cards))
        return jobs

    def run(self, files: list, force=False, yes=False):
        jobs = self.load(files)
        self.audio.validate_voices({v for _, _, cards in jobs for c in cards
                                    for v in (c.front_voice, c.back_voice) if v})
        names = {d.casefold(): d for d in self.anki.deck_names()}

        if force:
            doomed = [names[d.casefold()] for _, d, _ in jobs if d.casefold() in names]
            if doomed and not yes and not self.confirm(
                    "--force will DELETE these decks, including all their cards, "
                    "any subdecks and your study progress, and rebuild them from "
                    "the input files:",
                    [f"{d} ({self.anki.card_count(d)} cards)" for d in doomed]):
                raise SystemExit("Aborted. Nothing was deleted.")

        total = Result()
        for path, deck, cards in jobs:
            key = deck.casefold()
            if force and key in names:
                log.info("Deleting deck %r (--force)", names[key])
                self.anki.delete_deck(names[key])
                del names[key]
            log.info("Deck %r <- %s (%d cards)", deck, path.name, len(cards))
            r = self.sync_deck(names.get(key, deck), cards, exists=key in names)
            log.info("Deck %r: %d added, %d updated, %d removed, %d unchanged, "
                     "%d failed", deck, r.added, r.updated, r.removed,
                     r.unchanged, r.failed)
            for k in ("added", "updated", "removed", "unchanged", "failed"):
                setattr(total, k, getattr(total, k) + getattr(r, k))

        log.info("Done. %d deck(s): %d added, %d updated, %d removed, "
                 "%d unchanged, %d failed.", len(jobs), total.added,
                 total.updated, total.removed, total.unchanged, total.failed)

    def sync_deck(self, deck: str, cards: list, exists: bool) -> Result:
        r = Result()
        notes = self.anki.deck_notes(deck) if exists else []
        by_id, extra = {}, []
        for note in notes:
            card_id = tag_value(note["tags"], ID_TAG)
            if card_id:
                # two notes with one id (e.g. copied in Anki): keep the first,
                # remove the others
                if card_id.casefold() in by_id:
                    extra.append(note)
                else:
                    by_id[card_id.casefold()] = note

        deck_ready = exists  # created only when its first card is ready
        for card in cards:
            note = by_id.pop(card.id.casefold(), None)
            try:
                fields, audio, h = self.build(deck, card)
                if note is None:
                    if not deck_ready:
                        self.anki.create_deck(deck)
                        deck_ready = True
                    self.add(deck, card, fields, audio, h)
                    r.added += 1
                    log.info("+ %s: %s -> %s", card.id, card.front, card.back)
                elif note["modelName"] != card.note_type:
                    r.failed += 1
                    log.warning("! %s: note type is %r but the file says %r; "
                                "Anki can't change it in place. Change it in "
                                "Anki (Notes > Change Note Type) or rebuild "
                                "the deck with --force", card.id,
                                note["modelName"], card.note_type)
                elif (HASH_TAG + h).casefold() in map(str.casefold, note["tags"]):
                    r.unchanged += 1
                    log.debug("= %s", card.id)
                else:
                    self.update(note, card, fields, audio, h)
                    r.updated += 1
                    log.info("~ %s: %s -> %s", card.id, card.front, card.back)
            except RuntimeError as e:  # AnkiConnect refused this one note
                r.failed += 1
                log.warning("! %s: %s", card.id, e)

        removed = [*by_id.values(), *extra]  # tagged by us, not in the file
        if removed:
            self.anki.delete_notes([n["noteId"] for n in removed])
            r.removed = len(removed)
            for note in removed:
                log.info("- %s: %s (removed from the file)",
                         tag_value(note["tags"], ID_TAG),
                         plain(note["fields"].get("Front", {}).get("value", "")))
        return r

    def build(self, deck: str, card: Card):
        """AnkiConnect fields + audio for the card, and its hash. Audio files
        are made first: their content is part of the hash, so replacing a
        file in the audio folder updates the card."""
        # fields are HTML, so escape characters like < > &
        fields = {"Front": html.escape(card.front), "Back": html.escape(card.back)}
        audio, digests = [], {}
        for text, voice, name in ((card.front, card.front_voice, "Front"),
                                  (card.back, card.back_voice, "Back")):
            if not voice:
                continue
            side = name.lower()
            path = self.audio.get(deck, card.id, side, text, voice)
            if path is None:
                log.warning("! %s: %s %r has nothing to say aloud, no audio",
                            card.id, side, text)
                continue
            digests[name] = self.audio.digest(path)
            audio.append({
                "path": str(path.resolve()),
                "filename": self.audio.media_name(deck, card.id, side),
                "fields": [name],  # appends [sound:...] to that field
            })
        h = content_hash({"front": card.front, "back": card.back,
                          "note_type": card.note_type,
                          "front_audio": digests.get("Front"),
                          "back_audio": digests.get("Back")})
        return fields, audio, h

    def add(self, deck: str, card: Card, fields: dict, audio: list, h: str):
        self.anki.add_note({
            "deckName": deck,
            "modelName": card.note_type,
            "fields": fields,
            # identity is the id tag, so two cards may share a front
            "options": {"allowDuplicate": True},
            "tags": [ID_TAG + card.id, HASH_TAG + h],
            "audio": audio,
        })

    def update(self, note: dict, card: Card, fields: dict, audio: list, h: str):
        nid = note["noteId"]
        self.anki.update_note(nid, fields, audio)
        stale = [t for t in note["tags"] if t.casefold().startswith(TAG_ROOT + "::")]
        self.anki.remove_tags([nid], stale)
        self.anki.add_tags([nid], [ID_TAG + card.id, HASH_TAG + h])

    @staticmethod
    def confirm(message: str, lines: list) -> bool:
        """Ask before deleting. Returns True only on an explicit 'yes'."""
        print("\n" + message)
        for line in lines:
            print(f"  - {line}")
        try:
            return input("Type 'yes' to continue: ").strip().lower() == "yes"
        except EOFError:
            return False
