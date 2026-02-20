import os
import re

def fix_po_file(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Processing {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = re.split(r'\n\s*\n', content)
    
    seen_msgids = set()
    new_blocks = []
    
    msgid_pattern = re.compile(r'^msgid\s+"(.*)"', re.MULTILINE)
    obs_msgid_pattern = re.compile(r'^#~\s+msgid\s+"(.*)"', re.MULTILINE)
    
    for block in blocks:
        if not block.strip():
            continue
            
        if block.startswith('msgid ""'):
            new_blocks.append(block)
            continue
            
        match = msgid_pattern.search(block)
        obs_match = obs_msgid_pattern.search(block)
        
        if match:
            msgid = match.group(1)
            full_msgid_match = re.search(r'msgid\s+(".*?(?:\n".*?")*)\nmsgstr', block, re.DOTALL)
            key = full_msgid_match.group(1) if full_msgid_match else msgid
            
            if key not in seen_msgids:
                seen_msgids.add(key)
                new_blocks.append(block)
            else:
                try: print(f"  Removed duplicate msgid: {key[:50]}...")
                except UnicodeEncodeError: print("  Removed a duplicate")
        elif obs_match:
            # For obsolete messages, just extract the string to check for duplicates
            msgid = obs_match.group(1)
            full_msgid_match = re.search(r'#~\s+msgid\s+(".*?(?:\n#~\s+".*?")*)\n#~\s+msgstr', block, re.DOTALL)
            key = full_msgid_match.group(1) if full_msgid_match else msgid
            
            if key not in seen_msgids:
                seen_msgids.add(key)
                new_blocks.append(block)
            else:
                try: print(f"  Removed obsolete duplicate msgid: {key[:50]}...")
                except UnicodeEncodeError: print("  Removed an obsolete duplicate")
        else:
            new_blocks.append(block)
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(new_blocks) + '\n')
    print(f"Fixed {filepath}.\n")

if __name__ == "__main__":
    locales = ['pl', 'ru', 'en']
    for loc in locales:
        p = os.path.join('locale', loc, 'LC_MESSAGES', 'django.po')
        fix_po_file(p)
