<p align="center"><img src="https://raw.githubusercontent.com/thebjorn/seeqbox/main/assets/icon.png" alt="seeqbox secure storage cube" width="160"></p>

# seeqbox

[![Tests](https://github.com/thebjorn/seeqbox/actions/workflows/ci.yml/badge.svg)](https://github.com/thebjorn/seeqbox/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/thebjorn/seeqbox/branch/main/graph/badge.svg)](https://codecov.io/gh/thebjorn/seeqbox)
[![Downloads](https://static.pepy.tech/badge/seeqbox)](https://pepy.tech/project/seeqbox)
[![Socket](https://socket.dev/api/badge/pypi/package/seeqbox/latest)](https://socket.dev/pypi/package/seeqbox)

**Encrypted, versionable data for your applications.**

seeqbox is a Python library and CLI for keeping private application data in Git.
It encrypts files and their names/metadata with [age](https://age-encryption.org/).
Git stores ciphertext; private keys live elsewhere. An optional
[seeqret](https://github.com/thebjorn/seeqret) adapter supplies age identities.

**Status: 0.1.0, experimental.** Real age integration tests cover recovery,
tampering, conflicts, and Git staging. The implementation has not undergone an
independent security audit. Start with synthetic data and test your recovery
process before entrusting important records to it.

## What it does

- Python API: `put`, `get`, `list`, `delete`, `update`, `verify`, and `rotate`.
- CLI: initialize, seal/unlock a working directory, inspect, and verify a vault.
- Encrypted manifest hides logical filenames, metadata, and plaintext hashes.
- Random object filenames; unchanged objects retain their ciphertext.
- Multiple native age recipients, including a separate recovery identity.
- Atomic manifest replacement, exclusive writer lock, and stale-copy checks.
- Optional keyless pre-commit check against accidentally staging working data.
- No Python runtime dependencies; age is a separate, required executable.

It does not commit or push automatically. It is not a database engine, sync
service, browser SDK, or clinical application. See [the security model](https://github.com/thebjorn/seeqbox/blob/main/SECURITY.md).

## Install

Requires Python 3.12+ and `age` / `age-keygen` on PATH. Tested locally with age
1.3.2. Use the [official age downloads](https://github.com/FiloSottile/age/releases).

```powershell
python -m pip install seeqbox
seeqbox --version
age --version
```

Releases are on [PyPI](https://pypi.org/project/seeqbox/); the
[changelog](https://github.com/thebjorn/seeqbox/blob/main/CHANGELOG.md) lists what each one changed. To work on seeqbox
itself, clone the repository and install it editable:

```powershell
git clone https://github.com/thebjorn/seeqbox.git
cd seeqbox
python -m pip install -e ".[dev]"
```

## Quick start (PowerShell)

Run this in a **separate application project**, not the seeqbox source checkout.
Create a key outside the repository. Back it up separately, or add an offline
recovery recipient. Substitute your actual public recipient for `age1...`.

```powershell
# Choose an existing private directory outside the repository.
age-keygen -o C:\private\seeqbox-identity.txt
$env:SEEQBOX_IDENTITY = 'C:\private\seeqbox-identity.txt'

seeqbox init -r age1...
```

Before adding data, put these rules in the application's `.gitignore`:

```gitignore
/data/
/.seeqbox-state.json
*.key
.env
```

Keep all private identities outside the repository regardless of extension.
Ignore rules do not remove files already tracked by Git. This source repository
also ignores `/vault/` to prevent committing development fixtures; your consuming
application should track its encrypted `vault/` directory.

```powershell
New-Item -ItemType Directory data
Set-Content data\example.txt 'Only synthetic sample data'
seeqbox seal data
seeqbox verify
git add vault .gitignore
seeqbox check-staged --workdir data
git commit -m 'Store encrypted dataset'
git push
```

On another authorized machine, clone the app repository, configure an identity,
and restore:

```powershell
$env:SEEQBOX_IDENTITY = 'C:\private\seeqbox-identity.txt'
seeqbox unlock data
```

The destination contains plaintext. Protect it with OS permissions and disk
encryption. Include generated reports, notebook outputs, logs, and exports in
your project's privacy policy too; the staging guard is scoped to `data/` and
`vault/`, not arbitrary copies elsewhere.

Global options precede the command:

```powershell
seeqbox --vault private-vault --identity C:\private\identity.txt verify
```

## Python API

```python
from seeqbox import FileIdentity, Vault

# One-time initialization uses public keys only:
# Vault.create("vault", ["age1..."])

vault = Vault("vault", FileIdentity("C:/private/seeqbox-identity.txt"))
vault.put("observations/sample.json", b'{"example": true}', {"source": "synthetic"})
content = vault.get("observations/sample.json")
entries = vault.list()  # decrypted names and metadata: do not log sensitive values
vault.verify()

# Batch updates become visible together through one manifest replacement.
vault.update({"one.txt": (b"one", {}), "two.txt": (b"two", {})})
```

Names are portable relative paths. Metadata is any JSON object. `put` returns
`False` for an unchanged object. A `Vault` is a snapshot: reopen it after another
writer commits a change. Errors are `SeeqboxError`, `IntegrityError`, and
`ConflictError`. See [format v1](https://github.com/thebjorn/seeqbox/blob/main/docs/format.md) for interoperability and recovery.

## Using seeqret

The optional adapter fetches **native age identity text**, not a seeqret NaCl key.
Store it through your normal secure seeqret workflow. The adapter passes it to
age on stdin, not in process arguments or a temporary plaintext identity file.

```python
from seeqbox import SeeqretIdentity, Vault

vault = Vault("vault", SeeqretIdentity("AGE_IDENTITY", app="seeqbox", env="local"))
```

```powershell
# Install the optional adapter from the seeqbox source checkout:
python -m pip install -e '.[seeqret]'
# Then, from the consuming application project:
seeqbox --seeqret-key AGE_IDENTITY verify
```

A custom `IdentityProvider` can supply other key stores.
The provider runs trusted code and has access to private identity material.

## Changes, deletion, and recipients

- `seal data` imports files. A missing file is a conflict, not an implicit deletion.
  Use `seal data --prune` to explicitly remove missing entries.
- `unlock data` refreshes an unchanged working copy. It refuses to overwrite local
  modifications or unrelated files and removes only unchanged managed files that
  were deleted from the manifest. Preserve and reconcile conflicting edits yourself.
- Concurrent Git branches can conflict on `manifest.age`. Version 0.1 does **not**
  merge encrypted manifests. Restore both versions separately and reconcile locally.
- `seeqbox recipients -r age1... -r age1...` replaces the recipient set and
  re-encrypts all current objects. Include every intended recipient, including recovery.
- Removing a recipient cannot revoke old ciphertext, historical commits, or copies.
  Old blobs remain deliberately; no automatic garbage collection is implemented.

## Git hook

Add this to your existing pre-commit hook, or use it as `.git/hooks/pre-commit`
(make it executable on Unix):

```sh
#!/bin/sh
exec seeqbox check-staged --workdir data
```

The guard reads **staged bytes**, rejects plaintext workdir files, unexpected
vault paths, private-key markers in configuration, and missing age headers.
An age header is not proof of valid encryption. Run `verify` with your private key
before pushing. Hooks are bypassable and do not replace review of staged changes.

## Limits and development

Objects are limited to 64 MiB and the encrypted manifest to 16 MiB. Encryption and
directory operations buffer data in memory; use small datasets initially. For a
live SQLite database, create a consistent snapshot with SQLite's backup API
before sealing. Raw filesystem copies of active databases are not supported.

```powershell
python -m pip install -e '.[dev]'
python -m pytest -q
rainbow-fmt check src tests
python -m build
```

Tests generate temporary identities and use exclusively synthetic data. CI tests
Windows, Linux, and macOS. Future work includes streaming large objects, structured
merge tooling, and JavaScript bindings to the documented format.

## Contributing

1. Fork it
2. It is appreciated (but not required) if you raise an issue first:
   https://github.com/thebjorn/seeqbox/issues
3. Create your feature branch (`git checkout -b my-new-feature`)
4. Commit your changes (`git commit -am 'Add some feature'`), after running
   the checks listed above and adding a line to the `Unreleased` section of
   [CHANGELOG.md](https://github.com/thebjorn/seeqbox/blob/main/CHANGELOG.md)
5. Push to the branch (`git push origin my-new-feature`)
6. Create new Pull Request

MIT licensed. The generated project icon is in `assets/icon.png`.
