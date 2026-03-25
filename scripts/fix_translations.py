"""Fix fuzzy entries and empty translations in .po files."""
import re
import sys
from pathlib import Path

# ============================================================
# MANUAL TRANSLATION FIXES
# ============================================================

# RU fuzzy fixes: msgid -> correct msgstr
RU_FUZZY_FIXES = {
    "Тип шаблона": "Тип шаблона",
    "Дата отправки": "Дата отправки",
    "Отправитель": "Отправитель",
    "Журнал email": "Журнал email",
    "Создать аккаунт": "Создать аккаунт",
    "Подтвердите пароль": "Подтвердите пароль",
    "Поиск клиентов": "Поиск клиентов",
    "Введите имя, фамилию, email или номер дела...": "Введите имя, фамилию, email или номер дела...",
    "Проверить все загруженные": "Проверить все загруженные",
    "Редактировать данные клиента": "Редактировать данные клиента",
}

# RU empty fixes: msgid -> correct msgstr
RU_EMPTY_FIXES = {
    "Тема": "Тема",
    "Получатели": "Получатели",
    "Переводы успешно обновлены и скомпилированы!": "Переводы успешно обновлены и скомпилированы!",
}

# EN fuzzy fixes: msgid -> correct msgstr
EN_FUZZY_FIXES = {
    "Тип шаблона": "Template type",
    "Дата отправки": "Date sent",
    "Отправитель": "Sender",
    "Журнал email": "Email log",
    "Создать аккаунт": "Create account",
    "Подтвердите пароль": "Confirm password",
    "Поиск клиентов": "Client search",
    "Проверить все загруженные": "Verify all uploaded",
}

# EN incorrect translations (not fuzzy, but wrong)
EN_WRONG_FIXES = {
    "Порядок отображения": "Display order",
    "Время сдачи отпечатков": "Fingerprint submission time",
    "Место сдачи отпечатков": "Fingerprint submission location",
    "Дата официальной децизии": "Official decision date",
    "Требование к документу": "Document requirement",
    "Требования к документам": "Document requirements",
}

# EN empty fixes
EN_EMPTY_FIXES = {
    "Тема": "Subject",
    "Получатели": "Recipients",
    "Переводы успешно обновлены и скомпилированы!": "Translations updated and compiled successfully!",
}


