"""Command line: python -m anki_cards <mode> [options]"""
import argparse
import dataclasses
import importlib.metadata as md
import logging
import os
import platform
from pathlib import Path
from urllib.parse import urlparse

from .config import Settings
from .modes import MODES
from .pipeline import Pipeline, find_input_files
from .services import AnkiClient, AudioService

log = logging.getLogger("anki_cards")


def setup_logging(verbose: bool, level_name: str):
    level = logging.DEBUG if verbose else getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("asyncio").setLevel(logging.INFO)


def log_environment(settings: Settings, mode: str):
    log.debug("python %s on %s", platform.python_version(), platform.platform())
    for pkg in ("deep-translator", "edge-tts", "requests"):
        try:
            log.debug("%s %s", pkg, md.version(pkg))
        except md.PackageNotFoundError:
            pass
    log.debug("mode: %s; config: %s", mode, settings)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        for name in (var, var.lower()):
            if os.getenv(name):
                host = urlparse(os.environ[name]).hostname
                log.debug("proxy env %s is set (host: %s)", name, host)


def parse_args(settings: Settings):
    p = argparse.ArgumentParser(
        prog="python -m anki_cards",
        description="Create Anki decks with audio from a folder of files via "
                    "AnkiConnect. One file = one deck, named after the file.",
    )
    sub = p.add_subparsers(dest="mode", required=True, metavar="MODE")
    for name, mode in MODES.items():
        s = sub.add_parser(name, help=mode.help, description=mode.help)
        default_input = settings.input_dir / name
        s.add_argument("-i", "--input", type=Path, default=default_input,
                       help=f"folder with one {'/'.join(mode.suffixes)} file "
                            "per deck, or a single file (default: %(default)s)")
        s.add_argument("--force", action="store_true",
                       help="delete decks that already exist (with all their "
                            "cards and study progress) and recreate them from "
                            "their files; asks for confirmation")
        s.add_argument("-y", "--yes", action="store_true",
                       help="with --force, do not ask for confirmation")
        s.add_argument("--voice", default=None, metavar="NAME",
                       help="edge-tts voice, e.g. pl-PL-MarekNeural "
                            f"(default: TTS_VOICE = {settings.tts_voice})")
        s.add_argument("-v", "--verbose", action="store_true",
                       help="debug logging (timings, requests, per-entry details)")
    return p.parse_args()


def main():
    settings = Settings.from_env()
    args = parse_args(settings)
    if args.voice:  # command line overrides .env
        settings = dataclasses.replace(settings, tts_voice=args.voice)
    setup_logging(args.verbose, settings.log_level)
    log_environment(settings, args.mode)

    mode_cls = MODES[args.mode]
    files = find_input_files(args.input, mode_cls.suffixes)
    if not files:
        raise SystemExit(f"No {'/'.join(mode_cls.suffixes)} files found in "
                         f"{args.input}")

    mode = mode_cls(settings)  # fails fast on bad mode config (e.g. translator)
    audio = AudioService(settings.audio_dir, settings.tts_voice,
                         settings.source_lang)
    audio.validate_voice()
    anki = AnkiClient(settings.anki_url)
    log.debug("AnkiConnect version: %s", anki.version())

    Pipeline(mode, anki, audio, settings.tags).run(files, args.force, args.yes)
