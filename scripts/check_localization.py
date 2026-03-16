import os
import sys

def check_po(filepath):
    errors = []
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return [f"File not found: {filepath}"]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if line.startswith('#, fuzzy'):
            errors.append(f"{filepath}:{i+1} Contains fuzzy translation")
        
        # very simple empty msgstr check for single-line translations
        if line.startswith('msgstr ""\n') and i > 0 and lines[i-1].startswith('msgid'):
            # This might be a multiline string, but if the next line is empty, it's truly empty
            if i + 1 < len(lines) and lines[i+1].strip() == "":
                # However, msgid "" with msgstr "" at the header is valid.
                if lines[i-1].startswith('msgid ""\n') and i == 1:
                    continue
                errors.append(f"{filepath}:{i+1} Contains empty msgstr")

    return errors

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    en_po = os.path.join(base_dir, 'locale', 'en', 'LC_MESSAGES', 'django.po')
    pl_po = os.path.join(base_dir, 'locale', 'pl', 'LC_MESSAGES', 'django.po')
    
    all_errors = []
    all_errors.extend(check_po(en_po))
    all_errors.extend(check_po(pl_po))
    
    if all_errors:
        print("Localization check failed:")
        for err in all_errors:
            print(f" - {err}")
        sys.exit(1)
    else:
        print("Localization check passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
