import os
import re
from pathlib import Path
import polib
import pytest
from django.utils.translation import override, gettext as _

PLACEHOLDER_REGEX = re.compile(r'%\([^)]+\)[#0 +\-]*(?:\d+)?(?:\.\d+)?[a-zA-Z]|%s')

def get_po_file(lang):
    path = f"locale/{lang}/LC_MESSAGES/django.po"
    if not os.path.exists(path):
        pytest.fail(f"PO file not found: {path}")
    return polib.pofile(path)

def test_no_fuzzy_in_po_files():
    for lang in ['en', 'pl', 'ru']:
        po = get_po_file(lang)
        fuzzy_entries = [e for e in po if e.fuzzy]
        assert not fuzzy_entries, f"Found fuzzy entries in {lang}: {[e.msgid for e in fuzzy_entries]}"

def test_no_previous_msgids_in_po_files():
    for lang in ['en', 'pl', 'ru']:
        po = get_po_file(lang)
        previous_entries = [
            e.msgid
            for e in po
            if not e.obsolete and (getattr(e, "previous_msgid", None) or getattr(e, "previous_msgid_plural", None))
        ]
        assert not previous_entries, f"Found stale previous msgids in {lang}: {previous_entries[:10]}"

def test_no_empty_msgstr_in_po_files():
    for lang in ['en', 'pl', 'ru']:
        po = get_po_file(lang)
        empty_entries = []
        for e in po:
            if not e.msgid or e.obsolete:
                continue
            if '\ufffd' in e.msgid:
                continue
            if e.msgid_plural:
                if not e.msgstr_plural or any(not v for v in e.msgstr_plural.values()):
                    empty_entries.append(e.msgid)
            elif not e.msgstr:
                empty_entries.append(e.msgid)
        if empty_entries:
            print(f"Empty entries in {lang}: {empty_entries[:20]}")
        assert not empty_entries, f"Found empty translations in {lang}: {empty_entries[:10]}"

def test_placeholders_match_in_po_files():
    for lang in ['en', 'pl', 'ru']:
        po = get_po_file(lang)
        bad_entries = []
        for e in po:
            if not e.msgid or e.obsolete:
                continue
            pairs = []
            if e.msgid_plural:
                pairs = [
                    (e.msgid, e.msgstr_plural.get(0, "")),
                    (e.msgid_plural, e.msgstr_plural.get(1, "")),
                ]
            else:
                pairs = [(e.msgid, e.msgstr)]
            for msgid, msgstr in pairs:
                if set(PLACEHOLDER_REGEX.findall(msgid)) != set(PLACEHOLDER_REGEX.findall(msgstr)):
                    bad_entries.append((msgid, msgstr))

        assert not bad_entries, f"Found placeholder mismatches in {lang}: {bad_entries[:10]}"

def test_no_cyrillic_in_en_pl_msgstr():
    cyrillic_regex = re.compile(r'[\u0410-\u044F\u0401\u0451]')
    for lang in ['en', 'pl']:
        po = get_po_file(lang)
        cyrillic_entries = []
        for e in po:
            if e.obsolete:
                continue
            text = ""
            if e.msgid_plural:
                text = "".join(e.msgstr_plural.values())
            else:
                text = e.msgstr
            
            if cyrillic_regex.search(text):
                cyrillic_entries.append((e.msgid, text))
        
        assert not cyrillic_entries, f"Found Cyrillic in {lang} translations: {cyrillic_entries[:5]}"

def test_cyrillic_msgids_exist_in_en_pl_catalogs():
    cyrillic_regex = re.compile(r'[\u0410-\u044F\u0401\u0451]')
    ru_po = get_po_file("ru")
    ru_msgids = {
        e.msgid
        for e in ru_po
        if not e.obsolete and e.msgid and not e.msgid_plural and cyrillic_regex.search(e.msgid)
    }

    for lang in ['en', 'pl']:
        po = get_po_file(lang)
        lang_msgids = {e.msgid for e in po if not e.obsolete and e.msgid}
        missing = sorted(ru_msgids - lang_msgids)

        assert not missing, f"Found RU source msgids missing from {lang}: {missing[:10]}"

def test_no_broken_encoding_markers_in_po_files():
    suspicious_question_mark = re.compile(r'[A-Za-z]\?[A-Za-z]')
    bad_entries = []
    for lang in ['en', 'pl', 'ru']:
        po = get_po_file(lang)
        for e in po:
            if e.obsolete:
                continue
            texts = e.msgstr_plural.values() if e.msgid_plural else [e.msgstr]
            for text in texts:
                if "\ufffd" in text or suspicious_question_mark.search(text):
                    bad_entries.append((lang, e.msgid, text))
                    break

    assert not bad_entries, f"Found possible broken encoding in PO files: {bad_entries[:10]}"

