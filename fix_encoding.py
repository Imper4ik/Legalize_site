import codecs

# Read the file with UTF-8 encoding
with codecs.open(r'e:\Anigravity\Legalize_site\Legalize_site-1\templates\clients\partials\modals.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Write it back with UTF-8 BOM to ensure Git recognizes the encoding
with codecs.open(r'e:\Anigravity\Legalize_site\Legalize_site-1\templates\clients\partials\modals.html', 'w', encoding='utf-8-sig') as f:
    f.write(content)

print("File re-encoded with UTF-8 BOM")
