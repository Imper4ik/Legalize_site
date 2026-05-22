import os, re

for directory in ['clients/templates', 'templates']:
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # fix blocktrans inside blocktranslate
                new_content = re.sub(r'\{%\s*blocktranslate\s*%\}\s*\{%\s*blocktrans\s*%\}', '{% blocktranslate %}', content)
                new_content = re.sub(r'\{%\s*endblocktrans\s*%\}\s*\{%\s*endblocktranslate\s*%\}', '{% endblocktranslate %}', new_content)
                
                # fix translate inside blocktranslate
                def repl(m):
                    inner = m.group(1)
                    new_inner = re.sub(r'\{%\s*translate\s+([\'"])(.*?)\1\s*%\}', r'\2', inner)
                    return m.group(0).replace(inner, new_inner)
                
                pattern = re.compile(r'\{%\s*blocktranslate.*?%\}(.*?)\{%\s*endblocktranslate\s*%\}', flags=re.DOTALL)
                new_content = pattern.sub(repl, new_content)
                
                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f'Fixed {path}')
