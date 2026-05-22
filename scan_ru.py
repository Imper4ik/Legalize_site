import os, re

def check_html_for_russian(directory):
    found_files = {}
    for root, _, files in os.walk(directory):
        if 'venv' in root or '.venv' in root:
            continue
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Remove script and style tags completely
                    content = re.sub(r'<script.*?</script>', '', content, flags=re.DOTALL)
                    content = re.sub(r'<style.*?</style>', '', content, flags=re.DOTALL)
                    
                    # Remove Django translation tags (single line and block)
                    content = re.sub(r'\{%\s*(translate|trans).*?%\}', '', content)
                    content = re.sub(r'\{%\s*blocktrans.*?%\}.*?\{%\s*endblocktrans\s*%\}', '', content, flags=re.DOTALL)
                    
                    # Also strip typical html comments which might have russian notes
                    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
                    content = re.sub(r'\{#.*?#\}', '', content, flags=re.DOTALL)
                    
                    # remove other django tags 
                    content = re.sub(r'\{%.*?%\}', '', content)

                    # Find any remaining cyrillic characters
                    ru_matches = set(re.findall(r'[А-Яа-яЁё]+', content))
                    
                    if ru_matches:
                        found_files[path] = list(ru_matches)[:10] 
                except Exception as e:
                    pass
    return found_files

results = check_html_for_russian('.')
for k, v in results.items():
    print(f'{k}: {v}')
