"""Explicit export/import of a plaintext working directory.
"""

from pathlib import Path
import os

from .age import FileIdentity
from .errors import ConflictError, SeeqboxError
from .files import (
    MAX_MANIFEST_SIZE,
    STATE_NAME,
    atomic_write,
    bounded_read,
    check_names,
    digest,
    json_bytes,
    read_json,
    reject_links,
)
from .vault import Vault


def _directory(vault: Vault, directory: str | Path) -> Path:
    directory = Path(directory).absolute()
    reject_links(directory)
    directory = directory.resolve()
    if directory == vault.root or directory in vault.root.parents or vault.root in directory.parents:
        raise SeeqboxError("Working directory and encrypted vault must be separate.")

    if isinstance(vault.identity, FileIdentity):
        if any(directory == p or directory in p.parents for p in vault.identity.paths):
            raise SeeqboxError("Private identity files must be outside the working directory.")

    if directory.exists() and not directory.is_dir():
        raise SeeqboxError("Working directory must be a directory.")

    return directory


def _state(vault: Vault, directory: Path) -> dict | None:
    path = directory / STATE_NAME
    reject_links(path)
    if not path.exists():
        return None

    state = read_json(bounded_read(path, MAX_MANIFEST_SIZE))
    if (
        state.get("vault_id") != vault.vault_id
        or not isinstance(state.get("generation"), str)
        or not isinstance(state.get("files"), dict)
    ):
        raise ConflictError("Working directory belongs to a different or invalid vault.")

    check_names(state["files"])
    if any(not isinstance(value, str) or len(value) != 64 for value in state["files"].values()):
        raise ConflictError("Invalid working directory state.")

    return state


def _save_state(vault: Vault, directory: Path) -> None:
    atomic_write(
        directory / STATE_NAME,
        json_bytes(
            {
                "vault_id": vault.vault_id,
                "generation": vault.generation,
                "files": {name: entry["sha256"] for name, entry in vault.list().items()},
            }
        )
        + b"\n",
    )


def _files(directory: Path) -> dict[str, Path]:
    paths = {}

    for folder, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs:
            reject_links(Path(folder) / name)
            if name.casefold() == ".git":
                raise SeeqboxError("Working directory must not contain a Git repository.")
        for name in files:
            path = Path(folder) / name
            reject_links(path)
            if path == directory / STATE_NAME:
                continue
            relative = path.relative_to(directory).as_posix()
            paths[relative] = path

    check_names(paths)
    return paths


def seal(vault: Vault, directory: str | Path, *, prune: bool = False) -> int:
    """Import local files; explicit prune removes records absent from this working copy.
    """
    directory = _directory(vault, directory)
    if not directory.is_dir():
        raise SeeqboxError("Working directory does not exist.")

    state = _state(vault, directory)
    if state is None and vault.list():
        raise ConflictError(
            "Unlock this vault first; a nonempty vault needs a known working copy."
        )

    if state and state["generation"] != vault.generation:
        raise ConflictError("Working copy is stale. Reconcile local edits before sealing.")

    paths = _files(directory)
    values = {name: (bounded_read(path), None) for name, path in paths.items()}
    missing = set(vault.list()) - set(values)
    if missing and not prune:
        raise ConflictError("Files are missing. Restore them or explicitly seal with --prune.")

    changed = vault.update(values, delete=sorted(missing) if prune else ())
    _save_state(vault, directory)
    return changed


def unlock(vault: Vault, directory: str | Path) -> int:
    """Restore files, refusing to overwrite local edits or unrelated files.
    """
    directory = _directory(vault, directory)
    state = _state(vault, directory)
    previous = state["files"] if state else {}
    entries = vault.list()
    # Authenticate all objects before writing any plaintext.
    contents = {name: vault.get(name) for name in entries}
    if directory.exists():
        existing = _files(directory)
        check_names(set(existing) | set(entries))
        for name, path in existing.items():
            current = digest(bounded_read(path))
            if name in previous:
                if current != previous[name] and (
                    name not in entries or current != entries[name]["sha256"]
                ):
                    raise ConflictError(
                        "Working directory contains local edits; nothing was overwritten."
                    )
            elif name in entries and current != entries[name]["sha256"]:
                raise ConflictError("Restore would overwrite an unrelated local file.")
        for name in previous:
            if name not in existing and name in entries:
                raise ConflictError("A local deletion must be reconciled before unlocking.")

    directory.mkdir(parents=True, exist_ok=True)

    for name, content in contents.items():
        target = directory / name
        reject_links(target)
        if not target.exists() or bounded_read(target) != content:
            atomic_write(target, content)

    for name in set(previous) - set(entries):
        target = directory / name
        reject_links(target)
        if target.exists():
            target.unlink()

    _save_state(vault, directory)
    return len(entries)
