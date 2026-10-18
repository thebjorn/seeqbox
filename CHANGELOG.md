# Changelog

All notable changes to seeqbox. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). The vault format version is
separate from the package version ([docs/format.md](docs/format.md)).

## 0.1.1 - 2026-10-19

- The PyPI project page shows the project icon and the README links work
  outside the repository.
- Tests cover identity validation, the staged-content guard's rejections,
  manifest and recipient tampering, working-directory conflicts, and the CLI
  identity sources; coverage is reported to Codecov.
- GitHub Actions updated to their current versions.

## 0.1.0 - 2026-10-19

- Encrypted vaults in Git: immutable age objects behind an encrypted,
  atomically replaced manifest, with exclusive writer locking, stale-manifest
  checks, and recipient rotation.
- `seeqbox` CLI: `init`, `put`, `get`, `list`, `verify`, `delete`, `seal`,
  `unlock`, and `recipients`.
- Identity from age identity files or from seeqret (optional extra).
- Portable path validation and local-edit conflict detection for seal/unlock.
- A staged-content guard for Git pre-commit hooks.
