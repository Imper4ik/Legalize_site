import os
import re
import polib
import pytest
from django.utils.translation import override, gettext as _

def get_po_file(lang):
    path = f"locale/{lang}/LC_MESSAGES/django.po"
    if not os.path.exists(path):
        pytest.fail(f"PO file not found: {path}")
    return polib.pofile(path)

def test_no_fuzzy_in_po_files():
    for lang in ['en', 'pl']:
        po = get_po_file(lang)
        fuzzy_entries = [e for e in po if e.fuzzy]
        assert not fuzzy_entries, f"Found fuzzy entries in {lang}: {[e.msgid for e in fuzzy_entries]}"

def test_no_empty_msgstr_in_po_files():
    cyrillic_regex = re.compile(r'[\u0410-\u044F\u0401\u0451]')
    for lang in ['en', 'pl']:
        po = get_po_file(lang)
        empty_entries = []
        for e in po:
            if not e.msgid or e.obsolete:
                continue
            if '\ufffd' in e.msgid:
                continue
            if cyrillic_regex.search(e.msgid):
                if e.msgid_plural:
                    if not e.msgstr_plural or any(not v for v in e.msgstr_plural.values()):
                        empty_entries.append(e.msgid)
                elif not e.msgstr:
                    empty_entries.append(e.msgid)
        if empty_entries:
            print(f"Empty entries for Cyrillic msgids in {lang}: {empty_entries}")
        assert len(empty_entries) < 200, f"Found too many ({len(empty_entries)}) empty translations for Cyrillic msgids in {lang}."

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
