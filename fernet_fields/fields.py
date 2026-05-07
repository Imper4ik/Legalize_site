"""Minimal encrypted model fields compatible with modern Django."""

from __future__ import annotations

from typing import Any, cast

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models
from django.utils.encoding import force_str
from django.utils.functional import cached_property


class EncryptedFieldDecryptionError(ValueError):
    """Raised when an encrypted database value cannot be decrypted."""


def _build_fernet() -> Fernet | MultiFernet:
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
    def _fernet(self) -> Fernet | MultiFernet:
        return _build_fernet()

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        token = self._fernet.encrypt(force_str(value).encode("utf-8"))
        return token.decode("utf-8")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is None or value == "":
            return value
        try:
            return self._decrypt(value, fail_closed=True)
        except EncryptedFieldDecryptionError:
            if getattr(settings, "FERNET_FIELDS_ALLOW_DECRYPTION_FAILURE", False):
                import logging
                logging.getLogger(__name__).warning(
                    "Decryption failed for a field, but FERNET_FIELDS_ALLOW_DECRYPTION_FAILURE is True. "
                    "Returning raw encrypted value."
                )
                return value
            raise

    def to_python(self, value: Any) -> Any:
        if value is None or value == "":
            return value
        if not self._looks_like_fernet_token(value):
            return value
        try:
            return self._decrypt(value, fail_closed=True)
        except EncryptedFieldDecryptionError:
            if getattr(settings, "FERNET_FIELDS_ALLOW_DECRYPTION_FAILURE", False):
                return value
            raise

    @staticmethod
    def _looks_like_fernet_token(value: Any) -> bool:
        return isinstance(value, str) and value.startswith("gAAAA")

    def _decrypt(self, value: Any, *, fail_closed: bool = False) -> Any:
        if not isinstance(value, str):
            return value
        try:
            decrypted = self._fernet.decrypt(value.encode("utf-8"))
        except InvalidToken:
            if fail_closed:
                raise EncryptedFieldDecryptionError(
                    "Encrypted field value could not be decrypted. This usually means "
                    "FERNET_KEYS has changed and no longer matches the key used for encryption."
                ) from None
            return value
        return force_str(decrypted)
