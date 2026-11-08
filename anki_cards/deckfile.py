"""Deck files: JSON with deck-wide settings and cards that can override them.

    {
      "settings": {"front_audio": "pl", "back_audio": null, "note_type": "Basic"},
      "cards": [
        {"id": "house", "front": "dom", "back": "дом"},
        {"id": "breakfast", "front": "Co jesz rano?", "back": "Jem jajka.",
         "back_audio": "pl"}
      ]
    }

"settings" is required and must set all three keys; a card can override
any of them. *_audio is a language code ("pl"), an edge-tts voice
("pl-PL-MarekNeural") or null for no audio.
"""
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .errors import InputError
from .services.tts import resolve_voice

# Raising this makes every card count as changed once, so all of them are
# updated in place (study progress is kept).
HASH_VERSION = 1

SETTING_KEYS = ("front_audio", "back_audio", "note_type")
CARD_KEYS = ("id", "front", "back") + SETTING_KEYS
# Anki tags can't contain spaces; :: would start a tag hierarchy level
ID_RE = re.compile(r"^[\w-]+$")


@dataclass(frozen=True)
class Card:
    id: str
    front: str
    back: str
    front_voice: str  # None = no audio
    back_voice: str
    note_type: str


def norm(s: str) -> str:
    """The text as it goes into Anki: NFC (Anki stores NFC, so lookups match),
    trimmed, inner whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFC", s).split())


def content_hash(fields: dict) -> str:
    """Short hash of a card's content. JSON with sorted keys, so "ab"+"c" and
    "a"+"bc" differ and the field order never matters."""
    payload = json.dumps({"v": HASH_VERSION, **fields}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def deck_name_for(path: Path) -> str:
    """The deck name is the file name without its extension."""
    return unicodedata.normalize("NFC", path.stem).strip()


def _check_keys(obj: dict, allowed: tuple, where: str):
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise InputError(f"{where}: unknown key(s) {', '.join(map(repr, unknown))} "
                         f"(allowed: {', '.join(allowed)})")


def _text(obj: dict, key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not norm(value):
        raise InputError(f"{where}: {key!r} must be a non-empty string")
    return norm(value)


def _voice(value, key: str, where: str):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}: {key!r} must be a language code, a voice "
                         "name or null")
    try:
        return resolve_voice(value.strip())
    except KeyError:
        raise InputError(f"{where}: no default voice for language {value!r}; "
                         "use a voice name, e.g. \"cs-CZ-VlastaNeural\" "
                         "(edge-tts --list-voices)")


def read_deck(path: Path) -> list:
    """Parse and validate a deck file into Cards. Any problem rejects the whole
    file, so a deck is never synced from half a file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        raise InputError("not a UTF-8 text file")
    except json.JSONDecodeError as e:
        raise InputError(f"invalid JSON: {e}")
    if not isinstance(data, dict):
        raise InputError('expected an object with "settings" and "cards"')
    _check_keys(data, ("settings", "cards"), "top level")

    deck = data.get("settings")
    if not isinstance(deck, dict):
        raise InputError('"settings" is required and must be an object')
    _check_keys(deck, SETTING_KEYS, "settings")
    missing = [k for k in SETTING_KEYS if k not in deck]
    if missing:
        raise InputError(f"settings: missing {', '.join(map(repr, missing))} "
                         "(use null for no audio)")

    items = data.get("cards")
    if not isinstance(items, list):
        raise InputError('"cards" must be an array')
    if not items:  # cards removed from the file are deleted from the deck
        raise InputError('"cards" is empty; to delete the deck, delete it in '
                         'Anki')

    cards, seen = [], {}
    for n, item in enumerate(items, start=1):
        where = f"card {n}"
        if not isinstance(item, dict):
            raise InputError(f"{where}: expected an object")
        _check_keys(item, CARD_KEYS, where)
        card_id = _text(item, "id", where)
        where = f"card {n} ({card_id})"
        if not ID_RE.match(card_id):
            raise InputError(f"{where}: id may only contain letters, digits, "
                             "'-' and '_'")
        if card_id.casefold() in seen:  # Anki tags ignore case
            raise InputError(f"{where}: same id as card {seen[card_id.casefold()]}")
        seen[card_id.casefold()] = n

        s = {**deck, **{k: item[k] for k in SETTING_KEYS if k in item}}
        if not isinstance(s["note_type"], str) or not s["note_type"].strip():
            raise InputError(f"{where}: 'note_type' must be a non-empty string")
        cards.append(Card(
            id=card_id,
            front=_text(item, "front", where),
            back=_text(item, "back", where),
            front_voice=_voice(s["front_audio"], "front_audio", where),
            back_voice=_voice(s["back_audio"], "back_audio", where),
            note_type=s["note_type"].strip(),
        ))
    return cards
