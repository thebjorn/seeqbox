"""Immutable age objects with an encrypted, atomically replaced manifest."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence
import os
import re
import uuid

from .age import Age, FileIdentity, IdentityProvider
from .errors import ConflictError, IntegrityError, SeeqboxError
from .files import (
    MAX_MANIFEST_SIZE,
    MAX_OBJECT_SIZE,
    atomic_write,
    bounded_read,
    check_names,
    digest,
    json_bytes,
    portable_name,
    read_json,
    reject_links,
)

FORMAT = "seeqbox"
VERSION = 1
_HEX = re.compile(r"^[0-9a-f]{64}$")
_BLOB = re.compile(r"^[0-9a-f]{32}\.age$")


class Vault:
    """An unlocked snapshot. Reopen after another process changes the vault."""

    def __init__(
        self,
        root: str | Path,
        identity: IdentityProvider,
        *,
        age: Age | None = None,
    ):
        raw = Path(root).absolute()
        reject_links(raw)
        self.root = raw.resolve()
        self.identity = identity
        if isinstance(identity, FileIdentity) and any(
            self.root == path or self.root in path.parents
            for path in identity.paths
        ):
            raise SeeqboxError(
                "Identity files must be outside the encrypted vault."
            )
        self.age = age or Age()
        config = read_json(bounded_read(self.root / "format.json", 4096))
        if (
            config.get("format") != FORMAT
            or config.get("version") != VERSION
            or not re.fullmatch(r"[0-9a-f]{32}", str(config.get("vault_id")))
        ):
            raise IntegrityError("Unsupported or invalid vault format.")
        self.vault_id = config["vault_id"]
        manifest = self.root / "manifest.age"
        encrypted = bounded_read(manifest, MAX_MANIFEST_SIZE)
        self.generation = digest(encrypted)
        # Concurrent replacement must not pair old ciphertext with a new manifest.
        plain = self.age.decrypt(manifest, self.identity)
        if digest(bounded_read(manifest, MAX_MANIFEST_SIZE)) != self.generation:
            raise ConflictError("The vault changed while opening; reopen it.")
        self._manifest = read_json(plain)
        self._validate(self._manifest)
        self._check_recipients()

    @classmethod
    def create(
        cls,
        root: str | Path,
        recipients: Sequence[str],
        *,
        age: Age | None = None,
    ) -> Path:
        """Initialize an empty directory using public keys; no identity needed."""
        root = Path(root).absolute()
        reject_links(root)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise SeeqboxError("Initialize an absent or empty vault directory.")
        recipients = list(dict.fromkeys(recipients))
        engine = age or Age()
        vault_id = uuid.uuid4().hex
        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "vault_id": vault_id,
            "recipients": recipients,
            "objects": {},
        }
        ciphertext = engine.encrypt(json_bytes(manifest), recipients)
        root.mkdir(parents=True, exist_ok=True)
        (root / "objects").mkdir()
        atomic_write(
            root / "format.json",
            json_bytes(
                {
                    "format": FORMAT,
                    "version": VERSION,
                    "vault_id": vault_id,
                }
            )
            + b"\n",
        )
        atomic_write(
            root / "recipients.txt", ("\n".join(recipients) + "\n").encode()
        )
        atomic_write(
            root / ".gitignore",
            b"/.write-lock\n/.seeqbox-*.tmp\n/objects/.seeqbox-*.tmp\n",
        )
        atomic_write(root / "manifest.age", ciphertext)
        return root

    def _validate(self, manifest: dict) -> None:
        if (
            manifest.get("format") != FORMAT
            or manifest.get("version") != VERSION
            or manifest.get("vault_id") != self.vault_id
            or not isinstance(manifest.get("objects"), dict)
            or not isinstance(manifest.get("recipients"), list)
            or not manifest["recipients"]
            or any(not isinstance(r, str) for r in manifest["recipients"])
        ):
            raise IntegrityError("Invalid manifest or vault identity mismatch.")
        check_names(manifest["objects"])
        for entry in manifest["objects"].values():
            if (
                not isinstance(entry, dict)
                or not _BLOB.fullmatch(str(entry.get("blob", "")))
                or not _HEX.fullmatch(str(entry.get("ciphertext_sha256", "")))
                or not _HEX.fullmatch(str(entry.get("sha256", "")))
                or type(entry.get("size")) is not int
                or not 0 <= entry["size"] <= MAX_OBJECT_SIZE
                or not isinstance(entry.get("metadata"), dict)
            ):
                raise IntegrityError("Invalid object entry in manifest.")

    def _check_recipients(self) -> None:
        try:
            text = bounded_read(
                self.root / "recipients.txt", 128 * 1024
            ).decode("ascii")
        except UnicodeError:
            raise IntegrityError("Invalid recipient list.") from None
        recipients = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if recipients != self._manifest["recipients"]:
            raise IntegrityError(
                "Recipient list differs from the encrypted manifest."
            )

    @contextmanager
    def _transaction(self):
        lock = self.root / ".write-lock"
        reject_links(lock)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ConflictError(
                "Vault is locked; check for an active writer."
            ) from None
        try:
            os.close(fd)
            if digest(
                bounded_read(self.root / "manifest.age", MAX_MANIFEST_SIZE)
            ) != self.generation:
                raise ConflictError(
                    "Vault changed since opening; reopen before writing."
                )
            self._check_recipients()
            yield
        finally:
            lock.unlink()

    def _save(self, manifest: dict) -> None:
        self._validate(manifest)
        payload = json_bytes(manifest)
        if len(payload) > MAX_MANIFEST_SIZE - 65536:
            raise SeeqboxError("Manifest exceeds the supported size limit.")
        encrypted = self.age.encrypt(payload, manifest["recipients"])
        atomic_write(self.root / "manifest.age", encrypted)
        self.generation = digest(encrypted)
        self._manifest = manifest

    def list(self) -> dict[str, dict[str, Any]]:
        """Return a detached mapping of names to metadata and integrity fields."""
        return deepcopy(self._manifest["objects"])

    def get(self, object_id: str) -> bytes:
        """Decrypt an object and verify its binding to this manifest."""
        portable_name(object_id)
        try:
            entry = self._manifest["objects"][object_id]
        except KeyError:
            raise SeeqboxError("Object does not exist.") from None
        path = self.root / "objects" / entry["blob"]
        encrypted = bounded_read(path, MAX_OBJECT_SIZE + 1024 * 1024)
        if digest(encrypted) != entry["ciphertext_sha256"]:
            raise IntegrityError(
                "Encrypted object is corrupt or has been substituted."
            )
        plain = self.age.decrypt(path, self.identity)
        if len(plain) != entry["size"] or digest(plain) != entry["sha256"]:
            raise IntegrityError("Object content does not match the manifest.")
        return plain

    def put(
        self,
        object_id: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store bytes and metadata; return False when nothing changed."""
        return bool(self.update({object_id: (content, metadata)}))

    def update(
        self,
        values: dict[str, tuple[bytes, dict | None]],
        *,
        delete: Sequence[str] = (),
    ) -> int:
        """Atomically publish a batch; objects written before a failure are harmless orphans."""
        if set(values).intersection(delete):
            raise SeeqboxError(
                "An object cannot be updated and deleted together."
            )
        with self._transaction():
            manifest = deepcopy(self._manifest)
            entries = manifest["objects"]
            for name in delete:
                portable_name(name)
                if name not in entries:
                    raise SeeqboxError("Cannot delete an unknown object.")
                del entries[name]
            check_names(set(entries) | set(values))
            prepared = []
            for name, (content, metadata) in values.items():
                if not isinstance(content, bytes) or len(
                    content
                ) > MAX_OBJECT_SIZE:
                    raise SeeqboxError(
                        "Content must be bytes, at most 64 MiB per object."
                    )
                old = entries.get(name)
                if metadata is None:
                    metadata = deepcopy(old["metadata"]) if old else {}
                if not isinstance(metadata, dict):
                    raise SeeqboxError("Metadata must be a JSON object.")
                try:
                    metadata = read_json(json_bytes(metadata))
                except (TypeError, ValueError):
                    raise SeeqboxError(
                        "Metadata must be JSON serializable."
                    ) from None
                fingerprint = digest(content)
                if old and old["sha256"] == fingerprint and old[
                    "metadata"
                ] == metadata:
                    # Verify unchanged ciphertext before reporting a successful seal.
                    self.get(name)
                    continue
                prepared.append((name, content, metadata, fingerprint))
            for name, content, metadata, fingerprint in prepared:
                old = entries.get(name)
                if old and old["sha256"] == fingerprint:
                    self.get(name)
                    entries[name] = {**old, "metadata": metadata}
                    continue
                encrypted = self.age.encrypt(content, manifest["recipients"])
                blob = uuid.uuid4().hex + ".age"
                atomic_write(self.root / "objects" / blob, encrypted)
                entries[name] = {
                    "blob": blob,
                    "ciphertext_sha256": digest(encrypted),
                    "sha256": fingerprint,
                    "size": len(content),
                    "metadata": metadata,
                }
            changed = len(prepared) + len(delete)
            if changed:
                self._save(manifest)
            return changed

    def delete(self, object_id: str) -> None:
        """Remove an entry; historical ciphertext is deliberately retained."""
        self.update({}, delete=[object_id])

    def verify(self) -> int:
        """Authenticate and validate every referenced object."""
        for name in self._manifest["objects"]:
            self.get(name)
        return len(self._manifest["objects"])

    def rotate(self, recipients: Sequence[str]) -> None:
        """Re-encrypt current objects for a new recipient set. History remains accessible."""
        recipients = list(dict.fromkeys(recipients))
        with self._transaction():
            manifest = deepcopy(self._manifest)
            manifest["recipients"] = recipients
            # Validate new recipients before creating any objects.
            self.age.encrypt(b"seeqbox recipient validation", recipients)
            for name, entry in manifest["objects"].items():
                encrypted = self.age.encrypt(self.get(name), recipients)
                blob = uuid.uuid4().hex + ".age"
                atomic_write(self.root / "objects" / blob, encrypted)
                entry["blob"] = blob
                entry["ciphertext_sha256"] = digest(encrypted)
            # Manifest is authoritative. A crash between these two replacements is
            # detectable; restore recipients.txt from the decrypted manifest.
            self._save(manifest)
            atomic_write(
                self.root / "recipients.txt",
                ("\n".join(recipients) + "\n").encode(),
            )
