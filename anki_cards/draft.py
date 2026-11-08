"""Draft a deck file from a plain list: one front per line, a back may
follow a tab.

    dom
    Co jesz na śniadanie?<TAB>Jem jajka.

becomes (with --translate en)
    {"id": "house", "front": "dom", "back": "house"}
    {"id": "what-do-you-eat-for-breakfast", "front": "Co jesz na śniadanie?",
     "back": "Jem jajka."}

Backs are machine-translated only with --translate, and only where the line
has none; otherwise they are left empty for you to fill in (import rejects
empty backs). Ids are always English (the front translated to English), so
they stay readable whatever the deck's languages are. --front-audio and
--back-audio are written into the deck's settings as given; the audio itself
is made by import.
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
from .services.tts import resolve_voice

log = logging.getLogger(__name__)

ID_MAX = 40


def slug(text: str) -> str:
    """'Good afternoon, how are you?' -> 'good-afternoon-how-are-you'."""
    ascii_text = (unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
                  .encode("ascii", "ignore").decode())
    ascii_text = re.sub(r"['’]", "", ascii_text)  # what's -> whats
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


def check_audio(value, option: str):
    """Fail now rather than at import if the audio value has no voice."""
    if value is not None:
        try:
            resolve_voice(value)
        except KeyError:
            raise SystemExit(f"{option} {value}: no default voice for this "
                             "language; give a voice name, e.g. "
                             "cs-CZ-VlastaNeural (edge-tts --list-voices)")


def draft(settings: Settings, src: Path, out: Path, lang: str, translate_to,
          front_audio, back_audio, note_type: str):
    check_audio(front_audio, "--front-audio")
    check_audio(back_audio, "--back-audio")
    lang = lang.lower()
    target = translate_to.lower() if translate_to else None
    if target == lang:
        raise SystemExit(f"--translate {target} is the language of the fronts "
                         "(--lang); leave --translate out to write the backs "
                         "yourself")
    if out.exists():
        raise SystemExit(f"{out} already exists; pick another name with -o "
                         "or delete it first")
    entries = read_lines(src)
    if not entries:
        raise SystemExit(f"{src}: no lines to draft")

    # only the translators that are needed; none for English fronts
    to_target = Translator(settings, lang, target) if target else None
    to_english = (None if lang == "en" else
                  to_target if target == "en" else
                  Translator(settings, lang, "en"))

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
        own_back = bool(back)
        if not back and to_target:
            back = translate(to_target, front)
        if to_english is None:
            english = front
        elif target == "en" and back:
            english = back
        else:
            english = translate(to_english, front)
        card = {"id": unique(slug(english or front), taken),
                "front": front, "back": back}
        if not back:
            log.warning("- %s: no %s; fill in \"back\" before importing",
                        front, "translation" if to_target else "back after a tab")
        elif not own_back and back.casefold() == front.casefold():
            log.warning("- %s: translation is identical to the front; "
                        "check it", front)
        log.info("[%d/%d] %s: %s -> %s", n, len(entries), card["id"], front, back)
        cards.append(card)

    deck_settings = {"front_audio": front_audio, "back_audio": back_audio,
                     "note_type": note_type}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump(deck_settings, cards), encoding="utf-8")
    log.info("Wrote %d card(s) to %s. Review it, then run: "
             "anki-cards import -i \"%s\"", len(cards), out, out)
