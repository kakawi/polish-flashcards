"""Exceptions shared by the commands and the services."""


class InputError(Exception):
    """An input file can't be used (bad format, wrong encoding...).
    The whole file is skipped."""


class ProviderError(Exception):
    """A service problem (rate limit, bad API key) that would affect every
    remaining request too, so the run stops."""
