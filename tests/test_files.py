"""Strict JSON parsing, object name validation, and bounded reads.
"""

import pytest

from seeqbox import IntegrityError, SeeqboxError
from seeqbox.files import bounded_read, portable_name, read_json


@pytest.mark.parametrize(
    'document',
    [b'[]', b'"text"', b'{"a": 1, "a": 2}', b'{not json', b'\xff'],
)
def test_read_json_accepts_only_objects_with_unique_keys(document):
    with pytest.raises(IntegrityError):
        read_json(document)


def test_read_json_returns_the_object():
    assert read_json(b'{"a": [1, 2]}') == {'a': [1, 2]}


@pytest.mark.parametrize('name', [None, 7, '', 'a' * 1025, 'é.txt'])
def test_portable_name_rejects_invalid_and_non_nfc_names(name):
    with pytest.raises(SeeqboxError):
        portable_name(name)


def test_bounded_read_enforces_the_limit_and_regular_files(tmp_path):
    path = tmp_path / 'sample.bin'
    path.write_bytes(b'0123456789')
    assert bounded_read(path, limit=10) == b'0123456789'
    with pytest.raises(SeeqboxError):
        bounded_read(path, limit=9)
    with pytest.raises(IntegrityError):
        bounded_read(tmp_path / 'absent.bin')
    with pytest.raises(IntegrityError):
        bounded_read(tmp_path)
