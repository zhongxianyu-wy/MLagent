"""User-facing error hierarchy.

All operational failures the CLI should surface cleanly subclass MlagentError.
main() catches MlagentError -> echo + exit 2.
"""


class MlagentError(Exception):
    """Base error for user-facing mlagent failures."""


class MemoryRepoNotFound(MlagentError):
    """Raised when a command needs an initialized project memory repo."""


class RecordExists(MlagentError):
    """Raised when writing a record whose id already exists without explicit replace."""
