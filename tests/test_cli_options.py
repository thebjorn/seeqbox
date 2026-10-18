"""CLI identity sources, metadata, working directories, and error reporting.
"""

import json
import subprocess
import sys

from seeqbox import __version__
from seeqbox.cli import main


def _options(vault, path):
    return ['--vault', str(vault), '--identity', str(path)]


def test_module_entry_point_reports_the_version():
    command = [sys.executable, '-m', 'seeqbox', '--version']
    result = subprocess.run(command, capture_output=True, check=True)
    assert result.stdout.decode().strip() == __version__


def test_identity_sources_are_validated(tmp_path, identities, capsys, monkeypatch):
    path, recipient = identities[0]
    vault = tmp_path / 'vault'
    assert main(['--vault', str(vault), 'init', '-r', recipient]) == 0

    monkeypatch.delenv('SEEQBOX_IDENTITY', raising=False)
    assert main(['--vault', str(vault), 'verify']) == 1
    assert 'SEEQBOX_IDENTITY' in capsys.readouterr().err

    both = [*_options(vault, path), '--seeqret-key', 'KEY', 'verify']
    assert main(both) == 1

    inside = vault / 'identity.txt'
    inside.write_bytes(path.read_bytes())
    assert main([*_options(vault, inside), 'verify']) == 1

    monkeypatch.setenv('SEEQBOX_IDENTITY', str(path))
    assert main(['--vault', str(vault), 'verify']) == 0


def test_put_with_metadata_file_and_list(tmp_path, identities, capsys):
    path, recipient = identities[0]
    vault = tmp_path / 'vault'
    options = _options(vault, path)
    assert main([*options, 'init', '-r', recipient]) == 0
    source = tmp_path / 'source.txt'
    source.write_text('synthetic')
    metadata = tmp_path / 'metadata.json'
    metadata.write_text('{"kind": "synthetic", "tags": ["a"]}')
    put = [*options, 'put', 'sample', str(source), '--metadata-file', str(metadata)]
    assert main(put) == 0
    capsys.readouterr()

    assert main([*options, 'list']) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing['sample']['metadata'] == {'kind': 'synthetic', 'tags': ['a']}
    assert listing['sample']['size'] == len('synthetic')


def test_seal_unlock_and_recipients_commands(tmp_path, identities, capsys):
    path, recipient = identities[0]
    other_path, other_recipient = identities[1]
    vault = tmp_path / 'vault'
    options = _options(vault, path)
    assert main([*options, 'init', '-r', recipient]) == 0
    work = tmp_path / 'data'
    work.mkdir()
    (work / 'note.txt').write_text('synthetic note')
    assert main([*options, 'seal', str(work)]) == 0
    assert 'Sealed 1' in capsys.readouterr().out

    # Rotation hands the vault to the other key; the old key no longer opens it.
    assert main([*options, 'recipients', '-r', other_recipient]) == 0
    restored = tmp_path / 'restored'
    assert main([*_options(vault, other_path), 'unlock', str(restored)]) == 0
    assert (restored / 'note.txt').read_text() == 'synthetic note'
    assert main([*options, 'verify']) == 1


def test_check_staged_command(tmp_path, identities, capsys, monkeypatch):
    path, recipient = identities[0]
    # The guard is a pre-commit hook: it inspects the repository it runs in.
    monkeypatch.chdir(tmp_path)
    subprocess.run(['git', 'init', '-q'], check=True)
    assert main(['init', '-r', recipient]) == 0
    subprocess.run(['git', 'add', 'vault'], check=True)
    assert main(['check-staged']) == 0
    assert 'Checked 4 staged vault files' in capsys.readouterr().out


def test_filesystem_errors_do_not_leak_paths(tmp_path, identities, capsys):
    path, recipient = identities[0]
    vault = tmp_path / 'vault'
    options = _options(vault, path)
    assert main([*options, 'init', '-r', recipient]) == 0
    source = tmp_path / 'private-record-name.txt'
    source.write_text('synthetic')
    assert main([*options, 'put', 'sample', str(source)]) == 0

    # A file where a directory is needed makes the restore fail at the OS level.
    blocker = tmp_path / 'blocker'
    blocker.write_text('a file where a directory is needed')
    target = blocker / 'private-record-name.txt'
    assert main([*options, 'get', 'sample', '-o', str(target)]) == 1
    error = capsys.readouterr().err
    assert 'Filesystem operation failed' in error
    assert 'private-record-name' not in error
