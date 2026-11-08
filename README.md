# anki-cards

Keep Anki decks in sync with JSON files, with text-to-speech audio, using the
[AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.

- **One file = one deck.** The file name (without extension) is the deck name,
  and Unicode names work (`Nazwy Miesięcy.json` → deck `Nazwy Miesięcy`).
- **Front and back audio per deck or per card**, in any language, generated
  with [edge-tts](https://github.com/rany2/edge-tts).
- **The file is the source of truth:** new cards are added, changed cards are
  updated in place (your study progress is kept), unchanged cards are left
  alone, and cards removed from the file are deleted.
- **`draft`** turns a plain word list into a deck file using machine
  translation ([MyMemory](https://mymemory.translated.net/) via
  [deep-translator](https://github.com/nidhaloff/deep-translator)), so you
  can review the translations before they reach Anki.

## Requirements

- Python 3.9+
- Anki desktop, running, with the AnkiConnect add-on (code `2055492159`)
- Internet access (TTS, and translation for `draft`)

## Install

```bash
git clone https://github.com/<you>/anki-cards.git
cd anki-cards
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .                                    # installs the anki-cards command
cp .env.example .env
```

## Usage

```bash
# 1. a word list -> a deck file, translated (one front per line)
anki-cards draft words.txt                 # writes input/words.json
anki-cards draft words.txt --to en --back-audio -o "input/Food.json"

# 2. review/fix input/*.json, then sync every deck file into Anki
anki-cards import
anki-cards import -i "input/Food.json"     # a single file
```

### `import`

| Flag | Meaning |
|------|---------|
| `-i`, `--input` | Folder with one `.json` file per deck, or a single file (default `INPUT_DIR`, i.e. `input`) |
| `--force` | Delete existing decks (all cards, subdecks and study progress) and recreate them. Asks first |
| `-y`, `--yes` | With `--force`, don't ask |
| `-v`, `--verbose` | Debug logging |

### `draft`

| Flag | Meaning |
|------|---------|
| `src` | Text file, one front per line. Your own translation may follow a tab |
| `-o`, `--output` | Deck file to write (default `INPUT_DIR/<src name>.json`); an existing file is never overwritten |
| `--from` | Language of the fronts, also used for front audio (default `pl`) |
| `--to` | Language of the backs (default `ru`) |
| `--back-audio` | Also make audio for the backs, in the `--to` language |
| `--note-type` | Note type for the deck (default `Basic (and reversed card)`) |

Each card's `id` is made from the front's **English** translation
(`pies` → `dog`), so ids stay readable whatever the
languages. Lines that couldn't be translated get an empty `back`, which
`import` rejects until you fill it in.

## Deck files

```json
{
  "settings": {"front_audio": "pl", "back_audio": null, "note_type": "Basic (and reversed card)"},
  "cards": [
    {"id": "house", "front": "dom", "back": "дом"},
    {"id": "breakfast", "front": "Co jesz na śniadanie?", "back": "Jem jajka.",
     "back_audio": "pl", "note_type": "Basic"}
  ]
}
```

See `input-examples/deck.json`.

| Card key | |
|----------|---|
| `id` | Required. Letters, digits, `-`, `_`; unique in the file (ignoring case). Identifies the card in Anki, so the front can be reworded without losing progress. Don't change it |
| `front`, `back` | Required, non-empty |
| `front_audio`, `back_audio`, `note_type` | Optional, override `settings` for this card |

`settings` is required and must set all three keys:

| Setting | |
|---------|---|
| `front_audio` | `"pl"` (language code: its default voice), `"pl-PL-MarekNeural"` (exact voice) or `null` (no audio) |
| `back_audio` | Same |
| `note_type` | Anki note type with `Front` and `Back` fields |

Language codes use these voices: `pl` Zofia, `ru` Svetlana, `uk` Polina,
`en` Aria (US), `de` Katja, `es` Elvira, `fr` Denise, `it` Elsa. For another
voice or language, give the full voice name (`edge-tts --list-voices`).

A key missing on a card inherits the deck setting; `null` turns it off for
that card. The whole file is rejected, before anything reaches Anki, if it
has a missing field, a duplicate or invalid id, or an unknown key (so a typo
like `back_adio` doesn't silently drop audio).

### How sync works

Every note gets two tags (grouped under `anki_cards` in the browser sidebar):

- `anki_cards::id::<id>`: which card of the file it is
- `anki_cards::h::<hash>`: a hash of the card's front, back, note type and
  the contents of its audio files

On each import:

| File vs. Anki | Result |
|---|---|
| New id | Card added |
| Same id, same hash | Nothing |
| Same id, different hash | Fields and audio updated in place, study progress kept |
| Id no longer in the file | Note deleted, with its study progress |

Notes without an id tag (added by hand) are never touched. An empty `cards`
array is rejected rather than emptying the deck; to delete a deck, delete it
in Anki.

A note type can't be changed in place: change it in Anki (*Notes → Change
Note Type*) or rebuild with `--force`.

### Audio files

Each side with audio has its own file, named after the card's id, in a folder
per deck (ids are only unique within a deck):

```
audio/Zwierzęta/cat_front.mp3
audio/Zwierzęta/cat_back.mp3
```

In Anki's media folder, which all decks share, the file is called
`Zwierzęta_cat_front.mp3`.

- An existing file is used as it is, so you can put audio from anywhere else
  under that name. Only missing files are generated.
- Generated files are recorded in the deck folder's `.generated.json`, with
  their text and voice. When a card's text or voice changes, its generated
  file is made again. A file you put there yourself is never overwritten.
- Replacing a file changes the card's hash, so the next import updates the
  card.
- Files of removed cards or renamed ids stay in the folder, and their copies
  stay in Anki's media folder. *Tools → Check Media* in Anki deletes unused
  media.

Close the note in Anki's browser before importing: AnkiConnect can't update
a note that is open there.

## Configuration

Settings are read from environment variables or a `.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANKI_URL` | `http://localhost:8765` | AnkiConnect address |
| `INPUT_DIR` | `input` | Folder with the deck files |
| `AUDIO_DIR` | `audio` | Audio files, as `<deck>/<id>_front.mp3` and `<id>_back.mp3` (see [Audio files](#audio-files)) |
| `MYMEMORY_EMAIL` | | `draft`: optional email that raises MyMemory's daily quota |
| `REQUEST_DELAY` | `0.7` | Seconds to pause between translation requests |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` |

Note types, voices and languages are not configured here: deck files set them
(see [Deck files](#deck-files)), and `draft` takes them as options.

## Project layout

```
anki_cards/
  cli.py          # import / draft commands
  config.py       # Settings, read from .env
  deckfile.py     # deck file format: validation, setting overrides, hash
  sync.py         # deck file -> Anki: add / update / delete
  draft.py        # word list -> deck file
  errors.py
  services/       # reusable in other projects
    anki.py       # AnkiConnect client
    tts.py        # edge-tts, audio/<deck>/<id>_<side>.mp3, language -> voice
    translate.py  # MyMemory with retries
```

## Troubleshooting

Run with `-v` to log every request with timings. MyMemory has a small free
daily quota; when it is used up, `draft` stops after a few retries and
writes nothing. Set `MYMEMORY_EMAIL` in `.env` for a larger quota, or run
again later.

## License

MIT
