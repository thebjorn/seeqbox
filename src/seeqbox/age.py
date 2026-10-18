"""Thin subprocess adapter; all cryptography is performed by age."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence
import importlib
import shutil
import subprocess

from .errors import SeeqboxError


class IdentityProvider(Protocol):
    """Provide age identity arguments and optional identity bytes on stdin."""

    def identity(self) -> tuple[list[str], bytes | None]: ...


@dataclass(frozen=True)
class FileIdentity:
    """Use one or more age identity files kept outside the repository."""

    paths: tuple[Path, ...]

    def __init__(self, *paths: str | Path):
        object.__setattr__(self, "paths", tuple(Path(p).resolve() for p in paths))

    def identity(self) -> tuple[list[str], bytes | None]:
        if not self.paths or any(not p.is_file() for p in self.paths):
            raise SeeqboxError("An age identity file is missing.")
        return [part for p in self.paths for part in ("-i", str(p))], None


@dataclass(frozen=True)
class SeeqretIdentity:
    """Read native age identity text from seeqret, passing it through stdin."""

    key: str
    app: str = "seeqbox"
    env: str = "local"

    def identity(self) -> tuple[list[str], bytes | None]:
        try:
            module = importlib.import_module("seeqret")
            value = module.get(self.key, app=self.app, env=self.env)
        except Exception:
            raise SeeqboxError("Could not read the identity from seeqret.") from None
        if not isinstance(value, str) or "AGE-SECRET-KEY-" not in value:
            raise SeeqboxError("The seeqret value must contain a native age identity.")
        return ["-i", "-"], (value.rstrip() + "\n").encode("utf-8")


class Age:
    """Invoke a trusted local age executable without a shell."""

    def __init__(self, executable: str = "age", timeout: float = 60):
        self.executable = shutil.which(executable)
        if self.executable is None:
            raise SeeqboxError("age was not found. Install age and add it to PATH.")
        self.timeout = timeout

    def _run(self, args: list[str], data: bytes | None = None) -> bytes:
        try:
            result = subprocess.run(
                [self.executable, *args], input=data if data is not None else b"",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise SeeqboxError("age could not finish the operation.") from None
        if result.returncode:
            # Do not echo stderr: external tools and identity plugins can leak secrets.
            raise SeeqboxError(
                "age failed: check the recipients, identity, and ciphertext."
            )
        return result.stdout

    def encrypt(self, content: bytes, recipients: Sequence[str]) -> bytes:
        if not recipients:
            raise SeeqboxError("At least one recipient is required.")
        args = ["--encrypt"]
        for recipient in recipients:
            # Native keys only in v1: no SSH identities or implicit plugin execution.
            if not recipient.startswith("age1") or not recipient.isalnum():
                raise SeeqboxError("Only native age recipients are supported.")
            args.extend(["-r", recipient])
        return self._run(args, content)

    def decrypt(self, path: Path, identity: IdentityProvider) -> bytes:
        args, data = identity.identity()
        return self._run(["--decrypt", *args, str(path.resolve())], data)
