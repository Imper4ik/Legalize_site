"""Encrypt existing client identity PII and populate the search indexes.

After 0126 changed first_name/last_name/email/phone to encrypted columns, any
pre-existing rows still hold plaintext. This migration re-saves each client so
the values are written back encrypted, and fills the blind-index columns
(email_hash/phone_hash) plus the ClientSearchToken prefix index used for search.

It is idempotent: rows already encrypted decrypt cleanly and are simply
re-hashed/re-tokenised with the same result.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from django.conf import settings
from django.db import migrations

NAME_TOKEN_MIN_PREFIX = 3


def _plaintext(value: object) -> str:
    # Encrypted columns return an EncryptedValueUnavailable placeholder for
    # not-yet-encrypted (plaintext) rows; its raw_value carries the original.
    raw = getattr(value, "raw_value", None)
    if raw is not None:
        return str(raw)
    return "" if value is None else str(value)


def _blind_hash(namespace: str, normalized: str) -> str:
    secret = str(getattr(settings, "SECRET_KEY", ""))
    message = f"{namespace}:{normalized}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _hash_email(value: str) -> str:
    normalized = value.strip().casefold()
    return _blind_hash("email", normalized) if normalized else ""


def _hash_phone(value: str) -> str:
    normalized = re.sub(r"\D", "", value)
    return _blind_hash("phone", normalized) if normalized else ""


def _name_prefix_tokens(*names: str) -> set[str]:
    tokens: set[str] = set()
    for name in names:
        for word in re.split(r"\s+", (name or "").strip().casefold()):
            if not word:
                continue
            if len(word) < NAME_TOKEN_MIN_PREFIX:
                tokens.add(word)
                continue
            for end in range(NAME_TOKEN_MIN_PREFIX, len(word) + 1):
                tokens.add(word[:end])
    return tokens


def encrypt_and_index(apps, schema_editor):
    if not getattr(settings, "FERNET_KEYS", None):
        return
    Client = apps.get_model("clients", "Client")
    ClientSearchToken = apps.get_model("clients", "ClientSearchToken")

    for client in Client.objects.all().iterator():
        first_name = _plaintext(client.first_name)
        last_name = _plaintext(client.last_name)
        email = _plaintext(client.email)
        phone = _plaintext(client.phone)

        client.first_name = first_name
        client.last_name = last_name
        client.email = email
        client.phone = phone
        client.email_hash = _hash_email(email)
        client.phone_hash = _hash_phone(phone)
        client.save(
            update_fields=["first_name", "last_name", "email", "phone", "email_hash", "phone_hash"]
        )

        ClientSearchToken.objects.filter(client=client).delete()
        token_hashes = {_blind_hash("name", token) for token in _name_prefix_tokens(first_name, last_name)}
        if token_hashes:
            ClientSearchToken.objects.bulk_create(
                [ClientSearchToken(client=client, token_hash=token_hash) for token_hash in token_hashes],
                ignore_conflicts=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0126_clientsearchtoken_remove_client_client_email_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_and_index, migrations.RunPython.noop),
    ]
