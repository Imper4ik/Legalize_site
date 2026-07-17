"""Safe helpers for displaying Fernet-encrypted model values."""

from __future__ import annotations

import logging
from typing import Any

from fernet_fields import EncryptedFieldDecryptionError, EncryptedValueUnavailable

ENCRYPTED_VALUE_UNAVAILABLE = "[encrypted value unavailable]"

logger = logging.getLogger(__name__)


class EncryptedJSONUnavailableError(RuntimeError):
    """Raised when a write path cannot safely read an encrypted JSON value."""

    def __init__(self, instance: Any, field_name: str) -> None:
        self.model_label, self.object_pk = _encrypted_field_metadata(instance)
        self.field_name = field_name
        super().__init__(
            f"Encrypted JSON field is unavailable: "
            f"model={self.model_label} pk={self.object_pk} field={field_name}"
        )


def _encrypted_field_metadata(instance: Any) -> tuple[str, Any]:
    meta = getattr(instance, "_meta", None)
    return (
        getattr(meta, "label", instance.__class__.__name__),
        getattr(instance, "pk", None),
    )


def _log_encrypted_json_unavailable(instance: Any, field_name: str, *, reason: str) -> None:
    model_label, object_pk = _encrypted_field_metadata(instance)
    logger.warning(
        "Encrypted JSON field unavailable: model=%s pk=%s field=%s reason=%s",
        model_label,
        object_pk,
        field_name,
        reason,
    )


def _read_encrypted_json_value(instance: Any, field_name: str) -> tuple[Any, bool]:
    try:
        value = getattr(instance, field_name)
    except EncryptedFieldDecryptionError:
        _log_encrypted_json_unavailable(instance, field_name, reason="decryption_error")
        return None, True

    if isinstance(value, EncryptedValueUnavailable) or value == ENCRYPTED_VALUE_UNAVAILABLE:
        _log_encrypted_json_unavailable(instance, field_name, reason="decryption_unavailable")
        return None, True
    return value, False


def read_encrypted_json_dict(instance: Any, field_name: str) -> tuple[dict[str, Any], bool]:
    """Return a detached dict and whether the encrypted source was unavailable.

    Display paths can render the empty copy while exposing a generic unavailable
    state. Write paths must use :func:`require_encrypted_json_dict` instead.
    """

    value, unavailable = _read_encrypted_json_value(instance, field_name)
    if unavailable:
        return {}, True
    if value in (None, ""):
        return {}, False
    if isinstance(value, dict):
        return value.copy(), False
    _log_encrypted_json_unavailable(instance, field_name, reason="unexpected_type")
    return {}, True


def read_encrypted_json_list(instance: Any, field_name: str) -> tuple[list[Any], bool]:
    """Return a detached list and whether the encrypted source was unavailable."""

    value, unavailable = _read_encrypted_json_value(instance, field_name)
    if unavailable:
        return [], True
    if value in (None, ""):
        return [], False
    if isinstance(value, list):
        return value.copy(), False
    _log_encrypted_json_unavailable(instance, field_name, reason="unexpected_type")
    return [], True


def require_encrypted_json_dict(instance: Any, field_name: str) -> dict[str, Any]:
    """Return a detached dict or refuse a write that could destroy ciphertext."""

    value, unavailable = read_encrypted_json_dict(instance, field_name)
    if unavailable:
        raise EncryptedJSONUnavailableError(instance, field_name)
    return value


def require_encrypted_json_list(instance: Any, field_name: str) -> list[Any]:
    """Return a detached list or refuse a write that could destroy ciphertext."""

    value, unavailable = read_encrypted_json_list(instance, field_name)
    if unavailable:
        raise EncryptedJSONUnavailableError(instance, field_name)
    return value


def safe_encrypted_attr(instance: Any, field_name: str, *, default: str = "") -> Any:
    """Return an encrypted model attribute without letting bad ciphertext break UI/export paths.

    Only logs model, primary key, and field metadata. Never include the encrypted raw
    value or decrypted value in logs.
    """

    try:
        value = getattr(instance, field_name)
    except EncryptedFieldDecryptionError:
        value = ENCRYPTED_VALUE_UNAVAILABLE

    if isinstance(value, EncryptedValueUnavailable) or value == ENCRYPTED_VALUE_UNAVAILABLE:
        model_label, object_pk = _encrypted_field_metadata(instance)
        logger.warning(
            "Encrypted field value unavailable: model=%s pk=%s field=%s",
            model_label,
            object_pk,
            field_name,
        )
        return ENCRYPTED_VALUE_UNAVAILABLE
    return default if value in (None, "") else value
