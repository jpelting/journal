from django.db import models

from .crypto import decrypt_text, encrypt_text


class EncryptedTextField(models.TextField):
    """A TextField whose non-blank values are encrypted at rest.

    Blank values are stored as a literal empty string, not ciphertext, so
    `.exclude(field="")`-style blank checks keep working at the DB level
    without decrypting every row.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return encrypt_text(value)

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return decrypt_text(value)
