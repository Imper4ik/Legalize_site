"""Utility helpers for extracting data from Wezwanie summons scans."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from clients.constants import DocumentType

logger = logging.getLogger(__name__)


DATE_FORMATS = ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")
CASE_NUMBER_PATTERNS = (
    re.compile(r"numer\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"nr\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"sprawa\s+nr[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"(?:sygnatura|sygn\.)\s*akt[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"sygnatura[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"nr\s+akt[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"znak\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    
    # 1. Wide net for WSC (single line only)
    # Matches "WSC", "W S C" etc. followed by chars, spaces, dots, slashes But NOT newlines
    re.compile(r"((?:W[ \t]*S[ \t]*C|S[ \t]*O[ \t]*C|W[ \t]*5[ \t]*C|V[ \t]*V[ \t]*S[ \t]*C|W[ \t]*\$[ \t]*C|W[ \t]*\.[ \t]*S[ \t]*\.[ \t]*C)[-\w. /]{5,})", re.IGNORECASE),
    
    # 2. Structure match (single line only)
    # "2-5 Chars - Roman/Digits ... "
    re.compile(r"([A-Z0-9 ]{2,5}[- ]+[XIV1l\d]{1,5}[- ]+[A-Z0-9][. ]+\d{4}[. ]+\d+)", re.IGNORECASE),
    
    # 3. Generic fallback
    re.compile(r"\b([A-Z]{2,4}[- ][XIV]+\.[-\w./]+)\b", re.IGNORECASE),
    
    # 4. Old Strict fallback
    re.compile(r"\b([A-Z]{1,3}[ \t]?/[ \t]?\d{1,5}[ \t]?/[ \t]?\d{2,4})\b"),
)
DATE_PATTERNS = (
    re.compile(r"(?:dniu|dnia|dn\.)?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", re.IGNORECASE),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class WezwanieData:
    """Parsed data extracted from the uploaded summons."""

    text: str
    error: str | None = None
    case_number: str | None = None
    fingerprints_date: date | None = None
    fingerprints_time: str | None = None
    fingerprints_location: str | None = None
    decision_date: date | None = None
    full_name: str | None = None
    wezwanie_type: str | None = None  # "fingerprints" or "decision" or "confirmation"
    required_documents: list[str] = None

    def __post_init__(self):
        if self.required_documents is None:
            self.required_documents = []


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None

    cleaned = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _extract_pdf_text(path: Path) -> str:
    """Extract text from PDF, using native text extraction or OCR for scans."""
    text_content = ""
    
    # 1. Try native text extraction first (fastest, best for digital PDFs)
    # Note: Using pypdf would be better here, but avoiding extra dependency for now
    # if simple read worked. Since we know simple read fails for scans, we skip straight
    # to OCR if we can't get text easily or if we want to be thorough.
    # However, standard PDF libraries (pypdf) are better than raw read.
    # Given we added pdf2image, we likely want to focus on OCR for scans.
    
    try:
        from pdf2image import convert_from_path
        import pytesseract
        
        # Convert PDF to images (first 2 pages usually enough for Wezwanie)
        try:
            images = convert_from_path(str(path), first_page=1, last_page=2)
        except Exception as e:
            logger.warning(f"pdf2image failed: {e}")
            images = []
            
        ocr_text = []
        for i, image in enumerate(images):
            try:
                # Polish language is crucial here
                page_text = pytesseract.image_to_string(image, lang='pol+eng')
                ocr_text.append(page_text)
            except Exception as e:
                logger.warning(f"OCR failed on page {i}: {e}")
                
        text_content = "\n".join(ocr_text)
        print(f"DEBUG: EXTRACTED PDF TEXT (flush):\n{text_content}\n-----------------------", flush=True)


        
    except ImportError:
        logger.warning("pdf2image or pytesseract not available")
    except Exception as e:
        logger.exception(f"PDF OCR extraction failed: {e}")

    # 2. Fallback: naive binary extraction (only works for some streams, mostly debug)
    if not text_content or len(text_content.strip()) < 50:
        try:
            raw_text = path.read_bytes().decode("utf-8", errors="ignore")
            # Only use if it looks like real text, not binary garbage
            if "wezwanie" in raw_text.lower() or "duw" in raw_text.lower():
                return raw_text
        except Exception:
            pass

    return text_content


def _preprocess_for_ocr(img):
    """
    Preprocess image for better OCR accuracy:
    1. EXIF Transpose (fix phone orientation)
    2. OSD (Detect & fix 90/180/270 degree rotation)
    3. Grayscale + Autocontrast
    4. Rescale + Sharpen
    """
    from PIL import Image, ImageOps, ImageFilter
    import pytesseract
    
    # 0. Fix EXIF orientation (crucial for phone photos)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # 1. Grayscale (needed for OSD and OCR)
    img = img.convert('L')
    
    # 2. OSD Rotation (Detect text orientation)
    # Tesseract's "image_to_osd" returns meta info including 'Rotate: 90'
    try:
        # Pytesseract expects an image object
        osd = pytesseract.image_to_osd(img)
        # Parse logic is a bit brittle, using regex is safer or just simple string search
        # OSD output looks like: "Page number: 0\nOrientation in degrees: 90\nRotate: 90\n..."
        import re
        rotate_match = re.search(r"Rotate: (\d+)", osd)
        if rotate_match:
            angle = int(rotate_match.group(1))
            if angle != 0:
                print(f"DEBUG: OSD detected rotation: {angle}. Fixing...", flush=True)
                # Tesseract says "Rotate: 90" meaning it IS rotated. We need to rotate it BACK? 
                # Actually image_to_osd 'Rotate' is the angle to rotate CW to make it upright.
                # So we verify logic: if Rotate: 90, we rotate 90? Or -90?
                # Usually standard behavior: rotate the image by that amount.
                img = img.rotate(angle, expand=True)
    except Exception as e:
        # OSD can fail on images with no text or too much noise
        pass

    # 3. Autocontrast (Max contrast for better separation)
    img = ImageOps.autocontrast(img)
    
    # 4. Rescale if small (assuming A4 width is approx 8.3 inches, 300 DPI -> ~2500px)
    target_width = 2500
    if img.width < 1500:
        ratio = target_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((target_width, new_height), resample=3)  # LANZCOS/BICUBIC
    
    # 5. Sharpen (subtle enhancement)
    img = img.filter(ImageFilter.SHARPEN)
    
    return img


def _extract_image_text(path: Path) -> str:
    try:
        from PIL import Image, ImageOps, ImageFilter
        import pytesseract
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("OCR dependencies (Pillow, pytesseract) are not installed; skipping OCR")
        return ""

    try:
        with Image.open(path) as img:
            # Preprocess image to improve accuracy (fix "eaten" letters)
            processed_img = _preprocess_for_ocr(img)
            
            text_out = pytesseract.image_to_string(processed_img, lang='pol+eng')
            print(f"DEBUG: EXTRACTED IMAGE TEXT (flush):\n{text_out}\n-----------------------", flush=True)
            return text_out
    except Exception as e:  # pragma: no cover - defensive logging
        print(f"DEBUG: OCR CRASHED: {e}", flush=True)
        logger.exception("Не удалось прочитать изображение %s через OCR", path)
        return ""


def _read_plain_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Не удалось прочитать файл %s как текст", path)
        return ""


def extract_text(path: str | Path) -> str:
    """Extract raw text from the uploaded summons file.

    Prefers PDF parsing when the file has a PDF extension. Falls back to a
    simple text read when parsing fails or for non-PDF files.
    """

    file_path = Path(path)

    text = ""
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        text = _extract_pdf_text(file_path)

    if suffix in IMAGE_SUFFIXES:
        return _extract_image_text(file_path)

    if not text:
        text = _read_plain_text(file_path)

    return text



def _try_normalize_wsc(text: str) -> str | None:
    """Attempt to fix common OCR errors in WSC numbers (e.g. 11->II, Ws->WSC)."""
    # Regex to pull apart the components: Prefix - Roman - Code . Numbers
    # Matches things like "Ws -11-5.6151..."
    pattern = re.compile(
        r"^([A-Z0-9\s]{2,5})[-\s]+([XIV1l\d]{1,5})[-\s]+([A-Z0-9])([.\s]+\d{4}[.\s]+\d+)", 
        re.IGNORECASE
    )
    match = pattern.search(text)
    if not match:
        return None
        
    prefix, roman, code, numbers = match.groups()
    
    # 1. Normalize Prefix
    n_prefix = prefix.upper().replace(" ", "").replace("VV", "W").replace("5", "S").replace("$", "S")
    if n_prefix == "WS": # Common OCR error for WSC
        n_prefix = "WSC"
    if n_prefix == "W5C":
        n_prefix = "WSC"
        
    # 2. Normalize Roman (1->I)
    n_roman = roman.upper().replace("1", "I").replace("L", "I")
    
    # 3. Normalize Code (5->S)
    n_code = code.upper().replace("5", "S")
    
    # 4. Normalize Numbers (remove spaces)
    n_numbers = numbers.replace(" ", "")
    
    return f"{n_prefix}-{n_roman}-{n_code}{n_numbers}"


def _find_case_number(text: str) -> str | None:
    candidates: list[str] = []
    candidate_log = []
    
    # 1. Try Specific Patterns (Prefix-based)
    for pattern in CASE_NUMBER_PATTERNS:
        # scan the whole text for matches
        for match in pattern.finditer(text):
            raw_val = match.group(1)
            candidate_log.append(f"Pattern match: '{raw_val}'")
            
            # Try advanced WSC normalization first
            advanced_norm = _try_normalize_wsc(raw_val)
            if advanced_norm:
                print(f"DEBUG: Advanced WSC Normalization: {raw_val} -> {advanced_norm}", flush=True)
                return advanced_norm
            
            # Standard cleanup if advanced failed
            normalized = re.sub(r"\s+", "", raw_val)
            normalized = normalized.replace("VV", "W").replace("5", "S").replace("$", "S")
            normalized = normalized.strip(".,-:/")
            normalized = normalized.upper()
            
            # Reject if too short (e.g. just "WSC") or looks like a date "2023-10-10"
            if len(normalized) < 5:
                continue
            if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
                continue
                
            print(f"DEBUG: Candidate accepted: {normalized} (from '{raw_val}')", flush=True)
            return normalized

    print(f"DEBUG: No Case Number found. Candidates extracted but rejected: {candidate_log}", flush=True)
    return None


def _find_first_date(text: str) -> date | None:
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    return None


def _detect_wezwanie_type(text: str) -> str | None:
    """Detect if this is a fingerprints invitation, decision notification, or fingerprint confirmation."""
    text_lower = text.lower()
    
    # Keywords for confirmation (post-visit)
    confirmation_keywords = ["potwierdzenie złożenia", "potwierdzenie przyjęcia", "odciski linii papilarnych zostały pobrane"]
    if any(keyword in text_lower for keyword in confirmation_keywords):
        return "confirmation"

    # Keywords for decision wezwanie (second type)
    decision_keywords = ["decyzj", "wydanie decyzji", "termin wydania", "termin rozpatrz"]
    if any(keyword in text_lower for keyword in decision_keywords):
        return "decision"
    
    # Keywords for fingerprints wezwanie (first type)
    fingerprint_keywords = ["odcisk", "odciski", "pobran", "fingerprint"]
    if any(keyword in text_lower for keyword in fingerprint_keywords):
        return "fingerprints"
    
    return None


def _find_fingerprints_time(text: str) -> str | None:
    """Extract fingerprints appointment time."""
    time_patterns = [
        re.compile(r"godz\.\s*(\d{1,2}[:.]\d{2})", re.IGNORECASE),
        re.compile(r"godzinie\s*(\d{1,2}[:.]\d{2})", re.IGNORECASE),
        re.compile(r"at\s*(\d{1,2}[:.]\d{2})", re.IGNORECASE),
    ]
    for pattern in time_patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).replace('.', ':')
    return None


def _find_fingerprints_location(text: str) -> str | None:
    """Extract fingerprints appointment location."""
    location_patterns = [
        re.compile(r"sala\s*(\d+)", re.IGNORECASE),
        re.compile(r"pokój\s*(\d+)", re.IGNORECASE),
        re.compile(r"miejsce[:\s]+(.*?)(?:\.|\n)", re.IGNORECASE),
        re.compile(r"ul\.\s*([^,\n]+)", re.IGNORECASE),
    ]
    for pattern in location_patterns:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def _find_decision_date(text: str) -> date | None:
    """Extract decision date from second wezwanie."""
    # Patterns for decision date with keywords
    decision_patterns = [
        # Pattern: "powinna być podjęta do dnia DD.MM.YYYY"
        re.compile(r"powinna być podjęta do dnia\s+([\d./-]+)", re.IGNORECASE),
        # Pattern: "termin wydania decyzji: DD.MM.YYYY"
        re.compile(r"termin wydania decyzji[:\s]+([\d./-]+)", re.IGNORECASE),
        # Pattern: "decyzja ... do dnia DD.MM.YYYY"
        re.compile(r"decyzj[aiy].*?do dnia\s+([\d./-]+)", re.IGNORECASE),
        # General fallback
        re.compile(r"(?:rozpatrzenie|termin).*?do[:\s]+([\d./-]+)", re.IGNORECASE),
    ]
    
    for pattern in decision_patterns:
        match = pattern.search(text)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                return parsed
    
    return None


def _find_full_name(text: str) -> str | None:
    """Extract full name from wezwanie (Polish names)."""
    name_patterns = [
        # Pattern: "Pan/Pani Anna Nowak" (Strict Case for name parts to avoid 'ul.')
        re.compile(
            r"(?:Pan/Pani|Pan|Pani|Panna|Pan/i|Panli)\s+"
            r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+"
            r"(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+|\s+[A-ZĄĆĘŁŃÓŚŹŻ]{2,}){1,3})",
            re.UNICODE,
        ),
        # Pattern: "Adresat: Jan Kowalski"
        re.compile(
            r"(?:Adresat|Dla|Do)\s*[:\-]?\s+"
            r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+){1,3})",
            re.UNICODE,
        ),
        # Pattern: "Imię i nazwisko: Jan Kowalski"
        re.compile(r"(?:imię i nazwisko|imi[ęe] oraz nazwisko)[:\s]+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)+)", re.IGNORECASE | re.UNICODE),
        # Pattern: "Name: Jan Kowalski"
        re.compile(r"(?:name|full name)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", re.IGNORECASE),
    ]
    
    for pattern in name_patterns:
        match = pattern.search(text)
        if match:
            name = match.group(1).strip()
            # Validate: should have at least 2 words
            if len(name.split()) >= 2:
                return name
    
    return None


def parse_wezwanie(file_path: str | Path) -> WezwanieData:
    """Parse the uploaded summons and return the extracted fields."""

    text = extract_text(file_path)
    if not text.strip():
        return WezwanieData(text="", error="no_text")
    print(f"DEBUG: EXTRACTED TEXT START (1000 chars):\n{text[:1000]}\n...", flush=True)

    wezwanie_type = _detect_wezwanie_type(text)
    print(f"DEBUG: Detected Type: {wezwanie_type}", flush=True)

    case_number = _find_case_number(text)
    print(f"DEBUG: Case Number found: {case_number}", flush=True)

    full_name = _find_full_name(text)
    print(f"DEBUG: Full Name found: {full_name}", flush=True)

    
    # Extract dates based on type
    fingerprints_date = None
    fingerprints_time = None
    fingerprints_location = None
    decision_date = None
    
    if wezwanie_type == "decision":
        # Second wezwanie - look for decision date
        decision_date = _find_decision_date(text)
        if not decision_date:
            # Fallback to first date found
            decision_date = _find_first_date(text)
    elif wezwanie_type == "fingerprints":
        # First wezwanie - look for fingerprints date, time, location
        fingerprints_date = _find_first_date(text)
        fingerprints_time = _find_fingerprints_time(text)
        fingerprints_location = _find_fingerprints_location(text)
    else:
        # Unknown/Confirmation - look for fingerprints date
        fingerprints_date = _find_first_date(text)
    
    # Extract required documents
    required_documents = _extract_required_documents(text)
    
    return WezwanieData(
        text=text,
        case_number=case_number,
        fingerprints_date=fingerprints_date,
        fingerprints_time=fingerprints_time,
        fingerprints_location=fingerprints_location,
        decision_date=decision_date,
        full_name=full_name,
        wezwanie_type=wezwanie_type,
        required_documents=required_documents,
    )


def _extract_required_documents(text: str) -> list[str]:
    """Scan text for keywords indicating required documents."""
    found_docs = set()
    text_lower = text.lower()
    
    # Mapping of DocumentType to regex patterns
    # Note: These should be robust enough to catch standard phrasing in Wezwanias
    patterns = {
        DocumentType.PHOTOS: [r"4\s*zdjęcia", r"fotografie"],
        DocumentType.PAYMENT_CONFIRMATION: [r"opłata\s*skarbowa", r"dowód\s*wpłaty", r"340\s*z[łl]", r"440\s*z[łl]"],
        DocumentType.PASSPORT: [r"kopia\s*paszportu", r"dokument\s*podróży"],
        DocumentType.HEALTH_INSURANCE: [r"ubezpieczeni[ea]", r"polisa"],
        DocumentType.ZALACZNIK_NR_1: [r"załącznik\s*nr\s*1"],
        DocumentType.WORK_PERMISSION: [r"zezwolenie\s*na\s*pracę", r"oświadczenie\s*o\s*powierzeniu"],
        DocumentType.ADDRESS_PROOF: [r"umowa\s*najmu", r"koszty\s*zamieszkania", r"akt\s*własności"],
        DocumentType.FINANCIAL_PROOF: [r"środki\s*finansowe", r"posiadaniu\s*środków", r"wyciąg\s*z\s*konta"],
        DocumentType.PIT_PROOF: [r"pit-37", r"zeznanie\s*podatkowe"],
        DocumentType.ZUS_RCA_OR_INSURANCE: [r"zus\s*rca", r"zgłoszenie\s*do\s*zus"],
    }

    for doc_type, regex_list in patterns.items():
        for pattern in regex_list:
            if re.search(pattern, text_lower):
                found_docs.add(doc_type.value)
                break  # Found this document type, move to next
    
    return list(found_docs)
