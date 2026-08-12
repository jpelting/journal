from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def _multi_fernet():
    return MultiFernet([Fernet(key) for key in settings.FIELD_ENCRYPTION_KEYS])


def encrypt_text(value):
    return _multi_fernet().encrypt(value.encode()).decode()


def decrypt_text(value):
    return _multi_fernet().decrypt(value.encode()).decode()
