"""Print the ``CHANGELOG.md`` section of one version, for the GitHub release.

   Used by the ``build`` job in ``.github/workflows/publish.yml``
   (docs/releasing.md): ``python ci/release_notes.py v0.1.0``. The section is
   the one headed ``## 0.1.0 - DATE`` (the tag's ``v`` is dropped); its body,
   up to the next ``##`` heading, is printed with a line naming the PyPI
   release first. A missing section is an error (exit 1), so a tag cannot be
   released without its changelog entry.
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / 'CHANGELOG.md'


def release_notes(changelog: str, version: str) -> str:
    """The body of ``changelog``'s section for ``version`` (with or without ``v``).
    """
    version = version.removeprefix('v')
    pattern = re.compile(rf'^## {re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)', re.M | re.S)
    match = pattern.search(changelog)
    if match is None:
        raise LookupError(f'CHANGELOG.md has no section for version {version}')

    body = match.group(1).strip('\n')
    pypi = f'https://pypi.org/project/seeqbox/{version}/'
    return f'Released on PyPI: [seeqbox {version}]({pypi})\n\n{body}\n'


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write('usage: release_notes.py VERSION\n')
        return 2

    try:
        sys.stdout.write(release_notes(CHANGELOG.read_text(encoding='utf-8'), argv[1]))
    except LookupError as error:
        sys.stderr.write(f'error: {error}\n')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
