import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from clients.services.wezwanie_parser import extract_text

@patch('pytesseract.image_to_string')
@patch('PIL.Image.open')
def test_image_ocr_uses_polish_language(mock_open, mock_image_to_string):
    """
    Verify that when extracting text from an image (not PDF),
    pytesseract is called with lang='pol+eng'.
    """
    # Setup mocks
    mock_image_obj = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_image_obj
    mock_image_to_string.return_value = "Mocked OCR text"

    # Define a dummy image path
    image_path = Path("test_document.jpg")

    # Call the function under test
    result = extract_text(image_path)

    # Assertions
    assert result == "Mocked OCR text"
    
    # This is the critical check: did we pass the correct language?
    # Inspect the call arguments to image_to_string
    mock_image_to_string.assert_called_once()
    
    # We expect the first arg to be the image object
    # We expect 'lang' kwarg to be 'pol+eng'
    args, kwargs = mock_image_to_string.call_args
    assert args[0] == mock_image_obj
    
    # This assertion is expected to FAIL before the fix
    print(f"DEBUG: kwargs={kwargs}")
    assert kwargs.get('lang') == 'pol+eng', f"Expected lang='pol+eng', but got {kwargs.get('lang')}"
