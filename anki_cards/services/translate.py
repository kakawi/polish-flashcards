"""Machine translation with MyMemory, through deep-translator."""
import logging
import time

from deep_translator import MyMemoryTranslator
from deep_translator.constants import MY_MEMORY_LANGUAGES_TO_CODES
from deep_translator.exceptions import TooManyRequests

from ..config import Settings
from ..errors import ProviderError

log = logging.getLogger(__name__)


def mymemory_code(lang: str) -> str:
    """MyMemory wants region codes (pl -> pl-PL); look them up in its table."""
    if "-" in lang:
        return lang
    for code in MY_MEMORY_LANGUAGES_TO_CODES.values():
        if code.split("-")[0].lower() == lang.lower():
            return code
    raise SystemExit(f"MyMemory does not support language code {lang!r}")


class Translator:
    """Translate text from one language to another, with retries on rate
    limits.

    Raises ProviderError when MyMemory keeps rate-limiting us (e.g. the daily
    quota is used up), which would hit every request; any other exception is
    about the single text.
    """

    def __init__(self, settings: Settings, source: str, target: str):
        self.source = source
        self.target = target
        self.delay = settings.request_delay
        self._impl = MyMemoryTranslator(  # fails fast on unknown languages
            source=mymemory_code(source),
            target=mymemory_code(target),
            email=settings.mymemory_email,
        )

    def translate(self, text: str, retries: int = 4) -> str:
        """Translate with exponential backoff when MyMemory rate-limits us."""
        wait = 5
        for attempt in range(1, retries + 1):
            start = time.monotonic()
            try:
                result = self._fetch(text)
                log.debug("translate: %r -> %r (%.2fs)", text, result,
                          time.monotonic() - start)
                time.sleep(self.delay)
                return result
            except TooManyRequests as e:
                log.warning(
                    "translate: HTTP 429 from MyMemory (attempt %d/%d, %.2fs): %r",
                    attempt, retries, time.monotonic() - start, e,
                )
                if attempt == retries:
                    raise ProviderError(
                        "MyMemory is rate-limiting this connection (its daily "
                        "quota may be used up). Run again later, or set "
                        "MYMEMORY_EMAIL in .env for a larger quota. Run with -v "
                        "for details."
                    )
                log.warning("waiting %ds before retrying", wait)
                time.sleep(wait)
                wait *= 2

    def _fetch(self, text: str) -> str:
        """One translation request. Inspect all candidate answers: MyMemory's
        top answer is often just the input echoed back."""
        results = self._impl.translate(text, return_all=True)
        log.debug("mymemory raw result: %.1500r", results)
        candidates = [r for r in results if isinstance(r, str)]
        matches = [m for m in results if isinstance(m, dict) and m.get("translation")]

        def score(m):
            try:
                return float(m.get("match") or 0)
            except (TypeError, ValueError):
                return 0.0

        candidates += [m["translation"]
                       for m in sorted(matches, key=score, reverse=True)]
        for c in candidates:
            if c.strip().casefold() != text.strip().casefold():
                return c
        return candidates[0] if candidates else text
