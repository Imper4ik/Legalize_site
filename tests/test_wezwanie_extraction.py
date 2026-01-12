from django.test import TestCase
from unittest.mock import patch
from clients.services.wezwanie_parser import parse_wezwanie
from clients.constants import DocumentType

class WezwanieExtractionTest(TestCase):
    @patch('clients.services.wezwanie_parser.extract_text')
    def test_extract_documents(self, mock_extract):
        """Test extraction of required documents from text."""
        sample_text = """
        Urząd Wojewódzki w Warszawie
        Wydział Spraw Cudzoziemców
        WEZWANIE
        
        Wzywam do złożenia:
        1. 4 zdjęcia biometryczne nieuszkodzone.
        2. Kserokopia paszportu (wszystkie strony).
        3. Dowód wpłaty 440 zł tytułem zezwolenia na pracę.
        4. Polisa ubezpieczeniowa zdrowotna.
        """
        mock_extract.return_value = sample_text
        
        # Path doesn't matter since we mock extract_text
        data = parse_wezwanie("dummy_path.pdf")
        
        extracted = data.required_documents
        print(f"Extracted docs: {extracted}")
        
        self.assertIn(DocumentType.PHOTOS.value, extracted)
        self.assertIn(DocumentType.PASSPORT.value, extracted)
        self.assertIn(DocumentType.PAYMENT_CONFIRMATION.value, extracted)
        self.assertIn(DocumentType.HEALTH_INSURANCE.value, extracted)
        
        # Ensure we didn't match random stuff
        self.assertNotIn(DocumentType.ZALACZNIK_NR_1.value, extracted)

    @patch('clients.services.wezwanie_parser.extract_text')
    def test_extract_documents_empty(self, mock_extract):
        """Test with text containing no relevant keywords."""
        mock_extract.return_value = "Proszę przyjść w poniedziałek."
        data = parse_wezwanie("dummy.pdf")
        self.assertEqual(data.required_documents, [])
