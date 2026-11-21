"""Process exit codes, following BSD ``sysexits.h`` where one fits."""

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    #: The use case refused the request (e.g. email taken, key reused).
    REJECTED = 1
    #: Bad arguments or input that fails validation (argparse also exits with 2).
    USAGE = 2
    #: Storage is unavailable: safe to retry, with the same --idempotency-key.
    TEMPFAIL = 75
    #: Missing or invalid API token.
    NOPERM = 77
    #: The deployment is misconfigured, e.g. the schema needs ``todo db upgrade``.
    CONFIG = 78
