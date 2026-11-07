"""Exceptions shared by the pipeline, the modes and the services."""


class InputError(Exception):
    """An input file can't be used (bad format, wrong encoding...).
    The whole file is skipped."""


class SkipEntry(Exception):
    """This one entry gets no card; the reason is logged and the run goes on."""


class ProviderError(Exception):
    """A service problem (rate limit, bad API key) that would affect every
    remaining entry too, so the run stops."""
