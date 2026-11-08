"""Command line: anki-cards import|draft [options]"""
import argparse
import importlib.metadata as md
import logging
import os
import platform
from pathlib import Path
from urllib.parse import urlparse

from .config import Settings
from .draft import draft
from .services import AnkiClient, AudioService
from .sync import Sync, find_input_files

log = logging.getLogger("anki_cards")


def setup_logging(verbose: bool, level_name: str):
    level = logging.DEBUG if verbose else getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("asyncio").setLevel(logging.INFO)


def log_environment(settings: Settings, command: str):
    log.debug("python %s on %s", platform.python_version(), platform.platform())
    for pkg in ("deep-translator", "edge-tts", "requests"):
        try:
            log.debug("%s %s", pkg, md.version(pkg))
        except md.PackageNotFoundError:
            pass
    log.debug("command: %s; config: %s", command, settings)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        for name in (var, var.lower()):
            if os.getenv(name):
                host = urlparse(os.environ[name]).hostname
                log.debug("proxy env %s is set (host: %s)", name, host)


def parse_args(settings: Settings):
    p = argparse.ArgumentParser(
        prog="anki-cards",
        description="Create Anki decks with audio from JSON deck files via "
                    "AnkiConnect. One file = one deck, named after the file.",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    s = sub.add_parser("import", help="sync deck files into Anki",
                       description="Add new cards, update changed ones in place "
                                   "(keeping study progress) and delete cards "
                                   "removed from the file.")
    s.add_argument("-i", "--input", type=Path, default=settings.input_dir,
                   help="folder with one .json file per deck, or a single "
                        "file (default: %(default)s)")
    s.add_argument("--force", action="store_true",
                   help="delete decks that already exist (with all their "
                        "cards and study progress) and recreate them from "
                        "their files; asks for confirmation")
    s.add_argument("-y", "--yes", action="store_true",
                   help="with --force, do not ask for confirmation")

    d = sub.add_parser("draft", help="make a deck file from a plain list, "
                                     "machine-translated",
                       description="Make a deck file from a text file with one "
                                   "front per line (an own translation may "
                                   "follow a tab). Ids are generated in English.")
    d.add_argument("src", type=Path, help="text file, one front per line")
    d.add_argument("-o", "--output", type=Path, default=None,
                   help="deck file to write (default: INPUT_DIR/<src name>.json)")
    d.add_argument("--from", dest="source", default="pl",
                   help="language of the fronts, also used for front audio "
                        "(default: %(default)s)")
    d.add_argument("--to", dest="target", default="ru",
                   help="language to translate the backs into "
                        "(default: %(default)s)")
    d.add_argument("--back-audio", action="store_true",
                   help="make audio for the back too, in the --to language")
    d.add_argument("--note-type", default="Basic (and reversed card)",
                   help="note type for the deck (default: %(default)s)")

    for c in (s, d):
        c.add_argument("-v", "--verbose", action="store_true",
                       help="debug logging (timings, requests, per-card details)")
    return p.parse_args()


def main():
    settings = Settings.from_env()
    args = parse_args(settings)
    setup_logging(args.verbose, settings.log_level)
    log_environment(settings, args.command)

    if args.command == "draft":
        out = args.output or settings.input_dir / f"{args.src.stem}.json"
        draft(settings, args.src, out, args.source, args.target,
              args.back_audio, args.note_type)
        return

    files = find_input_files(args.input)
    if not files:
        raise SystemExit(f"No .json files found in {args.input}")
    anki = AnkiClient(settings.anki_url)
    log.debug("AnkiConnect version: %s", anki.version())
    Sync(anki, AudioService(settings.audio_dir)).run(files, args.force, args.yes)
