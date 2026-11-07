"""Turn input files into decks, for any mode.

One file = one deck; the file name (without extension) is the deck name.
A deck that already exists in Anki is skipped; with force=True it is deleted
and recreated from its file.
"""
import html
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .errors import InputError, ProviderError, SkipEntry
from .modes import Mode
from .services import AnkiClient, AudioService

log = logging.getLogger(__name__)


@dataclass
class Result:
    added: int = 0
    skipped: int = 0
    stop: bool = False  # a provider problem that affects every remaining file


def deck_name_for(path: Path) -> str:
    """The deck name is the file name without its extension."""
    return unicodedata.normalize("NFC", path.stem).strip()


def find_input_files(path: Path, suffixes: tuple) -> list:
    """A single file as given, or the matching files of a folder."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise SystemExit(f"Input folder not found: {path}")
    # skip hidden files like .DS_Store
    return sorted(
        f for f in path.iterdir()
        if f.is_file() and not f.name.startswith(".")
        and f.suffix.lower() in suffixes
    )


class Pipeline:
    def __init__(self, mode: Mode, anki: AnkiClient, audio: AudioService,
                 tags: tuple):
        self.mode = mode
        self.anki = anki
        self.audio = audio
        self.tags = list(tags)

    def run(self, files: list, force: bool = False, yes: bool = False):
        names = {d.casefold(): d for d in self.anki.deck_names()}
        existing = set(names)

        jobs = []
        for path in files:
            deck = deck_name_for(path)
            if deck:
                jobs.append((path, deck))
            else:
                log.warning("%s: empty deck name, skipping", path.name)

        if force:
            # each existing deck once, even if two files map to the same name
            doomed = list(dict.fromkeys(
                names[d.casefold()] for _, d in jobs if d.casefold() in names
            ))
            if doomed and not yes and not self.confirm_recreate(doomed):
                raise SystemExit("Aborted. Nothing was deleted.")

        decks = skipped_decks = added = 0
        seen = set()
        for path, deck in jobs:
            key = deck.casefold()
            if key in seen:
                log.warning("%s: deck %r was already handled by another file "
                            "in this run, skipping", path.name, deck)
                continue
            seen.add(key)

            if key in existing:
                if not force:
                    skipped_decks += 1
                    log.info("Deck %r already exists, skipping %s (use --force "
                             "to delete and recreate it)", deck, path.name)
                    continue
                log.info("Deleting deck %r (--force)", names[key])
                self.anki.delete_deck(names[key])
                existing.discard(key)

            result = self.process_file(path, deck, existing)
            decks += 1
            added += result.added
            log.info("Deck %r: added %d, skipped %d",
                     deck, result.added, result.skipped)
            if result.stop:
                log.error("Stopped while processing deck %r, so it may be "
                          "incomplete. Fix the problem and run again with "
                          "--force to rebuild it from scratch.", deck)
                break

        log.info("Done. %d deck(s) processed, %d skipped because they already "
                 "exist; %d card(s) added.", decks, skipped_decks, added)

    def process_file(self, path: Path, deck: str, existing_decks: set) -> Result:
        """Add the cards from one file to its deck."""
        result = Result()
        try:
            entries = self.mode.read(path)
        except InputError as e:
            log.error("%s: %s, skipping", path.name, e)
            return result

        # The deck is only created when the first card is ready, so a run that
        # fails early does not leave an empty deck behind.
        deck_ready = deck.casefold() in existing_decks
        log.info("Deck %r <- %s (%d entries)", deck, path.name, len(entries))

        for n, entry in enumerate(entries, start=1):
            key = self.mode.key(entry)
            log.debug("[%d] %r", n, key)
            # Check for an existing card FIRST, so we never translate or
            # synthesize audio for entries that are already in the deck.
            if deck_ready and self.anki.note_exists(
                    deck, self.mode.note_type, self.mode.key_field, key):
                result.skipped += 1
                log.info("- %s: already in deck, skipped", key)
                continue

            try:
                note = self.mode.build(entry)
            except ProviderError as e:
                log.error("%s", e)
                result.stop = True
                return result
            except SkipEntry as e:
                result.skipped += 1
                log.warning("- %s: %s", key, e)
                continue

            payload = self.to_anki_note(deck, note)
            if not deck_ready:
                self.anki.create_deck(deck)
                existing_decks.add(deck.casefold())
                deck_ready = True
            try:
                self.anki.add_note(payload)
                result.added += 1
                log.info("+ %s", " -> ".join(note.fields.values()))
            except RuntimeError as e:
                result.skipped += 1
                log.warning("- %s: %s", key, e)
        return result

    def to_anki_note(self, deck: str, note) -> dict:
        """Note -> AnkiConnect addNote payload, generating the audio files."""
        return {
            "deckName": deck,
            "modelName": self.mode.note_type,
            # fields are HTML, so escape characters like < > &
            "fields": {k: html.escape(v) for k, v in note.fields.items()},
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            "tags": self.tags,
            "audio": [{
                "path": str(self.audio.get(a.text).resolve()),
                "filename": self.audio.media_name(a.text),
                "fields": [a.field],  # appends [sound:...] to that field
            } for a in note.audio],
        }

    def confirm_recreate(self, decks) -> bool:
        """Ask before deleting decks. Returns True only on an explicit 'yes'."""
        print("\n--force will DELETE these decks, including all their cards, "
              "any subdecks and your study progress, and rebuild them from the "
              "input files:")
        for name in decks:
            print(f"  - {name} ({self.anki.card_count(name)} cards)")
        try:
            return input("Type 'yes' to continue: ").strip().lower() == "yes"
        except EOFError:
            return False
