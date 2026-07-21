"""Minimal encrypted model fields compatible with modern Django."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.encoding import force_str
from django.utils.functional import cached_property

logger = logging.getLogger(__name__)
ENCRYPTED_VALUE_UNAVAILABLE = "[encrypted value unavailable]"


class EncryptedFieldDecryptionError(ValueError):
    """Raised when an encrypted database value cannot be decrypted."""


class EncryptedValueUnavailable(str):
    """Safe placeholder for an unreadable encrypted database value."""

    raw_value: str

    def __new__(cls, raw_value: str) -> "EncryptedValueUnavailable":
        obj = str.__new__(cls, ENCRYPTED_VALUE_UNAVAILABLE)
        obj.raw_value = raw_value
        return obj


def _reject_unavailable_placeholder(value: Any) -> None:
    if value == ENCRYPTED_VALUE_UNAVAILABLE:
        raise ValidationError(
            "This value is currently unavailable due to decryption failure. "
            "Saving it would permanently overwrite and lose the original data."
        )


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

    def clean(self, value: Any, model_instance: models.Model | None) -> Any:
        _reject_unavailable_placeholder(value)
        return super().clean(value, model_instance)

    def get_prep_value(self, value: Any) -> Any:
        if isinstance(value, EncryptedValueUnavailable):
            return value.raw_value
        _reject_unavailable_placeholder(value)
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
            model = getattr(self, "model", None)
            logger.warning(
                "Encrypted field to_python decryption failed for %s.%s",
                getattr(model, "__name__", "?"),
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


class EncryptedJSONField(models.TextField):
    """JSON value encrypted at rest using the same Fernet key ring as text fields.

    The field stores encrypted JSON text in the database and returns normal Python
    JSON values to application code. Plain legacy JSON strings are still readable
    so existing rows can be migrated safely by re-saving them.
    """

    description = "Fernet-encrypted JSON"

    if TYPE_CHECKING:
        # django-stubs derives the attribute type from TextField (``str``), but
        # this field stores and returns arbitrary JSON (dict/list/etc.). Present
        # it as ``Any`` to type checkers so assigning JSON values is accepted.
        # Invisible at runtime; no behavioural change.
        def __get__(self, instance: Any, owner: Any) -> Any: ...
        def __set__(self, instance: Any, value: Any) -> None: ...

    @cached_property
    def _fernet(self) -> Fernet | MultiFernet:
        return _build_fernet()

    def clean(self, value: Any, model_instance: models.Model | None) -> Any:
        _reject_unavailable_placeholder(value)
        return super().clean(value, model_instance)

    def get_prep_value(self, value: Any) -> Any:
        if isinstance(value, EncryptedValueUnavailable):
            return value.raw_value
        _reject_unavailable_placeholder(value)
        if value is None or value == "":
            return value
        json_value = json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(",", ":"))
        token = self._fernet.encrypt(json_value.encode("utf-8"))
        return token.decode("utf-8")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        return self._load_value(value)

    def to_python(self, value: Any) -> Any:
        return self._load_value(value)

    def value_to_string(self, obj: models.Model) -> str:
        value = self.value_from_object(obj)
        if value is None:
            return ""
        return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)

    def _load_value(self, value: Any) -> Any:
        if value is None or value == "":
            return value
        if isinstance(value, EncryptedValueUnavailable):
            return value
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if not isinstance(value, str):
            return value

        raw_value = value
        if self._looks_like_fernet_token(value):
            try:
                raw_value = force_str(self._fernet.decrypt(value.encode("utf-8")))
            except InvalidToken:
                logger.warning(
                    "Encrypted JSON field value could not be decrypted; returning unavailable marker"
                )
                return EncryptedValueUnavailable(force_str(value))

        try:
            return json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            return raw_value

    @staticmethod
    def _looks_like_fernet_token(value: Any) -> bool:
        return isinstance(value, str) and value.startswith("gAAAA")
