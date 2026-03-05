"""
Custom Django model fields for the IOMS project.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


class EncryptedCharField(models.TextField):
    """
    Fernet-symmetric-encrypted text field.

    Values are encrypted before write and decrypted on read.
    If FERNET_KEY is empty or invalid (e.g. in dev/test without a key),
    the field stores plaintext transparently so tests don't require key setup.
    """

    def _get_fernet(self):
        key = getattr(settings, "FERNET_KEY", "")
        if not key:
            return None
        try:
            if isinstance(key, str):
                key = key.encode()
            return Fernet(key)
        except Exception:
            return None

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        fernet = self._get_fernet()
        if fernet is None:
            return value
        try:
            return fernet.decrypt(value.encode()).decode()
        except (InvalidToken, Exception):
            # Return raw value if decryption fails (handles already-plaintext in dev)
            return value

    def get_prep_value(self, value):
        if not value:
            return value
        fernet = self._get_fernet()
        if fernet is None:
            return value
        return fernet.encrypt(value.encode()).decode()
