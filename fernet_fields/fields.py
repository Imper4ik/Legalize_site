"""Minimal encrypted model fields compatible with modern Django."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models
from django.utils.encoding import force_str
from django.utils.functional import cached_property


def _build_fernet():
    keys = getattr(settings, "FERNET_KEYS", [])
    if not keys:
        raise ValueError("FERNET_KEYS must contain at least one key")
    fernets = [Fernet(key) for key in keys]
    if len(fernets) == 1:
        return fernets[0]
    return MultiFernet(fernets)


class EncryptedTextField(models.TextField):
    """TextField encrypted at rest using Fernet keys."""

    @cached_property
    def _fernet(self):
        return _build_fernet()

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        token = self._fernet.encrypt(force_str(value).encode("utf-8"))
        return token.decode("utf-8")

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return self._decrypt(value)

    def to_python(self, value):
        if value is None or value == "":
            return value
        return self._decrypt(value)

    def _decrypt(self, value):
        if not isinstance(value, str):
            return value
        try:
            decrypted = self._fernet.decrypt(value.encode("utf-8"))
        except InvalidToken:
            return value
        return force_str(decrypted)
