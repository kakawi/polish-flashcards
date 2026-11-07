"""Card modes, one per subcommand."""
from .base import Audio, Mode, Note
from .qa import QAMode
from .vocab import VocabMode

MODES = {m.name: m for m in (VocabMode, QAMode)}

__all__ = ["Audio", "MODES", "Mode", "Note", "QAMode", "VocabMode"]
