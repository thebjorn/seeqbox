"""Identity providers and the age adapter's input validation.
"""

import sys
from types import SimpleNamespace

import pytest

from seeqbox import Age, FileIdentity, SeeqboxError, SeeqretIdentity


def test_missing_identity_file_is_reported(tmp_path):
    with pytest.raises(SeeqboxError):
        FileIdentity(tmp_path / 'absent.txt').identity()
    with pytest.raises(SeeqboxError):
        FileIdentity().identity()


def test_seeqret_value_must_be_a_native_identity(monkeypatch):
    module = SimpleNamespace(get=lambda key, **kwargs: 'not an age identity')
    monkeypatch.setitem(sys.modules, 'seeqret', module)
    with pytest.raises(SeeqboxError):
        SeeqretIdentity('TEST_AGE').identity()


def test_seeqret_failure_is_wrapped_without_details(monkeypatch):
    def get(key, **kwargs):
        raise RuntimeError('store is locked: /home/user/.seeqret')

    monkeypatch.setitem(sys.modules, 'seeqret', SimpleNamespace(get=get))
    with pytest.raises(SeeqboxError) as info:
        SeeqretIdentity('TEST_AGE').identity()
    assert '.seeqret' not in str(info.value)


def test_only_native_recipients_are_accepted(identities):
    engine = Age()
    with pytest.raises(SeeqboxError):
        engine.encrypt(b'x', [])
    with pytest.raises(SeeqboxError):
        engine.encrypt(b'x', ['ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA'])
    with pytest.raises(SeeqboxError):
        engine.encrypt(b'x', [identities[0][1] + ' --plugin-name evil'])


def test_age_timeout_is_reported(identities):
    engine = Age(timeout=1e-9)
    with pytest.raises(SeeqboxError):
        engine.encrypt(b'x', [identities[0][1]])
