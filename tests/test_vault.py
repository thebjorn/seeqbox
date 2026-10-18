import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from seeqbox import Age, ConflictError, FileIdentity, IntegrityError, SeeqboxError, SeeqretIdentity, Vault
from seeqbox.files import json_bytes


def test_round_trip_and_metadata_are_private(vault):
    payload = "synthetic confidential sample: blåbær".encode()
    name = "synthetic-notes/private.json"
    metadata = {"description": "synthetic confidential metadata", "nested": [1, True, None]}
    assert vault.put(name, payload, metadata)
    assert vault.get(name) == payload
    assert vault.list()[name]["metadata"] == metadata
    assert vault.verify() == 1
    for path in vault.root.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert payload not in raw
            assert name.encode() not in raw
            assert b"synthetic confidential metadata" not in raw


def test_noop_preserves_manifest_and_ciphertext(vault):
    vault.put("sample.bin", b"\x00\xff\x01")
    before = {p.name: p.read_bytes() for p in vault.root.rglob("*.age")}
    assert not vault.put("sample.bin", b"\x00\xff\x01")
    after = {p.name: p.read_bytes() for p in vault.root.rglob("*.age")}
    assert before == after


def test_metadata_only_update_preserves_blob(vault):
    vault.put("sample", b"x", {"version": 1})
    blob = vault.list()["sample"]["blob"]
    assert vault.put("sample", b"x", {"version": 2})
    assert vault.list()["sample"]["blob"] == blob


def test_empty_bytes_and_delete_keep_history(vault):
    vault.put("empty", b"")
    blob = vault.root / "objects" / vault.list()["empty"]["blob"]
    assert vault.get("empty") == b""
    vault.delete("empty")
    assert vault.list() == {}
    assert blob.exists()
    with pytest.raises(SeeqboxError):
        vault.get("empty")


def test_wrong_identity_cannot_open(vault, identities):
    with pytest.raises(SeeqboxError):
        Vault(vault.root, FileIdentity(identities[1][0]))


def test_object_tamper_rejected(vault):
    vault.put("record", b"original")
    path = vault.root / "objects" / vault.list()["record"]["blob"]
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(IntegrityError):
        vault.get("record")
    with pytest.raises(IntegrityError):
        vault.put("record", b"original")


def test_manifest_tamper_rejected(vault):
    path = vault.root / "manifest.age"
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(SeeqboxError):
        Vault(vault.root, vault.identity)


def test_recipient_tamper_rejected(vault, identities):
    (vault.root / "recipients.txt").write_text(identities[1][1] + "\n")
    with pytest.raises(IntegrityError):
        Vault(vault.root, vault.identity)


def test_stale_writer_cannot_overwrite(vault):
    other = Vault(vault.root, vault.identity)
    vault.put("first", b"1")
    with pytest.raises(ConflictError):
        other.put("second", b"2")
    assert Vault(vault.root, vault.identity).list().keys() == {"first"}


def test_lock_prevents_writes(vault):
    (vault.root / ".write-lock").write_text("synthetic active writer")
    with pytest.raises(ConflictError):
        vault.put("record", b"x")


def test_failed_manifest_write_preserves_previous_snapshot(vault, monkeypatch):
    vault.put("old", b"old")
    previous = (vault.root / "manifest.age").read_bytes()
    original = vault.age.encrypt
    def fail_manifest(data, recipients):
        if data.startswith(b'{"format":"seeqbox"'):
            raise SeeqboxError("synthetic failure")
        return original(data, recipients)
    monkeypatch.setattr(vault.age, "encrypt", fail_manifest)
    with pytest.raises(SeeqboxError):
        vault.put("new", b"new")
    assert (vault.root / "manifest.age").read_bytes() == previous
    assert Vault(vault.root, vault.identity).verify() == 1
    assert not (vault.root / ".write-lock").exists()


def test_multiple_recipients_and_rotation(vault, identities):
    vault.put("record", b"test")
    old_manifest = (vault.root / "manifest.age").read_bytes()
    vault.rotate([identities[0][1], identities[1][1], identities[2][1]])
    for path, _ in identities:
        assert Vault(vault.root, FileIdentity(path)).get("record") == b"test"
    vault.rotate([identities[1][1]])
    assert Vault(vault.root, FileIdentity(identities[1][0])).get("record") == b"test"
    with pytest.raises(SeeqboxError):
        Vault(vault.root, FileIdentity(identities[0][0]))
    historical = vault.root.parent / "historical.age"
    historical.write_bytes(old_manifest)
    assert json.loads(Age().decrypt(historical, FileIdentity(identities[0][0])))["objects"]


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a\\b", "C:/escape", ".git/config", "NUL", "COM1.txt", "a.", "a ", "a//b", ".seeqbox-state.json", "a\x00b"])
def test_unsafe_names_rejected(vault, name):
    with pytest.raises(SeeqboxError):
        vault.put(name, b"x")


def test_collisions_rejected(vault):
    vault.put("Sample", b"x")
    with pytest.raises(SeeqboxError):
        vault.put("sample", b"y")
    with pytest.raises(SeeqboxError):
        vault.put("Sample/child", b"y")


def test_manifest_path_traversal_rejected(vault, identities):
    vault.put("record", b"x")
    document = json.loads(Age().decrypt(vault.root / "manifest.age", vault.identity))
    document["objects"]["record"]["blob"] = "../../outside.age"
    (vault.root / "manifest.age").write_bytes(Age().encrypt(json_bytes(document), [identities[0][1]]))
    with pytest.raises(IntegrityError):
        Vault(vault.root, vault.identity)


def test_seeqret_provider_uses_stdin(vault, identities, monkeypatch):
    calls = []
    def get(key, **kwargs):
        calls.append((key, kwargs))
        return identities[0][0].read_text()
    monkeypatch.setitem(sys.modules, "seeqret", SimpleNamespace(get=get))
    unlocked = Vault(vault.root, SeeqretIdentity("TEST_AGE"))
    unlocked.put("sample", b"test")
    assert unlocked.get("sample") == b"test"
    assert calls[0] == ("TEST_AGE", {"app": "seeqbox", "env": "local"})


def test_plain_age_recovery(vault):
    vault.put("sample", b"portable recovery")
    entry = vault.list()["sample"]
    result = subprocess.run(["age", "-d", "-i", str(vault.identity.paths[0]),
                             str(vault.root / "objects" / entry["blob"])],
                            capture_output=True, check=True)
    assert result.stdout == b"portable recovery"


def test_existing_directory_not_overwritten(tmp_path, identities):
    path = tmp_path / "existing"
    path.mkdir()
    (path / "important.txt").write_text("unchanged")
    with pytest.raises(SeeqboxError):
        Vault.create(path, [identities[0][1]])
    assert (path / "important.txt").read_text() == "unchanged"
