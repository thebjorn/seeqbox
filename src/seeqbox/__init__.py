"""Encrypted, versionable data for your applications.
"""

from .age import Age, FileIdentity, IdentityProvider, SeeqretIdentity
from .errors import ConflictError, IntegrityError, SeeqboxError
from .vault import Vault

__version__ = "0.1.0"
__all__ = [
    "Age",
    "ConflictError",
    "FileIdentity",
    "IdentityProvider",
    "IntegrityError",
    "SeeqboxError",
    "SeeqretIdentity",
    "Vault",
]
