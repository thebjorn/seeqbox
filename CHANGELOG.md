# Changelog

All notable changes to seeqbox. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). The vault format version is
separate from the package version ([docs/format.md](docs/format.md)).

## Unreleased

- Encrypted vaults in Git: immutable age objects behind an encrypted,
  atomically replaced manifest, with exclusive writer locking, stale-manifest
  checks, and recipient rotation.
- `seeqbox` CLI: `init`, `put`, `get`, `list`, `verify`, `delete`, `seal`,
  `unlock`, and `recipients`.
- Identity from age identity files or from seeqret (optional extra).
- Portable path validation and local-edit conflict detection for seal/unlock.
- A staged-content guard for Git pre-commit hooks.
