
import re
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Copied from wezwanie_parser.py
CASE_NUMBER_PATTERNS = (
    # 0. NEW: Strict WSC Pattern (High Priority)
    re.compile(r"\b(WSC[-\s]+[XIV]+[-\s]+[A-Z][.\s]+\d+[.\s]+\d+(?:[.\s]+\d+)?)\b", re.IGNORECASE),
    
    # 0.5. NEW: Very Permissive WSC/WSO Pattern
    re.compile(r"\b((?:WSC|WSO|W\$C|W5C)[-\s]+[XIV1l]+[-\s]+[A-Z5$][.\s]+\d+[.\s]+\d+(?:[.\s]+\d+)?)\b", re.IGNORECASE),

    re.compile(r"numer\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"nr\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"sprawa\s+nr[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"(?:sygnatura|sygn\.)\s*akt[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"sygnatura[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"nr\s+akt[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    re.compile(r"znak\s+sprawy[:\s]*([-A-Za-z0-9./ ]+)", re.IGNORECASE),
    
    # 1. Wide net for WSC (single line only)
    re.compile(r"((?:W[ \t]*S[ \t]*C|S[ \t]*O[ \t]*C|W[ \t]*5[ \t]*C|V[ \t]*V[ \t]*S[ \t]*C|W[ \t]*\$[ \t]*C|W[ \t]*\.[ \t]*S[ \t]*\.[ \t]*C)(?!\.[\w]+\.pl)[-\w. /]{5,})", re.IGNORECASE),
    
    # 2. Structure match (single line only)
    re.compile(r"([A-Z0-9 ]{2,5}[- ]+[XIV1l\d]{1,5}[- ]+[A-Z0-9][. ]+\d{4}[. ]+\d+(?:[. ]+\d+)?)", re.IGNORECASE),
    
    # 3. Generic fallback
    re.compile(r"\b([A-Z]{2,4}[- ][XIV]+\.[-\w./]+)\b", re.IGNORECASE),
    
    # 4. Old Strict fallback
    re.compile(r"\b([A-Z]{1,3}[ \t]?/[ \t]?\d{1,5}[ \t]?/[ \t]?\d{2,4})\b"),
)

def _try_normalize_wsc(text: str) -> str | None:
    pattern = re.compile(
        r"^([A-Z0-9\s]{2,5})[-\s]+([XIV1l\d]{1,5})[-\s]+([A-Z0-9])([.\s]+\d+(?:[.\s]+\d+)+)", 
        re.IGNORECASE
    )
    match = pattern.search(text)
    if not match:
        return None
        
    prefix, roman, code, numbers = match.groups()
    n_prefix = prefix.upper().replace(" ", "").replace("VV", "W").replace("5", "S").replace("$", "S")
    if n_prefix == "WS": n_prefix = "WSC"
    if n_prefix == "W5C": n_prefix = "WSC"
    if n_prefix == "SOC": n_prefix = "WSC"
    n_roman = roman.upper().replace("1", "I").replace("L", "I")
    n_code = code.upper().replace("5", "S")
    n_numbers = numbers.replace(" ", "")
    return f"{n_prefix}-{n_roman}-{n_code}{n_numbers}"

def _find_case_number(text: str) -> str | None:
    candidate_log = []
    
    for i, pattern in enumerate(CASE_NUMBER_PATTERNS):
        print(f"Checking pattern {i}: {pattern.pattern}")
        for match in pattern.finditer(text):
            raw_val = match.group(1)
            
            if "mazowieckie.pl" in raw_val.lower():
                continue
                
            candidate_log.append(f"Pattern match: '{raw_val}'")
            
            advanced_norm = _try_normalize_wsc(raw_val)
            if advanced_norm:
                return advanced_norm
            
            normalized = re.sub(r"\s+", "", raw_val)
            normalized = normalized.replace("VV", "W").replace("5", "S").replace("$", "S")
            normalized = normalized.strip(".,-:/")
            normalized = normalized.upper()
            
            if len(normalized) < 5:
                continue
            if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
                continue
                
            return normalized

    print(f"No case number found. Candidates rejected: {candidate_log}")
    return None

import sys

# Windows console encoding fix
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

raw_text = "E2 £9 869 (CE) 1 spuzoneofojay pnnłofińAT anpor mor OSAUYDIOY, śdiry AMOŁyM 09 2inpmiaiol00'$1-00' это все в номер дела еаписало"
print(f"Testing text: {raw_text}")
result = _find_case_number(raw_text)
print(f"FOUND: {result}")
