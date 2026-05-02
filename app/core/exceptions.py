class EncounterCounterError(RuntimeError):
    """Base exception for application-specific runtime errors."""


class ModeNotImplementedError(EncounterCounterError):
    """Raised when a mode exists in the UI but is not implemented yet."""


class TemplateLoadError(EncounterCounterError):
    """Raised when a required template is missing or unreadable."""


class SingleInstanceError(EncounterCounterError):
    """Raised when another scanning session is already running."""
