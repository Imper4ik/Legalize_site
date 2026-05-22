import os
import re
import json

def process_html_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = re.compile(r'(<script.*?</script>|<style.*?</style>|<!--.*?-->|\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}|<[^>]+>)', flags=re.DOTALL | re.IGNORECASE)
    parts = pattern.split(content)
    
    new_parts = []
    changed = False
    
    for i, part in enumerate(parts):
        if i % 2 == 1:
            tag = part
            if tag.startswith('<') and not tag.startswith('</') and not tag.startswith('<script') and not tag.startswith('<style'):
                attr_pattern = re.compile(r'(placeholder|title|alt)=([\'"])([^\'"]*[А-Яа-яЁё][^\'"]*)([\'"])')
                def attr_repl(m):
                    attr_name = m.group(1)
                    q = m.group(2)
                    val = m.group(3)
                    return f'{attr_name}={q}{{% translate "{val}" %}}{q}'
                
                new_tag, count = attr_pattern.subn(attr_repl, tag)
                if count > 0:
                    changed = True
                    tag = new_tag
            new_parts.append(tag)
        else:
            text = part
            stripped = text.strip()
            if stripped and re.search(r'[А-Яа-яЁё]', stripped):
                # find start and end
                start_idx = text.find(stripped)
                end_idx = start_idx + len(stripped)
                
                leading = text[:start_idx]
                trailing = text[end_idx:]
                
                if '\n' in stripped:
                    new_parts.append(f"{leading}{{% blocktrans %}}{stripped}{{% endblocktrans %}}{trailing}")
                    changed = True
                else:
                    val = stripped
                    if '"' in val and "'" not in val:
                        new_tag = f"{{% translate '{val}' %}}"
                    elif '"' in val and "'" in val:
                        val = val.replace('"', '\\"')
                        new_tag = f'{{% translate "{val}" %}}'
                    else:
                        new_tag = f'{{% translate "{val}" %}}'
                        
                    new_parts.append(f"{leading}{new_tag}{trailing}")
                    changed = True
            else:
                new_parts.append(text)
                
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("".join(new_parts))
        print(f"Updated {filepath}")

with open('ru_scan_results.json', 'r', encoding='utf-8') as f:
    files = json.load(f)

for filepath in files.keys():
    process_html_file(filepath)
