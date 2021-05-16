# Pynacl has limited confusing and annoying high level bindings, this wrapper simulates libnacl, because i can't make libnacl work on android

from nacl.bindings import crypto_generichash_blake2b_salt_personal as _b2b_hash

from nacl.bindings.crypto_sign import crypto_sign, crypto_sign_keypair, crypto_sign_open, crypto_sign_seed_keypair
from nacl.bindings.crypto_secretbox import crypto_secretbox, crypto_secretbox_open
from nacl.bindings import crypto_sign_BYTES
from nacl.bindings.crypto_generichash import crypto_generichash_BYTES


def crypto_sign_detached(msg, key):
    raw_signed = crypto_sign(msg, key)
    signature = raw_signed[:crypto_sign_BYTES]
    message = raw_signed[crypto_sign_BYTES:]

    return signature


def crypto_sign_verify_detached(sig, msg, key):
    return crypto_sign_open(sig+msg, key)


def crypto_generichash(
    data,

    key=b"",
    salt=b""
):
    if not isinstance(data, bytes):
        data=data.encode()
    person = b""
    digest_size = crypto_generichash_BYTES
    digest = _b2b_hash(
        data, digest_size=digest_size, key=key, salt=salt, person=person
    )
    return digest
