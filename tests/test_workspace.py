import pytest

from seeqbox import ConflictError, IntegrityError, SeeqboxError, Vault
from seeqbox.workspace import seal, unlock


def test_seal_restore_and_noop(vault, tmp_path):
    source = tmp_path / "data"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "sample.txt").write_text("synthetic sample")
    assert seal(vault, source) == 1
    generation = vault.generation
    assert seal(vault, source) == 0
    assert vault.generation == generation
    target = tmp_path / "restored"
    assert unlock(vault, target) == 1
    assert (target / "nested" / "sample.txt").read_text() == "synthetic sample"


def test_stale_working_copy_refuses_seal(vault, tmp_path):
    source = tmp_path / "data"
    unlock(vault, source)
    (source / "local.txt").write_text("local")
    vault.put("remote.txt", b"remote")
    with pytest.raises(ConflictError):
        seal(vault, source)


def test_unlock_preserves_local_edits(vault, tmp_path):
    vault.put("sample.txt", b"original")
    target = tmp_path / "data"
    unlock(vault, target)
    (target / "sample.txt").write_text("local edit")
    vault.put("sample.txt", b"remote edit")
    with pytest.raises(ConflictError):
        unlock(vault, target)
    assert (target / "sample.txt").read_text() == "local edit"


def test_unlock_refreshes_unmodified_copy(vault, tmp_path):
    vault.put("sample.txt", b"original")
    target = tmp_path / "data"
    unlock(vault, target)
    vault.put("sample.txt", b"updated")
    unlock(vault, target)
    assert (target / "sample.txt").read_bytes() == b"updated"


def test_missing_files_require_explicit_prune(vault, tmp_path):
    vault.put("sample.txt", b"original")
    target = tmp_path / "data"
    unlock(vault, target)
    (target / "sample.txt").unlink()
    with pytest.raises(ConflictError):
        seal(vault, target)
    assert seal(vault, target, prune=True) == 1
    assert not vault.list()


def test_unlock_removes_only_unmodified_managed_deleted_files(vault, tmp_path):
    vault.put("sample.txt", b"original")
    target = tmp_path / "data"
    unlock(vault, target)
    (target / "unrelated.txt").write_text("leave me")
    vault.delete("sample.txt")
    unlock(vault, target)
    assert not (target / "sample.txt").exists()
    assert (target / "unrelated.txt").read_text() == "leave me"


def test_corrupt_object_does_not_partially_restore(vault, tmp_path):
    vault.put("a.txt", b"first")
    vault.put("b.txt", b"second")
    blob = vault.root / "objects" / vault.list()["b.txt"]["blob"]
    blob.write_bytes(b"bad")
    target = tmp_path / "data"
    with pytest.raises(IntegrityError):
        unlock(vault, target)
    assert not target.exists()


def test_no_plaintext_inside_vault(vault):
    with pytest.raises(SeeqboxError):
        unlock(vault, vault.root / "data")
    with pytest.raises(SeeqboxError):
        seal(vault, vault.root.parent)


def test_unrelated_conflict_not_overwritten(vault, tmp_path):
    vault.put("a.txt", b"vault")
    target = tmp_path / "data"
    target.mkdir()
    (target / "a.txt").write_bytes(b"unrelated")
    with pytest.raises(ConflictError):
        unlock(vault, target)
    assert (target / "a.txt").read_bytes() == b"unrelated"
