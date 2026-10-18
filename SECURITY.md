# Security model

seeqbox 0.1 is an experimental orchestration layer around age, not a new
cryptographic primitive and not an independently audited security product.

## What is protected

The encrypted manifest contains logical filenames, metadata, plaintext hashes,
and SHA-256 hashes binding each encrypted blob to its manifest entry. Objects
are native binary age files. Existing ciphertext corruption is detected by age
and by the manifest's object hashes. Public configuration contains only format
version, random vault ID, and public recipient keys.

Git observers can see recipients, object counts, ciphertext sizes, changes,
commit authors, messages, and timing. No padding or traffic analysis protection
is provided. Use a private repository for real sensitive datasets.

## Trust and limitations

- **Encryption is not sender authentication.** Anyone with the public recipients
  can encrypt a replacement dataset. Protect repository write access and verify
  trusted signed commits/tags when the threat model includes a malicious remote.
  seeqbox does not implement signature verification or rollback detection.
- A compromised unlocked machine can read plaintext and identities. Memory may
  appear in swap or crash dumps; Python and subprocess buffers are not securely
  erased. Use OS disk encryption and restrictive user permissions.
- `unlock`, `get`, and `list` deliberately release plaintext. The library cannot
  prevent applications from logging, indexing, uploading, or retaining it.
- Key files belong outside the repository. seeqret uses a separate local vault;
  never commit its symmetric key or private key alongside encrypted data.
- Identity providers and the selected age executable are trusted. Native age
  recipients only are supported in v1. Do not supply untrusted executable paths
  or identity files that activate external plugins. Interactive passphrase and
  hardware-token flows are not managed by this CLI and may fail or time out.
- Relative-path checks reject traversal, symlinks/reparse points, Windows device
  names, non-NFC names, and case-insensitive collisions. They are not a sandbox
  against hostile processes racing to replace local paths.
- One exclusive lock protects library writers on a local filesystem. It does
  not coordinate independent Git clones or defend against external filesystem
  edits. Avoid network filesystems; do not checkout/pull while a writer is active.
- Ciphertext blobs are written before the manifest. Failed writes can leave
  orphan blobs, but the prior manifest remains authoritative. Atomic replacement
  does not guarantee durability against every hardware/power-loss failure.
- Recipient rotation replaces the manifest and public recipient file separately.
  Interruption between them is detected on open; see the recovery procedure in
  `docs/format.md`. The current process may no longer have a valid key after rotation.
- Directory restore authenticates all objects and checks conflicts before writing,
  but restoration of many plaintext files is not a filesystem-wide transaction.
  A crash may leave a partial working directory; keep your encrypted vault and
  restore into a fresh directory if necessary.
- Removing recipients or entries does not erase historical data. Old keys still
  decrypt old versions. Keep historical recovery keys for retained history.
- `check-staged` is an accidental-disclosure guard for the configured paths. It
  does not prove cryptographic validity or scan arbitrary application outputs.

## Recovery and backups

Keep at least one independent recovery identity outside the machines that hold
the working keys. Include its public recipient from initialization onward.
Back up the repository independently of its hosting account and test restoration
from a fresh clone. A pushed repository without a surviving key is unrecoverable.

## Reporting

Please use GitHub's private vulnerability reporting when enabled. Do not include
private keys, real records, or sensitive plaintext in public issues. Public
reproductions should use synthetic datasets and freshly generated test identities.
