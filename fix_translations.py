import os

BASE_DIR = r'e:\Anigravity\Legalize_site\Legalize_site-1\templates'

for root, dirs, files in os.walk(BASE_DIR):
    for file in files:
        if file.endswith('.html'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = content.replace('{% translate', '{% trans')
                new_content = new_content.replace('{% blocktranslate', '{% blocktrans')
                new_content = new_content.replace('{% endblocktranslate', '{% endblocktrans')
                
                if new_content != content:
                    print(f'Fixing {file}')
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
            except Exception as e:
                print(f"Error processing {file}: {e}")
