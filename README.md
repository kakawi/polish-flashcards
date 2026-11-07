# anki-cards

Turn a folder of files into Anki decks with text-to-speech audio, using the
[AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.

There are two modes:

| Mode | Input | Front | Back |
|------|-------|-------|------|
| `vocab` | `.txt`, one word/sentence per line | text + audio | machine translation |
| `qa` | `.json`, question/answer pairs | question + audio | answer + audio (no translation) |

- **One file = one deck.** The file name (without extension) is the deck name,
  and Unicode names work (`Nazwy Miesięcy.txt` → deck `Nazwy Miesięcy`).
- Audio is generated with [edge-tts](https://github.com/rany2/edge-tts).
- Translation (vocab only) uses Google Translate, MyMemory or DeepL via
  [deep-translator](https://github.com/nidhaloff/deep-translator).
- Defaults to Polish → Russian, but any language pair works via `.env`.
- Decks that already exist in Anki are skipped.

## Requirements

- Python 3.9+
- Anki desktop, running, with the AnkiConnect add-on (code `2055492159`)
- Internet access (translation and TTS)

## Install

```bash
git clone https://github.com/<you>/anki-cards.git
cd anki-cards
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Usage

Each mode reads its own folder: `input/vocab/` and `input/qa/`. Open Anki,
then run:

```bash
python -m anki_cards vocab                      # every .txt in input/vocab
python -m anki_cards qa                         # every .json in input/qa
python -m anki_cards qa -i "input/qa/Food.json" # a single file
python -m anki_cards vocab --force              # delete + recreate existing decks (asks first)
python -m anki_cards qa -v                      # verbose log
```

| Flag | Meaning |
|------|---------|
| `-i`, `--input` | Folder with one file per deck, or a single file (default `input/<mode>`) |
| `--force` | Delete decks that already exist and recreate them from their files. Asks for confirmation first |
| `-y`, `--yes` | With `--force`, skip the confirmation prompt |
| `--voice` | edge-tts voice for this run, overriding `TTS_VOICE` |
| `-v`, `--verbose` | Debug logging |

Hidden files (such as `.DS_Store`) and files with another extension are
ignored.

### vocab: words and sentences

One entry per line (see `examples/vocab.example.txt`). The card is
*text + audio → translation*; with the default note type each note also gets a
reversed card. To use your own translation for a line, add it after a tab:

```
Dzień dobry, jak się masz?<TAB>Добрый день, как дела?
```

### qa: questions and answers

A JSON array of objects with `question` and `answer`, both in the source
language (see `examples/qa.example.json`):

```json
[
  {
    "question": "Co jesz na śniadanie?",
    "answer": "Na śniadanie jem jajka i chleb."
  }
]
```

Nothing is translated. Both sides get audio, and cards are one-way (`Basic`
note type). If the file is not valid JSON, or an item has no `question` or
`answer`, the whole file is reported and skipped, so a deck is never built
from half a file.

### Existing decks

If a deck with the file's name already exists in Anki (names are compared
case-insensitively), the whole file is skipped. The deck is created only when
its first card is ready, so a run that fails early leaves nothing behind.

To rebuild a deck from its file, run with `--force`. This **deletes** the
existing deck, including all its cards, any subdecks and your study progress
for those cards, and creates it again. The script lists the decks and their
card counts and waits for you to type `yes` (use `-y` to skip the prompt).
If a run stops half-way (for example a translation rate limit), re-run with
`--force` to rebuild the deck from scratch. Audio files in `audio/` are
reused, so nothing is synthesized twice.

## Configuration

Settings are read from environment variables or a `.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `INPUT_DIR` | `input` | Base input folder; each mode reads `INPUT_DIR/<mode>` |
| `ANKI_URL` | `http://localhost:8765` | AnkiConnect address |
| `VOCAB_NOTE_TYPE` | `Basic (and reversed card)` | Note type for `vocab`; use `Basic` for one-way cards |
| `QA_NOTE_TYPE` | `Basic` | Note type for `qa` |
| `SOURCE_LANG` | `pl` | Source language code |
| `TARGET_LANG` | `ru` | Target language code (vocab) |
| `TTS_VOICE` | `pl-PL-ZofiaNeural` | edge-tts voice (`edge-tts --list-voices`) |
| `AUDIO_DIR` | `audio` | Where audio files are stored; existing `<text>.mp3` files are reused |
| `TAGS` | `auto` | Comma-separated tags for every note |
| `TRANSLATOR` | `google` | `google`, `mymemory` or `deepl` (vocab) |
| `MYMEMORY_EMAIL` | | Optional email that raises MyMemory's daily quota |
| `DEEPL_API_KEY` | | Required for `TRANSLATOR=deepl` |
| `DEEPL_FREE` | `true` | Use DeepL's free API endpoint |
| `REQUEST_DELAY` | `0.7` | Seconds to pause between translation requests |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` |

Note types need the fields `Front` and `Back`.

For example, for Spanish → English:

```
SOURCE_LANG=es
TARGET_LANG=en
TTS_VOICE=es-ES-ElviraNeural
```

## Project layout

```
anki_cards/
  cli.py          # argparse, one subcommand per mode
  config.py       # Settings, read from .env
  errors.py       # InputError / SkipEntry / ProviderError
  pipeline.py     # files -> decks: existing decks, --force, duplicates, audio, stats
  services/
    anki.py       # AnkiConnect client
    tts.py        # edge-tts with an audio cache
    translate.py  # Google / MyMemory / DeepL with retries
  modes/
    base.py       # Mode interface, Note and Audio
    vocab.py
    qa.py
```

### Adding a mode

A mode only decides how to read a file and what a note looks like; the
pipeline does the rest. Create `anki_cards/modes/<name>.py`:

```python
class MyMode(Mode):
    name = "mine"                  # subcommand, and input folder input/mine
    help = "what it does"
    suffixes = (".json",)

    @property
    def note_type(self):
        return "Basic"

    def read(self, path):          # -> list of entries; raise InputError if unusable
        ...

    def key(self, entry):          # Front text, used to skip cards already in the deck
        ...

    def build(self, entry):        # -> Note; raise SkipEntry to leave this entry out
        return Note(fields={"Front": ..., "Back": ...},
                    audio=[Audio(text, "Front")])
```

Then add it to `MODES` in `anki_cards/modes/__init__.py`. Services such as
`Translator` can be created in the mode's `__init__` if it needs them.

## Troubleshooting

```bash
python -m anki_cards vocab -v
```

Verbose mode logs every request with timings. If Google Translate blocks your
network (an "unusual traffic" CAPTCHA page), the script detects it, logs the
reply it got and stops instead of retrying. In that case set
`TRANSLATOR=mymemory` or `TRANSLATOR=deepl` in `.env`.

## Notes

- Machine translation of single words can be wrong or ambiguous. Skim the
  output, or supply your own translation after a tab. If a provider returns
  the original text unchanged, no card is created for that entry.
- Free translation services have limits: Google may block your IP, and
  MyMemory has a small daily quota.
- Changing a note type later does not convert existing cards; use
  *Notes → Change Note Type* in Anki's browser.

## License

MIT
