"""Minimal encrypted model fields compatible with modern Django."""

from __future__ import annotations

import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models
from django.utils.encoding import force_str
from django.utils.functional import cached_property


logger = logging.getLogger(__name__)
ENCRYPTED_VALUE_UNAVAILABLE = "[encrypted value unavailable]"


class EncryptedFieldDecryptionError(ValueError):
    """Raised when an encrypted database value cannot be decrypted."""


class EncryptedValueUnavailable(str):
    """Safe placeholder for an unreadable encrypted database value."""

    def __new__(cls, raw_value: str) -> "EncryptedValueUnavailable":
        obj = str.__new__(cls, ENCRYPTED_VALUE_UNAVAILABLE)
        obj.raw_value = raw_value
        return obj


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

    def clean(self, value: Any, model_instance: models.Model) -> Any:
        if value == ENCRYPTED_VALUE_UNAVAILABLE:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                "This value is currently unavailable due to decryption failure. "
                "Saving it would permanently overwrite and lose the original data."
            )
        return super().clean(value, model_instance)

    def get_prep_value(self, value: Any) -> Any:
        if isinstance(value, EncryptedValueUnavailable):
            return value.raw_value
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
            logger.warning(
                "Encrypted field value could not be decrypted; returning unavailable marker"
            )
            return EncryptedValueUnavailable(force_str(value))

    def to_python(self, value: Any) -> Any:
        if value is None or value == "":
            return value
        if not self._looks_like_fernet_token(value):
            return value
        try:
            return self._decrypt(value, fail_closed=True)
        except EncryptedFieldDecryptionError:
            logger.warning(
                "Encrypted field to_python decryption failed for %s.%s",
                getattr(self, "model", None).__name__ if getattr(self, "model", None) else "?",
                getattr(self, "attname", "?"),
            )
            return EncryptedValueUnavailable(force_str(value))

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
