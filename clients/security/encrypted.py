"""Safe helpers for displaying Fernet-encrypted model values."""

from __future__ import annotations

import logging
from typing import Any

from fernet_fields import EncryptedFieldDecryptionError, EncryptedValueUnavailable

ENCRYPTED_VALUE_UNAVAILABLE = "[encrypted value unavailable]"

logger = logging.getLogger(__name__)


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
        meta = getattr(instance, "_meta", None)
        model_label = getattr(meta, "label", instance.__class__.__name__)
        logger.warning(
            "Encrypted field value unavailable: model=%s pk=%s field=%s",
            model_label,
            getattr(instance, "pk", None),
            field_name,
        )
        return ENCRYPTED_VALUE_UNAVAILABLE
    return default if value in (None, "") else value
