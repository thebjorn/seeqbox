# seeqbox vault format v1

All JSON is UTF-8. Writers use sorted keys, compact separators, and finite JSON
values. Duplicate JSON keys are rejected. The format version is independent of
the Python package version. Unknown versions fail closed.

## Directory layout

| Path | Encoding | Contents |
| --- | --- | --- |
| `format.json` | Plain JSON | `format`, `version`, `vault_id` |
| `recipients.txt` | Plain ASCII | Native age public recipients, one per line |
| `manifest.age` | Binary age | Encrypted manifest JSON |
| `objects/<32 lowercase hex>.age` | Binary age | Original object bytes |
| `.gitignore` | Text | Local lock and transient write-file exclusions |
| `.write-lock` | Local, ignored | Exclusive writer lock |

`vault_id` and blob basenames are independently generated random UUID4 hex values.
Object names, metadata, and plaintext hashes do not appear in public filenames.
No deterministic encryption or public plaintext fingerprints are used.

The public descriptor is:

```json
{"format":"seeqbox","version":1,"vault_id":"<32 lowercase hex>"}
```

## Encrypted manifest

The following is a schematic example, not a valid encrypted file:

```json
{
  "format": "seeqbox",
  "version": 1,
  "vault_id": "<same ID as format.json>",
  "recipients": ["age1..."],
  "objects": {
    "example.txt": {
      "blob": "<32 lowercase hex>.age",
      "ciphertext_sha256": "<SHA-256 of the age file, 64 lowercase hex>",
      "sha256": "<SHA-256 of the plaintext, 64 lowercase hex>",
      "size": 22,
      "metadata": {"source": "synthetic"}
    }
  }
}
```

Each blob decrypts directly to the original bytes. The manifest ciphertext hash
is used as an optimistic concurrency token. It is not a signature or proof of
freshness. Name normalization and path restrictions are implemented in
`seeqbox.files.portable_name`; case-insensitive and file/directory collisions
are rejected.

Update protocol: acquire exclusive local `.write-lock`, compare the current
manifest ciphertext hash with the opened snapshot, write new immutable objects,
encrypt and atomically replace the manifest, then release the lock. A metadata-
only update retains the object's ciphertext. Deletes only remove manifest entries.
Re-encryption always uses fresh randomness from age.

## Plaintext working state

`data/.seeqbox-state.json` records `vault_id`, the manifest ciphertext hash as
`generation`, and a `files` mapping of names to plaintext SHA-256 hashes. It is
local plaintext, not trusted cryptographic metadata. Ignore the entire working
directory. Its purpose is to detect stale copies and protect unsealed edits.

## Recovery without seeqbox

Use age's `-o` option to avoid PowerShell text redirection altering binary output:

```powershell
age -d -i C:\private\identity.txt -o C:\private\manifest.json vault\manifest.age
```

Read the decrypted manifest in that private location. For each entry, decrypt the
referenced blob to the intended private destination, creating directories first:

```powershell
age -d -i C:\private\identity.txt -o C:\private\recovered.bin vault\objects\BLOB.age
```

Replace `BLOB.age` with the exact manifest entry. Verify the ciphertext SHA-256,
plaintext SHA-256, and byte size against the entry. Do not commit the decrypted
manifest or recovered files. A recovery tool must validate relative paths before
using manifest names as filesystem paths.

If interrupted recipient rotation causes `recipients.txt` to disagree with the
manifest, decrypt the current manifest with a **new** authorized identity and
restore its `recipients` array to `recipients.txt`, one per line. Alternatively,
restore both public configuration and manifest from the same known-good Git
commit using the corresponding old identity. Never mix configurations from
different revisions. Confirm no writer is active before removing a stale lock.

## Compatibility

The file format does not depend on Python, SQLite, or seeqret. A JavaScript client
can implement the same layout with a compatible age implementation. CLI clients
can use `list` for JSON and `get --output` for binary data. All global CLI options
precede the subcommand. There is no custom cryptography to port.
