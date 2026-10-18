# Releasing

Releases are published to [PyPI](https://pypi.org/project/seeqbox/) from
GitHub Actions by [trusted publishing](https://docs.pypi.org/trusted-publishers/):
no password or token is stored anywhere. The workflow is
[`.github/workflows/publish.yml`](../.github/workflows/publish.yml).

## One-time setup

1. On pypi.org, *Your account → Publishing → Add a new pending publisher →
   GitHub* (after the first release: the project's *Settings → Publishing*):

   | Field             | Value         |
   | ----------------- | ------------- |
   | PyPI project name | `seeqbox`     |
   | Owner             | `thebjorn`    |
   | Repository name   | `seeqbox`     |
   | Workflow name     | `publish.yml` |
   | Environment name  | `pypi`        |

2. On GitHub, *Settings → Environments → New environment* named `pypi`.
   Optionally add yourself as a required reviewer: the `publish` job then
   waits for approval before uploading. The environment is what the pending
   publisher above is bound to; a job outside it cannot publish.

## Making a release

The version lives in three files that must agree: `pyproject.toml`,
`src/seeqbox/__init__.py` and `dkbuild.yml` (`package.version`, which also
lists `__init__.py` under `package.versioned` so that
[dktools](https://github.com/thebjorn/dktools) finds it in the `src` layout).
Between releases they hold the *last released* version; there is no `.dev`
suffix. `tests/test_package.py` checks that the installed metadata matches
`__version__`, so reinstall (`python -m pip install -e ".[dev]"`) after a bump.

1. Rename the `Unreleased` section of `CHANGELOG.md` to the new version and
   date (`## 0.2.0 - 2026-11-01`); commit to `main` and wait for a green
   `Tests` run.
2. On `main`, run `dk upversion -t` for a patch release, `dk upversion -i -t`
   for a minor one or `dk upversion -m -t` for a major one
   (`dk upversion -s 1.2.3 -t` sets an exact version). It bumps the three
   files, commits them, tags `v` + version and pushes the commit and the tag.
   Without `-t` it only edits the files.
3. The tag starts the `Publish` workflow: the `test` job runs the formatting
   check and the test suite with real age; `build` builds the sdist and the
   wheel, checks that the wheel is `seeqbox-<version>-…`, runs `twine check`
   and extracts the version's section of `CHANGELOG.md` (`ci/release_notes.py`,
   which fails when the section is missing); `publish` uploads to PyPI in the
   `pypi` environment; `release` creates the GitHub release with the changelog
   section as its notes and the distributions attached.

PyPI never accepts the same version twice: a broken release is fixed with a
new version (and the old one can be *yanked* on PyPI). A tag whose version
does not match the wheel (the files were not bumped) fails in the `build` job
and publishes nothing. The GitHub release is created only after PyPI accepted
the upload, so a rejected version is never announced.
