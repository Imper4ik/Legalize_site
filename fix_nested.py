import os, re

for directory in ['clients/templates', 'templates']:
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                pattern = re.compile(r'\{%\s*blocktrans.*?%\}(.*?)\{%\s*endblocktrans\s*%\}', flags=re.DOTALL)
                
                def repl(m):
                    inner = m.group(1)
                    new_inner = re.sub(r'\{%\s*translate\s+([\'"])(.*?)\1\s*%\}', r'\2', inner)
                    return m.group(0).replace(inner, new_inner)
                
                new_content = pattern.sub(repl, content)
                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f'Fixed {path}')
