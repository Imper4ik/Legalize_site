import os

src = r'e:\Anigravity\Legalize_site\Legalize_site-1\static\clients\js\client_detail.js'
dest = r'e:\Anigravity\Legalize_site\Legalize_site-1\static\clients\js\client'

with open(src, 'r', encoding='utf-8') as f:
    lines = f.readlines()

def get(start, end):
    # start and end are 1-indexed, inclusive
    res = lines[start-1:end]
    return [l[2:] if l.startswith('  ') else l for l in res]

ajax_js = get(7, 111) + get(163, 194) + get(245, 260)
payments_js = get(117, 161) + get(196, 243) + get(262, 426)
documents_js = get(428, 771) + get(958, 1097)
checklist_js = get(2, 5) + get(113, 115) + get(773, 956)
email_modal_js = get(1099, 1231)
init_js = get(1233, 1246)

if not os.path.exists(dest):
    os.makedirs(dest)

def write_f(name, content):
    with open(os.path.join(dest, name), 'w', encoding='utf-8') as f:
        f.writelines(content)

write_f('ajax.js', ajax_js)
write_f('payments.js', payments_js)
write_f('documents.js', documents_js)
write_f('checklist.js', checklist_js)
write_f('email_modal.js', email_modal_js)
write_f('init.js', init_js)

print("Extraction successful.")
