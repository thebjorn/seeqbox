"""Working-directory preflight checks for seal and unlock.
"""

import json

import pytest

from seeqbox import ConflictError, FileIdentity, SeeqboxError, Vault
from seeqbox.workspace import STATE_NAME, seal, unlock


def test_identity_inside_working_directory_rejected(vault, identities, tmp_path):
    work = tmp_path / 'data'
    work.mkdir()
    inside = work / 'identity.txt'
    inside.write_bytes(identities[0][0].read_bytes())
    unlocked = Vault(vault.root, FileIdentity(inside))
    with pytest.raises(SeeqboxError):
        seal(unlocked, work)


def test_working_directory_must_be_a_directory(vault, tmp_path):
    path = tmp_path / 'data'
    path.write_text('not a directory')
    with pytest.raises(SeeqboxError):
        unlock(vault, path)
    with pytest.raises(SeeqboxError):
        seal(vault, tmp_path / 'absent')


def test_git_repository_inside_working_directory_rejected(vault, tmp_path):
    work = tmp_path / 'data'
    (work / '.git').mkdir(parents=True)
    (work / 'note.txt').write_text('synthetic')
    with pytest.raises(SeeqboxError):
        seal(vault, work)


def test_nonempty_vault_requires_a_known_working_copy(vault, tmp_path):
    vault.put('record.txt', b'remote')
    work = tmp_path / 'data'
    work.mkdir()
    (work / 'other.txt').write_text('local')
    with pytest.raises(ConflictError):
        seal(vault, work)
    assert vault.list().keys() == {'record.txt'}


def test_local_deletion_must_be_reconciled_before_unlock(vault, tmp_path):
    vault.put('record.txt', b'remote')
    work = tmp_path / 'data'
    unlock(vault, work)
    (work / 'record.txt').unlink()
    with pytest.raises(ConflictError):
        unlock(vault, work)
    assert not (work / 'record.txt').exists()


def test_state_from_another_vault_rejected(vault, identities, tmp_path):
    work = tmp_path / 'data'
    unlock(vault, work)
    other_root = tmp_path / 'other'
    Vault.create(other_root, [identities[0][1]])
    other = Vault(other_root, vault.identity)
    with pytest.raises(ConflictError):
        seal(other, work)
    with pytest.raises(ConflictError):
        unlock(other, work)


def test_corrupt_state_rejected(vault, tmp_path):
    work = tmp_path / 'data'
    unlock(vault, work)
    state = {'vault_id': vault.vault_id, 'generation': 'x', 'files': {'a.txt': 'short'}}
    (work / STATE_NAME).write_text(json.dumps(state))
    with pytest.raises(ConflictError):
        seal(vault, work)
