"""Wallet package: ECDSA key pairs, addresses and digital signatures."""

from wallet.wallet import (
    Wallet,
    WalletError,
    address_from_public_key,
    is_valid_address,
    validate_password,
    verify_signature,
)

__all__ = [
    "Wallet",
    "WalletError",
    "address_from_public_key",
    "is_valid_address",
    "validate_password",
    "verify_signature",
]
