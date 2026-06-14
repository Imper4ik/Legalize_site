from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.test import SimpleTestCase, override_settings

from fernet_fields.fields import (
    ENCRYPTED_VALUE_UNAVAILABLE,
    EncryptedTextField,
    EncryptedValueUnavailable,
    _build_fernet,
)


class BuildFernetTests(SimpleTestCase):
    @override_settings(FERNET_KEYS=[])
    def test_build_fernet_raises_without_keys(self):
        with self.assertRaises(ValueError):
            _build_fernet()

    @override_settings(FERNET_KEYS=[Fernet.generate_key().decode()])
    def test_build_fernet_returns_single_fernet_for_one_key(self):
        fernet = _build_fernet()
        self.assertIsInstance(fernet, Fernet)

    @override_settings(FERNET_KEYS=[Fernet.generate_key().decode(), Fernet.generate_key().decode()])
    def test_build_fernet_returns_multifernet_for_multiple_keys(self):
        fernet = _build_fernet()
        self.assertIsInstance(fernet, MultiFernet)


class EncryptedTextFieldTests(SimpleTestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode()

    @override_settings(FERNET_KEYS=["dummy"])
    def test_get_prep_value_and_decrypt_roundtrip(self):
        key = Fernet.generate_key().decode()
        with override_settings(FERNET_KEYS=[key]):
            field = EncryptedTextField()
            encrypted = field.get_prep_value("secret")

            self.assertNotEqual(encrypted, "secret")
            self.assertEqual(field.to_python(encrypted), "secret")
            self.assertEqual(field.from_db_value(encrypted, None, None), "secret")

    @override_settings(FERNET_KEYS=["dummy"])
    def test_invalid_token_is_returned_as_is(self):
        key = Fernet.generate_key().decode()
        with override_settings(FERNET_KEYS=[key]):
            field = EncryptedTextField()
            value = "not-a-valid-token"
            self.assertEqual(field.to_python(value), value)

    @override_settings(FERNET_KEYS=["dummy"])
    def test_corrupted_fernet_token_returns_unavailable_marker(self):
        key = Fernet.generate_key().decode()
        raw_value = "gAAAA-corrupted-token"
        with override_settings(FERNET_KEYS=[key]):
            field = EncryptedTextField()
            value = field.from_db_value(raw_value, None, None)
            self.assertIsInstance(value, EncryptedValueUnavailable)
            self.assertEqual(str(value), ENCRYPTED_VALUE_UNAVAILABLE)
            self.assertEqual(field.get_prep_value(value), raw_value)

            py_val = field.to_python(raw_value)
            self.assertIsInstance(py_val, EncryptedValueUnavailable)
            self.assertEqual(str(py_val), ENCRYPTED_VALUE_UNAVAILABLE)

    @override_settings(FERNET_KEYS=["dummy"])
    def test_fernet_key_rotation_reads_old_key_and_writes_primary_key(self):
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        old_token = Fernet(old_key).encrypt(b"secret").decode()

        with override_settings(FERNET_KEYS=[new_key, old_key]):
            field = EncryptedTextField()
            self.assertEqual(field.from_db_value(old_token, None, None), "secret")

            rotated_token = field.get_prep_value("secret")
            self.assertEqual(Fernet(new_key).decrypt(rotated_token.encode()), b"secret")
            with self.assertRaises(InvalidToken):
                Fernet(old_key).decrypt(rotated_token.encode())

    @override_settings(FERNET_KEYS=["dummy"])
    def test_none_and_empty_values_stay_unchanged(self):
        key = Fernet.generate_key().decode()
        with override_settings(FERNET_KEYS=[key]):
            field = EncryptedTextField()
            self.assertIsNone(field.get_prep_value(None))
            self.assertEqual(field.get_prep_value(""), "")
