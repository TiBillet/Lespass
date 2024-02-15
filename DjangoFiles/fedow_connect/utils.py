import base64, json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from django.conf import settings

def data_to_b64(data: dict or list) -> bytes:
    data_to_json = json.dumps(data)
    json_to_bytes = data_to_json.encode('utf-8')
    bytes_to_b64 = base64.urlsafe_b64encode(json_to_bytes)
    return bytes_to_b64



def sign_message(message: bytes = None,
                 private_key: rsa.RSAPrivateKey = None) -> bytes:
    # Signer le message
    signature = private_key.sign(
        message,
        padding=padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        algorithm=hashes.SHA256()
    )
    return base64.urlsafe_b64encode(signature)


def verify_signature(public_key: rsa.RSAPublicKey,
                     message: bytes,
                     signature: str) -> bool:
    # Vérifier la signature
    try:
        public_key.verify(
            base64.urlsafe_b64decode(signature),
            message,
            padding=padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            algorithm=hashes.SHA256()
        )
        return True
    except InvalidSignature:
        return False