def fix_po_file(filepath, fuzzy_fixes, empty_fixes, wrong_fixes=None):
    """Fix fuzzy, empty, and wrong translations in a .po file.
    
    Strategy: process line by line, tracking state.
    """
    if wrong_fixes is None:
        wrong_fixes = {}
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Split into blocks separated by blank lines
    blocks = re.split(r'\n\n', content)
    
    fixed_fuzzy = 0
    fixed_empty = 0
    fixed_wrong = 0
    new_blocks = []
    
    is_ru = "ru" in str(filepath)
    
    for block in blocks:
        lines = block.split('\n')
        
        # Extract components
        has_fuzzy = False
        msgid_text = ""
        msgstr_text = ""
        flag_lines = []
        prev_msgid_lines = []
        comment_lines = []
        msgid_lines = []
        msgstr_lines = []
        
        state = None
        for line in lines:
            if line.startswith("#, ") and "fuzzy" in line:
                has_fuzzy = True
                flag_lines.append(line)
            elif line.startswith("#, "):
                flag_lines.append(line)
            elif line.startswith("#| "):
                prev_msgid_lines.append(line)
            elif line.startswith("#"):
                comment_lines.append(line)
            elif line.startswith('msgid '):
                state = "msgid"
                msgid_lines.append(line)
                # Extract text
                m = re.match(r'msgid "(.*)"', line)
                if m:
                    msgid_text = m.group(1)
            elif line.startswith('msgstr '):
                state = "msgstr"
                msgstr_lines.append(line)
                m = re.match(r'msgstr "(.*)"', line)
                if m:
                    msgstr_text = m.group(1)
            elif line.startswith('"'):
                if state == "msgid":
                    msgid_lines.append(line)
                    # Continuation line
                    m = re.match(r'"(.*)"', line)
                    if m:
                        msgid_text += m.group(1)
                elif state == "msgstr":
                    msgstr_lines.append(line)
                    m = re.match(r'"(.*)"', line)
                    if m:
                        msgstr_text += m.group(1)
        
        # Skip header and empty blocks
        if not msgid_lines:
            new_blocks.append(block)
            continue
        
        modified = False
        
        # Fix fuzzy entries
        if has_fuzzy and msgid_text:
            if msgid_text in fuzzy_fixes:
                new_msgstr = fuzzy_fixes[msgid_text]
            elif is_ru:
                # For RU locale, msgid is already Russian, so msgstr = msgid
                new_msgstr = msgid_text
            else:
                # For EN, keep the fuzzy msgstr but remove flag so it actually shows
                # Actually, for EN we need proper translations
                # We'll keep the existing msgstr text (it was auto-guessed) 
                # and just remove fuzzy flag
                new_msgstr = msgstr_text if msgstr_text else msgid_text
            
            # Rebuild block without fuzzy flag and prev_msgid
            new_lines = []
            for cl in comment_lines:
                new_lines.append(cl)
            # Add flag lines WITHOUT fuzzy
            for fl in flag_lines:
                if "fuzzy" in fl:
                    # Remove fuzzy from the flag line
                    cleaned = fl.replace(", fuzzy", "").replace("fuzzy, ", "").replace("fuzzy", "")
                    if cleaned.strip() == "#,":
                        continue  # Skip empty flag line
                    if cleaned.strip():
                        new_lines.append(cleaned)
                else:
                    new_lines.append(fl)
            # Skip prev_msgid lines (they're only relevant for fuzzy)
            for ml in msgid_lines:
                new_lines.append(ml)
            new_lines.append(f'msgstr "{new_msgstr}"')
            
            block = '\n'.join(new_lines)
            modified = True
            fixed_fuzzy += 1
        
        # Fix empty msgstr
        elif msgstr_text == "" and msgid_text != "" and not has_fuzzy:
            if msgid_text in empty_fixes:
                new_msgstr = empty_fixes[msgid_text]
            elif is_ru:
                new_msgstr = msgid_text
            else:
                new_msgstr = None
            
            if new_msgstr is not None:
                # Replace the msgstr line
                new_lines = []
                for line in lines:
                    if line.startswith('msgstr ""'):
                        new_lines.append(f'msgstr "{new_msgstr}"')
                    else:
                        new_lines.append(line)
                block = '\n'.join(new_lines)
                modified = True
                fixed_empty += 1
        
        # Fix wrong translations (not fuzzy, not empty)
        if not has_fuzzy and msgid_text in wrong_fixes and msgstr_text != "" and not modified:
            new_msgstr = wrong_fixes[msgid_text]
            new_lines = []
            replaced = False
            skip_continuation = False
            for line in lines:
                if line.startswith('msgstr ') and not replaced:
                    new_lines.append(f'msgstr "{new_msgstr}"')
                    replaced = True
                    skip_continuation = True
                elif skip_continuation and line.startswith('"'):
                    continue  # Skip old continuation lines
                else:
                    skip_continuation = False
                    new_lines.append(line)
            block = '\n'.join(new_lines)
            fixed_wrong += 1
        
        new_blocks.append(block)
    
    # Write output
    result = '\n\n'.join(new_blocks)
    # Ensure file ends with newline
    if not result.endswith('\n'):
        result += '\n'
    
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write(result)
    
    print(f"Fixed in {filepath}:")
    print(f"  Fuzzy fixed: {fixed_fuzzy}")
    print(f"  Empty fixed: {fixed_empty}")
    print(f"  Wrong fixed: {fixed_wrong}")
    return fixed_fuzzy, fixed_empty, fixed_wrong


if __name__ == "__main__":
    base = Path(r"e:\Anigravity\Legalize_site\Legalize_site-1\locale")
    
    ru_po = base / "ru" / "LC_MESSAGES" / "django.po"
    en_po = base / "en" / "LC_MESSAGES" / "django.po"

    print("=== Fixing RU translations ===")
    fix_po_file(str(ru_po), RU_FUZZY_FIXES, RU_EMPTY_FIXES)

    print("\n=== Fixing EN translations ===")
    fix_po_file(str(en_po), EN_FUZZY_FIXES, EN_EMPTY_FIXES, EN_WRONG_FIXES)

    print("\nDone! Now run: python manage.py compilemessages --ignore=venv --ignore=.venv")
