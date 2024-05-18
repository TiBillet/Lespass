import base64, json
import hashlib
from decimal import Decimal

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from django.conf import settings
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def dround(value):
    # Si c'est un entier, on divise par 100
    if type(value) == int:
        return Decimal(value / 100).quantize(Decimal('1.00'))
    return value.quantize(Decimal('1.00'))



def data_to_b64(data: dict or list) -> bytes:
    data_to_json = json.dumps(data)
    json_to_bytes = data_to_json.encode('utf-8')
    bytes_to_b64 = base64.urlsafe_b64encode(json_to_bytes)
    return bytes_to_b64

def b64_to_data(b64: bytes) -> dict or list:
    b64_to_bytes = base64.urlsafe_b64decode(b64)
    bytes_to_json = b64_to_bytes.decode('utf-8')
    json_to_data = json.loads(bytes_to_json)
    return json_to_data


def rsa_generator():
    # Génération d'une paire de clés RSA chiffré avec la SECRET_KEY de Django
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    # Extraction de la clé publique associée à partir de la clé privée
    public_key = private_key.public_key()

    # Sérialisation des clés au format PEM
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(settings.SECRET_KEY.encode('utf-8'))
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem.decode('utf-8'), public_pem.decode('utf-8')

def get_private_key(private_pem):
    private_key = serialization.load_pem_private_key(
        private_pem.encode('utf-8'),
        password=settings.SECRET_KEY.encode('utf-8'),
    )
    return private_key


def get_public_key(public_key_pem: str) -> RSAPublicKey:
    try:
        # Charger la clé publique au format PEM
        public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'), backend=default_backend())

        # Vérifier que la clé publique est au format RSA
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("La clé publique n'est pas au format RSA")
        return public_key

    except Exception as e:
        raise e


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


def sign_utf8_string(utf8_string: str=None, utf8_private_pem: str=None) -> str:
    # Pour signer une utf_8_string avec une private pem
    private_key = serialization.load_pem_private_key(
            utf8_private_pem.encode('utf-8'),
            password=settings.SECRET_KEY.encode('utf-8'),
        )
    message = utf8_string.encode('utf-8')
    return sign_message(message, private_key).decode('utf-8')


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


def fernet_encrypt(message: str) -> str:
    message = message.encode('utf-8')
    encryptor = Fernet(settings.FERNET_KEY)
    return encryptor.encrypt(message).decode('utf-8')


def fernet_decrypt(message: str) -> str:
    message = message.encode('utf-8')
    decryptor = Fernet(settings.FERNET_KEY)
    return decryptor.decrypt(message).decode('utf-8')

def hash_hexdigest(utf8_string):
    return hashlib.sha256(utf8_string.encode('utf-8')).hexdigest()

def rsa_encrypt_string(utf8_string=None, public_key: rsa.RSAPublicKey=None) -> str:
    message = utf8_string.encode('utf-8')
    ciphertext = public_key.encrypt(
        message,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return base64.urlsafe_b64encode(ciphertext).decode('utf-8')

def rsa_decrypt_string(utf8_enc_string: str, private_key: rsa.RSAPrivateKey) -> str:
    ciphertext = base64.urlsafe_b64decode(utf8_enc_string)
    plaintext = private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return plaintext.decode('utf-8')