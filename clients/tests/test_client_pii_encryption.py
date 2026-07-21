"""Client identity PII is encrypted at rest but stays searchable via blind indexes.

Covers the searchable-encryption design: ciphertext at rest, transparent
decryption, exact blind-index match for email/phone, prefix/word search for
encrypted names, and intake de-duplication over the hashes.
"""
from __future__ import annotations

import pytest
from django.db import connection

from clients.models import Client, ClientSearchToken
from clients.services.intake import _conflicts_for_personal_data

pytestmark = pytest.mark.django_db


def _make(**kwargs):
    defaults = {"first_name": "Иван", "last_name": "Петров", "citizenship": "UA"}
    defaults.update(kwargs)
    return Client.objects.create(**defaults)


def test_pii_is_ciphertext_at_rest():
    client = _make(email="Ivan.Petrov@Example.COM", phone="+48 123 456 789")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT first_name, last_name, email, phone FROM clients_client WHERE id=%s",
            [client.id],
        )
        first_name, last_name, email, phone = cursor.fetchone()
    for raw in (first_name, last_name, email, phone):
        assert raw.startswith("gAAAA"), raw
    assert "Иван" not in first_name
    assert "example.com" not in email.lower()
    assert "123" not in phone


def test_decryption_is_transparent():
    client = _make(email="a@b.com", phone="123456789")
    client.refresh_from_db()
    assert client.first_name == "Иван"
    assert client.last_name == "Петров"
    assert client.email == "a@b.com"


def test_email_and_phone_blind_index_exact_match():
    client = _make(email="Ivan.Petrov@Example.COM", phone="+48 123 456 789")
    # Case/space-insensitive email; formatting-insensitive phone.
    assert Client.objects.filter(email_hash=Client.hash_email("ivan.petrov@example.com")).get() == client
    assert Client.objects.filter(phone_hash=Client.hash_phone("48123456789")).get() == client
    assert Client.objects.filter(phone_hash=Client.hash_phone("+48 123 456 789")).get() == client
    assert not Client.objects.filter(email_hash=Client.hash_email("other@example.com")).exists()


def _search(query):
    return set(Client.objects.filter(Client.build_search_filter(query)).values_list("id", flat=True))


def test_name_prefix_and_word_search():
    ivan = _make(first_name="Иван", last_name="Петров", email="ivan@example.com")
    maria = _make(first_name="Мария", last_name="Иванова", email="maria@example.com")

    assert _search("Ива") == {ivan.id, maria.id}  # prefix matches Иван and Иванова
    assert _search("иван") == {ivan.id, maria.id}
    assert _search("петр") == {ivan.id}
    assert _search("Иван Петров") == {ivan.id}  # AND across words
    assert _search("мария") == {maria.id}
    assert _search("ив") == set()  # < 3 chars is not a prefix token
    assert _search("сидоров") == set()


def test_search_by_email_and_phone_and_case_insensitive():
    client = _make(email="Contact@Example.com", phone="+48 500 600 700")
    assert _search("contact@example.com") == {client.id}
    assert _search("48500600700") == {client.id}


def test_tokens_rebuilt_on_rename():
    client = _make(first_name="Иван", last_name="Петров")
    assert _search("ива") == {client.id}
    client.first_name = "Сергей"
    client.save(update_fields=["first_name"])
    assert _search("сер") == {client.id}
    # Old first-name prefix no longer matches; last name still does.
    assert _search("ива") == set()
    assert _search("петр") == {client.id}


def test_tokens_created_for_client():
    client = _make(first_name="Иван", last_name="Петров")
    # Prefix tokens for both name words are stored (ива/иван + петр/петро/...).
    assert ClientSearchToken.objects.filter(client=client).count() >= 4


def test_intake_dedup_uses_hashes():
    client = _make(email="Dup@Example.com", phone="+48 111 222 333")
    conflicts = _conflicts_for_personal_data({"email": "dup@example.com", "phone": "48111222333"})
    assert client in list(conflicts)
    none = _conflicts_for_personal_data({"email": "fresh@example.com", "phone": "999"})
    assert client not in list(none)
