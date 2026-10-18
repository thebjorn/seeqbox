from pathlib import Path
import shutil
import subprocess

import pytest

from seeqbox import FileIdentity, Vault


@pytest.fixture(scope="session")
def identities(tmp_path_factory):
    if not shutil.which("age") or not shutil.which("age-keygen"):
        pytest.fail("Integration tests require age and age-keygen on PATH.")
    directory = tmp_path_factory.mktemp("seeqbox-test-identities")
    pairs = []
    for name in ("alice", "bob", "recovery"):
        path = directory / f"{name}.txt"
        subprocess.run(["age-keygen", "-o", str(path)], capture_output=True, check=True)
        result = subprocess.run(["age-keygen", "-y", str(path)], capture_output=True, check=True)
        pairs.append((path, result.stdout.decode().strip()))
    return pairs


@pytest.fixture
def vault(tmp_path, identities):
    path, recipient = identities[0]
    Vault.create(tmp_path / "vault", [recipient])
    return Vault(tmp_path / "vault", FileIdentity(path))
