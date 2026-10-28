#!/usr/bin/env python3
"""aea-key.py FILE.aea: the archive key of an Apple firmware AEA file, base64, for `aea decrypt -key-value base64:...`.

The file's auth data names a public HPKE private key (com.apple.wkms.fcs-key-url) and carries the archive key
wrapped to it (com.apple.wkms.fcs-response: enc-request, wrapped-key). HPKE base mode, RFC 9180:
DHKEM(P-256, HKDF-SHA256), HKDF-SHA256, AES-256-GCM, empty info and aad.
"""
import base64
import json
import re
import sys
import urllib.request

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

head = open(sys.argv[1], 'rb').read(65536)
url = re.search(rb'https://wkms-public\.apple\.com/fcs-keys/[A-Za-z0-9_+/-]+=*', head).group().decode()
response = json.loads(re.search(rb'\{"enc-request"[^}]*\}', head).group())
pem = urllib.request.urlopen(url, timeout=30).read()
sk = serialization.load_pem_private_key(pem, None)
enc = base64.b64decode(response['enc-request'])
ct = base64.b64decode(response['wrapped-key'])


def extract(salt, ikm):
    h = hmac.HMAC(salt or b'\0' * 32, hashes.SHA256())
    h.update(ikm)
    return h.finalize()


def expand(prk, info, length):
    out, t, i = b'', b'', 1
    while len(out) < length:
        h = hmac.HMAC(prk, hashes.SHA256())
        h.update(t + info + bytes([i]))
        t = h.finalize()
        out += t
        i += 1
    return out[:length]


def labeled_extract(suite, salt, label, ikm):
    return extract(salt, b'HPKE-v1' + suite + label + ikm)


def labeled_expand(suite, prk, label, info, length):
    return expand(prk, length.to_bytes(2, 'big') + b'HPKE-v1' + suite + label + info, length)


kem_suite = b'KEM' + (0x10).to_bytes(2, 'big')
pk_e = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), enc)
dh = sk.exchange(ec.ECDH(), pk_e)
pk_rm = sk.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
eae_prk = labeled_extract(kem_suite, b'', b'eae_prk', dh)
shared = labeled_expand(kem_suite, eae_prk, b'shared_secret', enc + pk_rm, 32)
suite = b'HPKE' + (0x10).to_bytes(2, 'big') + (1).to_bytes(2, 'big') + (2).to_bytes(2, 'big')
context = b'\0' + labeled_extract(suite, b'', b'psk_id_hash', b'') + labeled_extract(suite, b'', b'info_hash', b'')
secret = labeled_extract(suite, shared, b'secret', b'')
key = labeled_expand(suite, secret, b'key', context, 32)
nonce = labeled_expand(suite, secret, b'base_nonce', context, 12)
print(base64.b64encode(AESGCM(key).decrypt(nonce, ct, b'')).decode())
