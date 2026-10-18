import os
import io
import zipfile
from pathlib import Path
import subprocess

import pytest

from seeqbox import SeeqboxError, Vault
from seeqbox.cli import main
from seeqbox.git import check_staged


def test_cli_lifecycle(tmp_path, identities, capsys):
    path, recipient = identities[0]
    vault = tmp_path / "vault"
    options = ["--vault", str(vault), "--identity", str(path)]
    assert main([*options, "init", "-r", recipient]) == 0
    source = tmp_path / "source.txt"
    source.write_text("synthetic cli sample")
    assert main([*options, "put", "sample", str(source)]) == 0
    assert main([*options, "verify"]) == 0
    target = tmp_path / "output.txt"
    assert main([*options, "get", "sample", "-o", str(target)]) == 0
    assert target.read_text() == "synthetic cli sample"
    assert main([*options, "get", "sample", "-o", str(target)]) == 1
    assert main([*options, "get", "sample", "-o", str(vault / "leak.txt")]) == 1
    assert main([*options, "delete", "sample"]) == 0
    assert "synthetic cli sample" not in capsys.readouterr().out


def test_cli_missing_age(capsys):
    assert main(["--age", "seeqbox-test-nonexistent-executable", "verify"]) == 1
    assert "not found" in capsys.readouterr().err


def _git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    return result.stdout


def test_staged_guard_reads_index_not_working_tree(vault, tmp_path):
    _git(tmp_path, "init")
    vault.put("sample", b"secret synthetic sample")
    _git(tmp_path, "add", "vault")
    assert check_staged(vault.root, tmp_path / "data", cwd=tmp_path) == 5
    # A plaintext index entry must be rejected even if disk has valid ciphertext.
    path = vault.root / "manifest.age"
    original = path.read_bytes()
    path.write_bytes(b"synthetic accidental plaintext")
    _git(tmp_path, "add", "vault/manifest.age")
    path.write_bytes(original)
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path / "data", cwd=tmp_path)


def test_staged_guard_rejects_plaintext_workdir(vault, tmp_path):
    _git(tmp_path, "init")
    work = tmp_path / "data"
    work.mkdir()
    (work / "sample.txt").write_text("synthetic")
    _git(tmp_path, "add", "data")
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, work, cwd=tmp_path)


def test_staged_guard_rejects_private_keys(vault, tmp_path):
    _git(tmp_path, "init")
    (vault.root / "recipients.txt").write_text("AGE-SECRET-KEY-TEST-NOT-A-REAL-KEY\n")
    _git(tmp_path, "add", "vault")
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path / "data", cwd=tmp_path)


def test_staged_guard_rejects_public_metadata(vault, tmp_path):
    _git(tmp_path, "init")
    config = vault.root / "format.json"
    config.write_text('{"format":"seeqbox","version":1,"vault_id":"' + vault.vault_id + '","patient":"synthetic"}')
    _git(tmp_path, "add", "vault")
    with pytest.raises(SeeqboxError):
        check_staged(vault.root, tmp_path / "data", cwd=tmp_path)


def test_symlink_working_file_rejected(vault, tmp_path):
    from seeqbox.workspace import seal
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic outside data")
    work = tmp_path / "data"
    work.mkdir()
    try:
        (work / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privilege.")
    with pytest.raises(SeeqboxError):
        seal(vault, work)


def test_git_commit_archive_recovery(vault, tmp_path, identities):
    _git(tmp_path, "init")
    vault.put("sample.txt", b"recover from another clone")
    _git(tmp_path, "add", "vault")
    _git(tmp_path, "-c", "user.name=seeqbox-test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-m", "Synthetic encrypted fixture")
    recovered = tmp_path.parent / (tmp_path.name + "-recovered")
    archive = _git(tmp_path, "archive", "--format=zip", "HEAD")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        bundle.extractall(recovered)
    restored = Vault(recovered / "vault", vault.identity)
    assert restored.get("sample.txt") == b"recover from another clone"
