"""Draft a deck file from a plain list: one front per line, machine-translated.

    dom
    Dzień dobry!<TAB>Добрый день!    (own translation after a tab)

becomes
    {"id": "house", "front": "dom", "back": "дом"}
    {"id": "good-afternoon", "front": "Dzień dobry!", "back": "Добрый день!"}

Ids are always English (the front translated to English), so they stay
readable whatever the deck's languages are. Review the file, fix what the
translator got wrong, then import it.
"""
import json
import logging
import re
import unicodedata
from pathlib import Path

from .config import Settings
from .deckfile import norm
from .errors import ProviderError
from .services import Translator

log = logging.getLogger(__name__)

ID_MAX = 40


def slug(text: str) -> str:
    """'Good afternoon, how are you?' -> 'good-afternoon-how-are-you'."""
    ascii_text = (unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
                  .encode("ascii", "ignore").decode())
    s = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(s) > ID_MAX:  # cut at a word boundary
        s = s[:ID_MAX].rsplit("-", 1)[0]
    return s or "card"


def unique(base: str, taken: set) -> str:
    """house, house-2, house-3..."""
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    taken.add(candidate)
    return candidate


def read_lines(path: Path) -> list:
    """[(front, own_translation or "")] for each non-empty line."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raise SystemExit(f"{path}: not a UTF-8 text file")
    entries = []
    for line in lines:
        front, _, back = line.partition("\t")
        if norm(front):
            entries.append((norm(front), norm(back)))
    return entries


def dump(settings: dict, cards: list) -> str:
    """Pretty JSON with one card per line, which is easiest to review and edit."""
    def one(obj):
        return json.dumps(obj, ensure_ascii=False)
    body = ",\n".join(f"    {one(c)}" for c in cards)
    return (f'{{\n  "settings": {one(settings)},\n'
            f'  "cards": [\n{body}\n  ]\n}}\n')


def draft(settings: Settings, src: Path, out: Path, source: str, target: str,
          back_audio: bool, note_type: str):
    if out.exists():
        raise SystemExit(f"{out} already exists; pick another name with -o "
                         "or delete it first")
    entries = read_lines(src)
    if not entries:
        raise SystemExit(f"{src}: no lines to draft")

    to_target = Translator(settings, source, target)
    to_english = (to_target if target == "en"
                  else Translator(settings, source, "en"))

    def translate(t, text):
        try:
            return norm(t.translate(text))
        except ProviderError as e:
            raise SystemExit(f"{e}\nNothing was written.")
        except Exception as e:  # e.g. no translation for this entry
            log.warning("- %s: translation to %s failed: %r", text, t.target, e)
            return ""

    cards, taken = [], set()
    for n, (front, back) in enumerate(entries, start=1):
        back = back or translate(to_target, front)
        english = back if target == "en" and back else translate(to_english, front)
        card = {"id": unique(slug(english or front), taken),
                "front": front, "back": back}
        if not back:
            log.warning("- %s: no translation; fill in \"back\" before "
                        "importing", front)
        elif back.casefold() == front.casefold():
            log.warning("- %s: translation is identical to the front; "
                        "check it", front)
        log.info("[%d/%d] %s: %s -> %s", n, len(entries), card["id"], front, back)
        cards.append(card)

    deck_settings = {"front_audio": source,
                     "back_audio": target if back_audio else None,
                     "note_type": note_type}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump(deck_settings, cards), encoding="utf-8")
    log.info("Wrote %d card(s) to %s. Review it, then run: "
             "anki-cards import -i \"%s\"", len(cards), out, out)
