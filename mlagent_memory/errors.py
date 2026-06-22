class MlagentError(Exception):
    """Base error for user-facing MLagent failures."""


class MemoryRepoNotFound(MlagentError):
    """Raised when a command needs an initialized project memory repo."""
