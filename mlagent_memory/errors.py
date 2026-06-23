class MlagentError(Exception):
    """Base error for user-facing MLagent failures."""


class MemoryRepoNotFound(MlagentError):
    """Raised when a command needs an initialized project memory repo."""


class InvalidSkillPerformance(MlagentError):
    """Raised when performance YAML is missing required fields during SkillVersion approval."""


class SkillVersionNotFound(MlagentError):
    """Raised when a requested SkillVersion or candidate cannot be found."""


class RecordExists(MlagentError):
    """Raised when writing a record whose id already exists without explicit replace."""


class SkillVersionAlreadyExists(MlagentError):
    """Raised when approving a SkillVersion whose approved version already exists without explicit replace."""
