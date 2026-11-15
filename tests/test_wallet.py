"""Tests for wallet/: key generation, addresses, signatures, encrypted storage."""

import pytest

import config
from wallet import (
    Wallet,
    WalletError,
    address_from_public_key,
    is_valid_address,
    verify_signature,
)

PASSWORD = "correct-horse-battery"
MESSAGE = b"pay bob 10 coins"


def test_each_wallet_gets_a_unique_key_and_address():
    wallets = [Wallet.create() for _ in range(5)]
    assert len({w.address for w in wallets}) == 5
    assert len({w.public_key_hex for w in wallets}) == 5


def test_address_format(alice):
    assert alice.address.startswith(config.ADDRESS_PREFIX)
    assert len(alice.address) == len(config.ADDRESS_PREFIX) + config.ADDRESS_HASH_LENGTH
    assert is_valid_address(alice.address)


def test_address_is_derived_from_public_key(alice):
    assert address_from_public_key(alice.public_key_hex) == alice.address


@pytest.mark.parametrize("bad", ["", "SC123", "XX" + "a" * 40, "SC" + "g" * 40, "SC" + "A" * 40, None, 42])
def test_invalid_addresses_are_recognised(bad):
    assert not is_valid_address(bad)


def test_signature_verifies_with_matching_public_key(alice):
    signature = alice.sign(MESSAGE)
    assert verify_signature(alice.public_key_hex, MESSAGE, signature)


def test_signature_fails_if_message_changes(alice):
    signature = alice.sign(MESSAGE)
    assert not verify_signature(alice.public_key_hex, b"pay bob 1000 coins", signature)


def test_signature_fails_with_another_wallets_key(alice, mallory):
    signature = mallory.sign(MESSAGE)
    assert not verify_signature(alice.public_key_hex, MESSAGE, signature)


@pytest.mark.parametrize(
    "public_key, signature",
    [("", ""), ("zz", "zz"), ("00" * 33, "00" * 70), ("not-hex", "abcd"), (None, None)],
)
def test_verify_never_raises_on_garbage(public_key, signature):
    assert verify_signature(public_key, MESSAGE, signature) is False


def test_sign_requires_bytes(alice):
    with pytest.raises(WalletError):
        alice.sign("a string, not bytes")


def test_encrypted_export_roundtrip(alice):
    pem = alice.to_encrypted_pem(PASSWORD)
    restored = Wallet.from_encrypted_pem(pem, PASSWORD)
    assert restored.address == alice.address
    assert verify_signature(alice.public_key_hex, MESSAGE, restored.sign(MESSAGE))


def test_exported_key_is_encrypted_not_plaintext(alice):
    pem = alice.to_encrypted_pem(PASSWORD)
    assert "BEGIN ENCRYPTED PRIVATE KEY" in pem
    assert "BEGIN PRIVATE KEY" not in pem
    assert "BEGIN EC PRIVATE KEY" not in pem


def test_wrong_password_cannot_unlock(alice):
    pem = alice.to_encrypted_pem(PASSWORD)
    with pytest.raises(WalletError):
        Wallet.from_encrypted_pem(pem, "wrong-password")
    with pytest.raises(WalletError):
        Wallet.from_encrypted_pem(pem, "")


def test_corrupted_keystore_is_rejected():
    with pytest.raises(WalletError):
        Wallet.from_encrypted_pem("this is not a key", PASSWORD)


@pytest.mark.parametrize("weak", ["", "short", "1234567", None])
def test_weak_passwords_are_rejected(alice, weak):
    with pytest.raises(WalletError):
        alice.to_encrypted_pem(weak)


def test_repr_does_not_leak_the_private_key(alice):
    private_hex = format(alice._private_key.private_numbers().private_value, "x")
    assert private_hex not in repr(alice)
    assert alice.address in repr(alice)
