# Working on seeqbox

These instructions apply throughout this repository. Read any more specific
`AGENTS.md` before editing files in its directory.

## Start here

- Read [STYLEGUIDE.md](STYLEGUIDE.md) before changing code. It is the authority
  for formatting, naming, comments, and documentation style.
- Read [README.md](README.md) for the public API, CLI, and application workflow.
- Read [SECURITY.md](SECURITY.md) before changing encryption, identity handling,
  filesystem operations, or Git safeguards.
- Read [docs/format.md](docs/format.md) before changing persisted data or recovery
  behavior. The vault format version is separate from the package version.
- Inspect the working tree before editing. Preserve unrelated user changes.

## Project scope and layout

seeqbox is a Python library and CLI that orchestrates the official age executable
to store encrypted application data in Git. It is a reusable storage component,
not a health-specific application. Python 3.11 and newer are supported.

| Path | Responsibility |
| --- | --- |
| `src/seeqbox/age.py` | age subprocess adapter and identity providers |
| `src/seeqbox/vault.py` | Encrypted manifest, objects, updates, and rotation |
| `src/seeqbox/files.py` | Portable paths and filesystem safeguards |
| `src/seeqbox/workspace.py` | Seal/unlock and local working-state conflicts |
| `src/seeqbox/git.py` | Checks against the Git staging index |
| `src/seeqbox/cli.py` | CLI arguments, commands, and error reporting |
| `src/seeqbox/errors.py` | Public exception types |
| `src/seeqbox/__init__.py` | Public exports and package version |
| `tests/` | Unit and integration tests using synthetic data and real age |
| `.github/workflows/ci.yml` | Cross-platform tests and distribution builds |
| `assets/` | Project icon and asset documentation |

The core package has no Python runtime dependencies. Keep the seeqret identity
adapter optional. The shared style guide includes frontend conventions; this
repository currently contains no frontend or JavaScript toolchain.

## Coding conventions

Follow the full style guide; these are the most relevant points for this codebase:

- Use four spaces, meaningful names, and blank lines between logical steps.
- Aim for 79-character lines; use up to 100 where needed for readability.
- Use `snake_case` for variables and functions, `PascalCase` for classes, and
  `UPPER_SNAKE_CASE` for constants.
- Follow the guide's kebab-case rule for ordinary filenames and directories.
  Python importable modules must remain valid identifiers; preserve established
  Python module, package, and pytest filenames.
- Prefer single quotes for new strings unless they contain a single quote.
  Do not change existing quotes merely to standardize them.
- Group imports as standard library, third-party, then local imports.
- Keep functions focused, ideally under 30 lines and under 50 where practical.
  Keep files around 300-400 lines where practical; avoid deep nesting.
- Document public modules, classes, and functions. Follow the style guide's
  docstring layout, including the indentation of extended descriptions and
  sections. Explain non-obvious decisions in comments.
- Maintain useful type annotations and the public `py.typed` marker.
- Keep changes focused. Avoid unrelated renames, formatting sweeps, or new
  dependencies when implementing a small feature or fix.

## Encryption and data-handling constraints

- Delegate cryptography to age. Do not invent encryption, deterministic
  ciphertext, or an alternative key format.
- Keep logical filenames, metadata, and plaintext hashes inside the encrypted
  manifest. Do not expose them through public object names or configuration.
- Use argument lists for subprocesses, without shell interpolation. Keep secret
  identity material out of command arguments, logs, and exception messages.
- Preserve ordinary age compatibility: individual objects must remain
  recoverable without installing seeqbox.
- Preserve exclusive writer locking, stale-manifest checks, immutable objects,
  and writing ciphertext before atomically replacing the manifest. Failed
  updates must not make the previous committed manifest unusable.
- Keep unchanged object ciphertext stable. Recipient rotation must re-encrypt
  current contents; it cannot revoke access to historical Git revisions.
- Validate paths from manifests and working directories. Retain traversal,
  symlink/reparse-point, Windows device-name, Unicode normalization, and
  case-insensitive/file-directory collision checks.
- Preserve conflict detection and the preflight checks that protect local edits
  during seal/unlock. Do not silently overwrite, prune, or discard user data.
- Check staged bytes when enforcing Git safeguards; the working tree may differ
  from the index. The guard is not proof of encryption or a general data scanner.
- Treat encryption as confidentiality, not sender authentication or rollback
  protection. Keep documented limitations accurate; do not claim an audit or
  regulatory compliance that has not happened.
- Use synthetic records and temporary test identities in tests and examples.
  Keep real records, private keys, decrypted manifests, and sensitive command
  output out of this source repository, public issues, and test logs.

## Development and verification

Run commands from the repository root. Install Python 3.11+ and the official
`age` and `age-keygen` executables on PATH. CI currently uses age 1.3.2.

```text
python -m pip install -e ".[dev]"
age --version
python -m pytest -q
python -m build
```

Tests generate their own identities in temporary directories. They must not
depend on a developer's private key or seeqret vault. Missing age executables
are an environment problem, not a reason to silently skip the integration suite.

Run focused tests while developing. For changes to encryption, persisted data,
filesystem behavior, or the CLI, run the full suite before handing off. Verify
packaging with `python -m build` when changing package metadata, dependencies,
exports, or included files. Documentation-only edits need link/content checks,
not an automatic full test run.

CI tests and builds on Windows, macOS, and Ubuntu with Python 3.11 and 3.13.
Keep Windows paths and subprocess behavior in mind. Use age's `-o` option for
binary output in PowerShell examples rather than shell text redirection.

Add regression tests for meaningful behavior changes, especially tampering,
wrong identities, recovery, stale writers, rotation, path validation, and local
edit conflicts. Prefer real age integration tests for cryptographic behavior;
mocking a successful subprocess does not verify encryption or recovery.

## Completing a change

- Keep README examples consistent with the actual Python API and CLI. Global
  CLI options precede subcommands.
- Update format and security documentation when behavior or guarantees change.
  Preserve compatibility, or document an explicit format-version and recovery
  plan for an incompatible change.
- Review the diff for unintended files and sensitive material before staging.
- Report what changed, the checks actually run, and any remaining limitations.
  If an environment restriction prevents a check, say so explicitly.