def _is_repairable_mojibake(value):
    if not value or not re.search(r'[^\x00-\x7F]', value):
        return False

    for encoding in ('cp1251', 'cp1252'):
        try:
            repaired = value.encode(encoding).decode('utf-8')
        except UnicodeError:
            continue
        if repaired != value and re.search(r'[\u0400-\u04FF\u0100-\u017F]', repaired):
            return True
    return False


def test_no_repairable_mojibake_in_i18n_sources():
    paths = []
    for root in ['clients', 'translations', 'submissions', 'users', 'templates', 'locale']:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for suffix in ('*.py', '*.html', '*.po'):
            paths.extend(root_path.rglob(suffix))

    bad_lines = []
    for path in paths:
        if any(part in {'migrations', '__pycache__'} for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(lines, 1):
            if _is_repairable_mojibake(line):
                bad_lines.append(f'{path}:{line_no}')
                break

    assert not bad_lines, f"Found repairable mojibake in i18n source files: {bad_lines[:20]}"


def test_no_cyrillic_in_js_files():
    cyrillic_regex = re.compile(r'[\u0410-\u044F\u0401\u0451]')
    js_dir = "static/clients/js/client/"
    cyrillic_found = []
    
    if not os.path.exists(js_dir):
        pytest.skip(f"JS directory not found: {js_dir}")
        
    for root, dirs, files in os.walk(js_dir):
        for file in files:
            if file.endswith('.js'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line_no, line in enumerate(lines, 1):
                        match = cyrillic_regex.search(line)
                        if match:
                            cyrillic_found.append(path)
                            break
                        
    assert not cyrillic_found, f"Found Cyrillic in JS files: {cyrillic_found}"

def test_no_polish_markers_in_ru_msgstr():
    po = get_po_file("ru")
    polish_markers = ["Nowy", "Szukaj", "według", "Edytuj", "Tytuł", "Przypomnienia", "Sprawdź", "Filtruj", "Odciski", "Płatność", "Zaktualizowano"]
    bad_entries = []
    for e in po:
        if e.obsolete:
            continue
        text = "".join(e.msgstr_plural.values()) if e.msgid_plural else e.msgstr
        if any(marker in text for marker in polish_markers):
            bad_entries.append((e.msgid, text))
                
    assert not bad_entries, f"Found Polish markers in RU translations: {bad_entries[:5]}"

def test_russian_msgids_translate_to_themselves_in_ru_po():
    po = get_po_file("ru")
    cyrillic_regex = re.compile(r'[\u0410-\u044F\u0401\u0451]')
    bad_entries = []
    for e in po:
        if e.obsolete or not e.msgid or e.msgid_plural:
            continue
        if cyrillic_regex.search(e.msgid) and e.msgstr != e.msgid:
            bad_entries.append((e.msgid, e.msgstr))

    assert not bad_entries, f"Found RU msgids with unexpected msgstr: {bad_entries[:10]}"

def test_critical_ru_translations():
    po = get_po_file("ru")
    critical_checks = {
        "Новый клиент": "Новый клиент",
        "Добавить клиента": "Добавить клиента",
        "Редактировать данные": "Редактировать данные",
        "Заголовок напоминания": "Заголовок напоминания",
        "Фильтровать": "Фильтровать",
        "Отпечатки": "Отпечатки",
        "Отпечатки пальцев": "Отпечатки пальцев",
        "Напоминания по документам": "Напоминания по документам",
        "Проверь и сгенерируй актуальные напоминания, отфильтруй по клиенту и периодам": "Проверь и сгенерируй актуальные напоминания, отфильтруй по клиенту и периодам",
        "Проверить и создать новые": "Проверить и создать новые",
    }
    for msgid, expected in critical_checks.items():
        found = False
        for e in po:
            if e.msgid == msgid:
                assert e.msgstr == expected, f"Expected '{expected}' for '{msgid}', got '{e.msgstr}'"
                found = True
                break
        assert found, f"Critical msgid '{msgid}' not found in ru PO file"

@pytest.mark.django_db
def test_gettext_ru_fallback_self():
    with override("ru"):
        assert _("Новый клиент") == "Новый клиент"
        assert _("Редактировать данные") == "Редактировать данные"
        assert _("Фильтровать") == "Фильтровать"
        assert _("Отпечатки пальцев") == "Отпечатки пальцев"
        assert _("Напоминания по документам") == "Напоминания по документам"
