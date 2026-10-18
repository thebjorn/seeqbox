"""Public exceptions. Messages never include decrypted payloads."""


class SeeqboxError(Exception):
    """A vault operation could not be completed."""


class IntegrityError(SeeqboxError):
    """Encrypted content or its authenticated metadata is invalid."""


class ConflictError(SeeqboxError):
    """A concurrent change or local modification requires reconciliation."""
