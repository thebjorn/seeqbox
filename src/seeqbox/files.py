"""Portable path checks and atomic file replacement."""

from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import stat
import tempfile
import unicodedata

from .errors import IntegrityError, SeeqboxError

STATE_NAME = ".seeqbox-state.json"
MAX_OBJECT_SIZE = 64 * 1024 * 1024
MAX_MANIFEST_SIZE = 16 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def read_json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except (UnicodeError, ValueError, TypeError):
        raise IntegrityError("Invalid JSON document.") from None


def reject_links(path: Path) -> None:
    """Reject symlinks and Windows reparse points in every existing ancestor."""
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SeeqboxError("Symlinks and reparse points are not supported.")


def portable_name(name: str) -> None:
    """Accept relative filenames that are safe on Windows, macOS, and Linux."""
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise SeeqboxError("Invalid object name.")
    if unicodedata.normalize("NFC", name) != name:
        raise SeeqboxError("Object names must use NFC Unicode normalization.")
    parts = name.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved |= {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}
    reserved |= {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in "¹²³"}
    for part in parts:
        if (not part or part in {".", ".."} or part.endswith((".", " "))
                or part.casefold() in {".git", STATE_NAME}
                or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
                or part.split(".")[0].rstrip().upper() in reserved):
            raise SeeqboxError("Object names must be safe relative portable paths.")
    if PurePosixPath(name).is_absolute():
        raise SeeqboxError("Absolute object names are not supported.")


def check_names(names) -> None:
    seen = set()
    for name in names:
        portable_name(name)
        folded = name.casefold()
        if folded in seen:
            raise SeeqboxError("Object names collide on a case-insensitive filesystem.")
        seen.add(folded)
    for name in seen:
        parent = PurePosixPath(name).parent
        while str(parent) != ".":
            if str(parent) in seen:
                raise SeeqboxError("An object name conflicts with a directory name.")
            parent = parent.parent


def bounded_read(path: Path, limit: int = MAX_OBJECT_SIZE) -> bytes:
    reject_links(path)
    if not path.is_file():
        raise IntegrityError("An expected regular file is missing.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise SeeqboxError("File exceeds the supported size limit.")
    return data


def atomic_write(path: Path, data: bytes) -> None:
    reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".seeqbox-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
