"""Vault validation of identities, configuration, manifests, and update arguments.
"""

import json

import pytest

from seeqbox import Age, FileIdentity, IntegrityError, SeeqboxError, Vault
from seeqbox.files import json_bytes


def _rewrite_manifest(vault, recipient, change):
    document = json.loads(Age().decrypt(vault.root / 'manifest.age', vault.identity))
    change(document)
    encrypted = Age().encrypt(json_bytes(document), [recipient])
    (vault.root / 'manifest.age').write_bytes(encrypted)


def test_identity_inside_vault_rejected(vault, identities):
    inside = vault.root / 'identity.txt'
    inside.write_bytes(identities[0][0].read_bytes())
    with pytest.raises(SeeqboxError):
        Vault(vault.root, FileIdentity(inside))


def test_unsupported_format_version_rejected(vault):
    config = {'format': 'seeqbox', 'version': 2, 'vault_id': vault.vault_id}
    (vault.root / 'format.json').write_text(json.dumps(config))
    with pytest.raises(IntegrityError):
        Vault(vault.root, vault.identity)


def test_manifest_from_another_vault_rejected(vault, identities):
    def change(document):
        document['vault_id'] = 'f' * 32

    _rewrite_manifest(vault, identities[0][1], change)
    with pytest.raises(IntegrityError):
        Vault(vault.root, vault.identity)


def test_manifest_plaintext_hash_binds_the_object(vault, identities):
    vault.put('record', b'synthetic')

    def change(document):
        document['objects']['record']['sha256'] = '0' * 64

    _rewrite_manifest(vault, identities[0][1], change)
    with pytest.raises(IntegrityError):
        Vault(vault.root, vault.identity).get('record')


def test_non_ascii_recipient_list_rejected(vault):
    (vault.root / 'recipients.txt').write_text('agé\n', encoding='utf-8')
    with pytest.raises(IntegrityError):
        Vault(vault.root, vault.identity)


def test_update_arguments_are_validated(vault):
    vault.put('record', b'x')
    with pytest.raises(SeeqboxError):
        vault.update({'record': (b'y', None)}, delete=['record'])
    with pytest.raises(SeeqboxError):
        vault.put('text', 'not bytes')
    with pytest.raises(SeeqboxError):
        vault.put('record', b'x', metadata=['not', 'a', 'dict'])
    with pytest.raises(SeeqboxError):
        vault.put('record', b'x', metadata={'when': object()})
    with pytest.raises(SeeqboxError):
        vault.update({}, delete=['unknown'])

    # None of the rejected calls changed the committed manifest.
    assert Vault(vault.root, vault.identity).list().keys() == {'record'}
