"""The interface every card mode implements.

A mode knows two things: how to read one input file into entries, and how to
turn one entry into a Note. Everything else (decks, --force, duplicates,
audio upload, stats) is handled by the pipeline.

To add a mode: subclass Mode in a new module and add it to MODES in
modes/__init__.py.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings


@dataclass
class Audio:
    text: str   # what to speak
    field: str  # note field the [sound:...] tag is appended to


@dataclass
class Note:
    fields: dict                              # field name -> plain text (escaped later)
    audio: list = field(default_factory=list)  # list[Audio]


class Mode(ABC):
    name: str = ""           # subcommand name, also the default input subfolder
    help: str = ""           # one line for --help
    suffixes: tuple = ()     # file extensions picked up from a folder
    key_field: str = "Front" # field used to detect cards already in the deck

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    @abstractmethod
    def note_type(self) -> str:
        """Anki note type; must have the fields used in build()."""

    @abstractmethod
    def read(self, path: Path) -> list:
        """Parse a file into entries. Raise InputError if it is unusable."""

    @abstractmethod
    def key(self, entry) -> str:
        """The key_field text of the entry, checked before build() so that
        entries already in the deck cost no translation or audio."""

    @abstractmethod
    def build(self, entry) -> Note:
        """Make the note. Raise SkipEntry to leave this entry out, or
        ProviderError to stop the run."""
