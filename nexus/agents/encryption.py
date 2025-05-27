import logging
from base64 import b64decode, b64encode

from cryptography.fernet import Fernet
from django.conf import settings

logger = logging.getLogger(__name__)


def get_fernet_key():
    """Get or generate a Fernet key for encryption"""
    key = getattr(settings, 'CREDENTIAL_ENCRYPTION_KEY', None)
    if not key:
        # Generate a new key if not configured
        key = Fernet.generate_key()
        logger.warning("No CREDENTIAL_ENCRYPTION_KEY found in settings, generated new key")
    return key


def encrypt_value(value: str) -> str:
    def is_already_encrypted(value: str) -> bool:
        try:
            decoded = b64decode(value)
            f_check = Fernet(get_fernet_key())
            f_check.decrypt(decoded)
            return True
        except Exception:
            return False

    if not value:
        return value

    try:
        if not is_already_encrypted(value):
            f = Fernet(get_fernet_key())
            encrypted_bytes = f.encrypt(value.encode())
            result = b64encode(encrypted_bytes).decode()
            logger.debug(f"Value encrypted successfully. Length before: {len(value)}, after: {len(result)}")
            return result
        else:
            return value
    except Exception as e:
        logger.error(f"Error encrypting value: {str(e)}")
        return value


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt an encrypted string value using Fernet"""
    if not encrypted_value:
        return encrypted_value

    try:
        f = Fernet(get_fernet_key())
        decoded = b64decode(encrypted_value)
        decrypted_bytes = f.decrypt(decoded)
        result = decrypted_bytes.decode()
        logger.debug(f"Value decrypted successfully. Length before: {len(encrypted_value)}, after: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Error decrypting value: {str(e)}")
        return encrypted_value
