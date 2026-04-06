from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet
from django.test import SimpleTestCase, override_settings

from fernet_fields.fields import EncryptedTextField, _build_fernet


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
    def test_none_and_empty_values_stay_unchanged(self):
        key = Fernet.generate_key().decode()
        with override_settings(FERNET_KEYS=[key]):
            field = EncryptedTextField()
            self.assertIsNone(field.get_prep_value(None))
            self.assertEqual(field.get_prep_value(""), "")
