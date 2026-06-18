from cryptography.fernet import Fernet

from app.core.config import settings

# converting the key back to byte object
_fernet = Fernet(settings.pii_encryption_key.encode())


def encrypt_pii(value: str) -> str:

    return _fernet.encrypt(value.encode()).decode()


def decrypt_pii(token: str) -> str:

    return _fernet.decrypt(token.encode()).decode()
