"""The staged-content guard's checks of Git's index.
"""

import subprocess

import pytest

from seeqbox import SeeqboxError
from seeqbox.git import check_staged


def _git(root, *args):
    command = ['git', '-C', str(root), *args]
    return subprocess.run(command, capture_output=True, check=True).stdout


def test_guard_requires_a_repository(vault, tmp_path):
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path / 'data', cwd=tmp_path)


def test_guard_requires_subdirectories_inside_the_repository(vault, tmp_path):
    _git(tmp_path, 'init', '-q')
    with pytest.raises(SeeqboxError):
        check_staged(tmp_path, tmp_path / 'data', cwd=tmp_path)
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path.parent / 'elsewhere', cwd=tmp_path)


def test_guard_ignores_files_outside_vault_and_workdir(vault, tmp_path):
    _git(tmp_path, 'init', '-q')
    (tmp_path / 'README.md').write_text('# synthetic project')
    _git(tmp_path, 'add', 'README.md', 'vault')
    assert check_staged(vault.root, tmp_path / 'data', cwd=tmp_path) == 4


def test_guard_rejects_executable_vault_files(vault, tmp_path):
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, 'add', 'vault')
    _git(tmp_path, 'update-index', '--chmod=+x', 'vault/manifest.age')
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path / 'data', cwd=tmp_path)


@pytest.mark.parametrize(
    'name, content',
    [
        ('recipients.txt', 'age1notvalid key\n'),
        ('recipients.txt', '\n'),
        ('recipients.txt', 'agé\n'),
        ('.gitignore', '/.write-lock\n'),
        ('.gitignore', '# AGE-SECRET-KEY-1TEST\n'),
        ('objects/' + '0' * 32 + '.age', 'not an age file'),
        ('notes.txt', 'unexpected plaintext'),
    ],
)
def test_guard_rejects_malformed_vault_files(vault, tmp_path, name, content):
    _git(tmp_path, 'init', '-q')
    path = vault.root / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding='utf-8')
    _git(tmp_path, 'add', 'vault')
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path / 'data', cwd=tmp_path)
