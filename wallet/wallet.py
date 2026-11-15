"""
Wallets: ECDSA key pairs, addresses, signing and verification.

A wallet is simply an ECDSA private key on the secp256k1 curve (the same
curve Bitcoin uses). Everything else is derived from it:

    private key  --(elliptic curve maths)-->  public key
    public key   --(SHA-256, first 40 hex)-->  address   e.g. "SC3f9a..."

Private key handling rules followed in this module:
  * the private key object is held in a "private" attribute and is never
    printed, logged or returned as plain text;
  * the only way to export it is `to_encrypted_pem`, which encrypts it with
    a password (PBKDF2 key derivation + AES-256, provided by `cryptography`);
  * verification only ever needs the PUBLIC key.
"""

import hashlib
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import config

# The elliptic curve used for every key in the system.
CURVE = ec.SECP256K1()

_ADDRESS_PATTERN = re.compile(
    rf"^{config.ADDRESS_PREFIX}[0-9a-f]{{{config.ADDRESS_HASH_LENGTH}}}$"
)


class WalletError(Exception):
    """Raised for wallet problems (wrong password, weak password, bad key)."""


# --------------------------------------------------------------------------
# Helper functions that only need PUBLIC information
# --------------------------------------------------------------------------
def address_from_public_key(public_key_hex: str) -> str:
    """Derive the wallet address from a hex-encoded public key."""
    try:
        key_bytes = bytes.fromhex(public_key_hex)
    except (ValueError, TypeError) as exc:
        raise WalletError("Public key is not valid hexadecimal.") from exc
    digest = hashlib.sha256(key_bytes).hexdigest()
    return config.ADDRESS_PREFIX + digest[: config.ADDRESS_HASH_LENGTH]


def is_valid_address(address) -> bool:
    """Return True if `address` has the SecureChain address format."""
    return isinstance(address, str) and bool(_ADDRESS_PATTERN.match(address))


def verify_signature(public_key_hex: str, message: bytes, signature_hex: str) -> bool:
    """
    Check an ECDSA signature.

    Returns True only if `signature_hex` was produced over `message` by the
    private key that belongs to `public_key_hex`. Any malformed input simply
    results in False - verification never raises.
    """
    try:
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            CURVE, bytes.fromhex(public_key_hex)
        )
        public_key.verify(bytes.fromhex(signature_hex), message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def validate_password(password) -> None:
    """Raise WalletError if the password is too weak to protect a key."""
    if not isinstance(password, str) or len(password) < config.MIN_PASSWORD_LENGTH:
        raise WalletError(
            f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters long."
        )


# --------------------------------------------------------------------------
# The wallet itself
# --------------------------------------------------------------------------
class Wallet:
    """An ECDSA key pair that can sign messages."""

    def __init__(self, private_key: ec.EllipticCurvePrivateKey):
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise WalletError("A wallet needs an elliptic-curve private key.")
        if private_key.curve.name != CURVE.name:
            raise WalletError("Wallet keys must use the secp256k1 curve.")
        self._private_key = private_key

    # ----- creation -------------------------------------------------------
    @classmethod
    def create(cls) -> "Wallet":
        """Generate a brand-new wallet with a random private key."""
        return cls(ec.generate_private_key(CURVE))

    # ----- public information --------------------------------------------
    @property
    def public_key_hex(self) -> str:
        """The public key in compressed form (33 bytes -> 66 hex characters)."""
        public_bytes = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.CompressedPoint,
        )
        return public_bytes.hex()

    @property
    def address(self) -> str:
        """The wallet address, derived from the public key."""
        return address_from_public_key(self.public_key_hex)

    # ----- signing --------------------------------------------------------
    def sign(self, message: bytes) -> str:
        """Sign `message` with ECDSA/SHA-256 and return the signature as hex."""
        if not isinstance(message, (bytes, bytearray)):
            raise WalletError("Only bytes can be signed.")
        signature = self._private_key.sign(bytes(message), ec.ECDSA(hashes.SHA256()))
        return signature.hex()

    # ----- secure storage -------------------------------------------------
    def to_encrypted_pem(self, password: str) -> str:
        """
        Export the private key ENCRYPTED with `password`.

        This text is what gets stored in the database. Without the password
        it is useless to an attacker who steals the database file.
        """
        validate_password(password)
        pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
        )
        return pem.decode("ascii")

    @classmethod
    def from_encrypted_pem(cls, pem: str, password: str) -> "Wallet":
        """Unlock a wallet from its encrypted form. Wrong password -> WalletError."""
        if not isinstance(password, str) or not password:
            raise WalletError("A password is required to unlock the wallet.")
        try:
            private_key = serialization.load_pem_private_key(
                pem.encode("ascii"), password=password.encode("utf-8")
            )
        except (ValueError, TypeError, UnicodeError) as exc:
            # Deliberately vague: do not reveal whether the data or password was wrong.
            raise WalletError("Incorrect password or corrupted keystore.") from exc
        return cls(private_key)

    def __repr__(self) -> str:
        # Never include key material in the text representation.
        return f"Wallet(address={self.address})"
