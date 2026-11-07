"""Machine translation through deep-translator (Google, MyMemory or DeepL)."""
import logging
import re
import time

import requests
from deep_translator import DeeplTranslator, GoogleTranslator, MyMemoryTranslator
from deep_translator.constants import MY_MEMORY_LANGUAGES_TO_CODES
from deep_translator.exceptions import (
    ApiKeyException,
    AuthorizationException,
    TooManyRequests,
)

from ..config import Settings
from ..errors import ProviderError

GOOGLE_URL = "https://translate.google.com/m"  # endpoint deep-translator uses

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
    """Translate source-language text, with retries on rate limits.

    Raises ProviderError for problems that will hit every request (rate
    limit after all retries, rejected API key); any other exception is about
    the single text.
    """

    def __init__(self, settings: Settings):
        self.provider = settings.translator
        self.source = settings.source_lang
        self.target = settings.target_lang
        self.delay = settings.request_delay
        self._impl = self._build(settings)  # fail fast on bad config

    def _build(self, s: Settings):
        if self.provider == "google":
            return GoogleTranslator(source=s.source_lang, target=s.target_lang)
        if self.provider == "mymemory":
            return MyMemoryTranslator(
                source=mymemory_code(s.source_lang),
                target=mymemory_code(s.target_lang),
                email=s.mymemory_email,
            )
        if self.provider == "deepl":
            if not s.deepl_api_key:
                raise SystemExit("TRANSLATOR=deepl needs DEEPL_API_KEY in .env")
            return DeeplTranslator(
                api_key=s.deepl_api_key,
                source=s.source_lang,
                target=s.target_lang,
                use_free_api=s.deepl_free,
            )
        raise SystemExit(
            f"Unknown TRANSLATOR {self.provider!r} (use google, mymemory or deepl)"
        )

    def translate(self, text: str, retries: int = 4) -> str:
        """Translate with exponential backoff when the provider rate-limits us."""
        wait = 5
        for attempt in range(1, retries + 1):
            start = time.monotonic()
            try:
                result = self._fetch(text)
                log.debug("translate: %r -> %r (%.2fs)", text, result,
                          time.monotonic() - start)
                time.sleep(self.delay)
                return result
            except (AuthorizationException, ApiKeyException) as e:
                raise ProviderError(f"{self.provider} rejected the API key: {e!r}")
            except TooManyRequests as e:
                log.warning(
                    "translate: HTTP 429 from %s (attempt %d/%d, %.2fs): %r",
                    self.provider, attempt, retries, time.monotonic() - start, e,
                )
                if attempt == 1 and self.provider == "google":
                    log.warning("Probing Google to see why we are blocked...")
                    if "unusual traffic" in self.probe_google(text).lower():
                        raise ProviderError(
                            "Google is showing a CAPTCHA ('unusual traffic') for "
                            "your network/IP. Waiting and retrying will not help. "
                            "Set TRANSLATOR=mymemory or TRANSLATOR=deepl in .env, "
                            "or try later / from another network."
                        )
                if attempt == retries:
                    raise ProviderError(
                        f"{self.provider} is rate-limiting this connection. Run "
                        "again later, or switch TRANSLATOR in .env. Run with -v "
                        "for details."
                    )
                log.warning("waiting %ds before retrying", wait)
                time.sleep(wait)
                wait *= 2

    def _fetch(self, text: str) -> str:
        """One translation request. For MyMemory, inspect all candidate answers:
        its top answer is often just the input echoed back."""
        if self.provider != "mymemory":
            return self._impl.translate(text)

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

    def probe_google(self, text: str = "dom") -> str:
        """Send one request exactly like deep-translator does and log the raw
        reply. Returns the visible text of the response ("" if it failed)."""
        params = {"tl": self.target, "sl": self.source, "q": text}
        start = time.monotonic()
        try:
            r = requests.get(GOOGLE_URL, params=params, timeout=15)
        except requests.RequestException as e:
            log.error("probe: request failed: %r", e)
            return ""
        log.info("probe: HTTP %s in %.2fs (%s)", r.status_code,
                 time.monotonic() - start, r.url)
        for h in ("Retry-After", "Content-Type", "Server", "Via"):
            if h in r.headers:
                log.info("probe: header %s: %s", h, r.headers[h])
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
        log.info("probe: body: %s", body[:400])
        return body
