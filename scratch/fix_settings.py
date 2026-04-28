import os

f = r'e:\Anigravity\Legalize_site\Legalize_site-1\legalize_site\settings\base.py'
with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

insert_lines = [
    '# Persistent connections: avoid per-request connect/disconnect overhead in',
    '# production with gunicorn workers.  CONN_HEALTH_CHECKS lets Django silently',
    '# reconnect when a pooled connection goes stale.',
    'DATABASES["default"]["CONN_MAX_AGE"] = int(os.environ.get("CONN_MAX_AGE", "600"))',
    'DATABASES["default"]["CONN_HEALTH_CHECKS"] = True',
    '',
    '# Limit staff sessions to 8 hours (one work day) by default.',
    'SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", "28800"))',
    '',
]

marker = '\u0412\u0410\u041b\u0418\u0414\u0410\u0422\u041e\u0420\u042b \u041f\u0410\u0420\u041e\u041b\u0415\u0419'
insert_text = '\n'.join(insert_lines) + '\n'

content = content.replace('# --- ' + marker + ' ---', insert_text + '# --- ' + marker + ' ---')

with open(f, 'w', encoding='utf-8') as fh:
    fh.write(content)
print('Done')
